"""
Cross-account Authentication
Reference 코드의 인증 로직 재사용
자격증명 캐싱 추가 (WebSocket 환경에서 매번 새로운 자격증명 생성 문제 해결)
"""
import re
import boto3
from utils.logging_config import log_debug, log_error
from datetime import datetime, timedelta
import threading

# 자격증명 캐시 (계정별 저장)
_credentials_cache = {}
_cache_lock = threading.Lock()
_CACHE_EXPIRY_MINUTES = 50  # 임시 자격증명 유효 시간 (기본 1시간, 50분으로 설정)


def extract_account_id(text: str) -> str:
    """
    텍스트에서 AWS 계정 ID 추출
    Reference 코드와 동일한 로직
    
    Args:
        text: 분석할 텍스트
        
    Returns:
        12자리 계정 ID 또는 None
    """
    account_pattern = r'\d{12}'  # 단어 경계 제거
    match = re.search(account_pattern, text)
    result = match.group() if match else None
    log_debug(f"계정 ID 추출 시도: '{text}' -> '{result}'")
    return result


def get_crossaccount_credentials():
    """
    Parameter Store에서 Cross-account 자격증명 가져오기
    Reference 코드와 동일한 로직
    
    Returns:
        tuple: (access_key, secret_key) 또는 (None, None)
    """
    try:
        log_debug("Parameter Store에서 cross-account 자격증명 로드 시도")
        ssm_client = boto3.client('ssm', region_name='ap-northeast-2')
        access_key = ssm_client.get_parameter(Name='/access-key/crossaccount', WithDecryption=True)['Parameter']['Value']
        secret_key = ssm_client.get_parameter(Name='/secret-key/crossaccount', WithDecryption=True)['Parameter']['Value']
        log_debug("Cross-account 자격증명 로드 성공")
        return access_key, secret_key
    except Exception as e:
        log_error(f"Cross-account 자격증명 로드 실패: {e}")
        return None, None


def is_credentials_valid(credentials: dict) -> bool:
    """
    캐시된 자격증명이 유효한지 확인
    
    Args:
        credentials: 캐시된 자격증명 딕셔너리
        
    Returns:
        bool: 유효 여부
    """
    if not credentials or 'timestamp' not in credentials:
        return False
    
    # 캐시 만료 시간 확인
    cache_time = credentials['timestamp']
    expiry_time = cache_time + timedelta(minutes=_CACHE_EXPIRY_MINUTES)
    
    if datetime.now() > expiry_time:
        log_debug(f"자격증명 캐시 만료")
        return False
    
    return True


def get_cached_credentials(account_id: str) -> dict:
    """
    캐시에서 자격증명 가져오기
    
    Args:
        account_id: AWS 계정 ID
        
    Returns:
        dict: 유효한 자격증명 또는 None
    """
    with _cache_lock:
        log_debug(f"캐시 상태 확인: 계정={account_id}, 캐시 크기={len(_credentials_cache)}, 캐시 키={list(_credentials_cache.keys())}")
        
        if account_id in _credentials_cache:
            cached = _credentials_cache[account_id]
            if is_credentials_valid(cached):
                log_debug(f"✅ 캐시된 자격증명 사용: {account_id}")
                # 타임스탐프 제외한 자격증명만 반환
                return {
                    'AWS_ACCESS_KEY_ID': cached['AWS_ACCESS_KEY_ID'],
                    'AWS_SECRET_ACCESS_KEY': cached['AWS_SECRET_ACCESS_KEY'],
                    'AWS_SESSION_TOKEN': cached['AWS_SESSION_TOKEN']
                }
            else:
                # 만료된 캐시 삭제
                del _credentials_cache[account_id]
                log_debug(f"❌ 만료된 자격증명 캐시 삭제: {account_id}")
        else:
            log_debug(f"❌ 캐시 미스: 계정 {account_id}에 대한 캐시 없음")
    
    return None


def cache_credentials(account_id: str, credentials: dict):
    """
    자격증명을 캐시에 저장
    
    Args:
        account_id: AWS 계정 ID
        credentials: 저장할 자격증명
    """
    with _cache_lock:
        _credentials_cache[account_id] = {
            'AWS_ACCESS_KEY_ID': credentials['AWS_ACCESS_KEY_ID'],
            'AWS_SECRET_ACCESS_KEY': credentials['AWS_SECRET_ACCESS_KEY'],
            'AWS_SESSION_TOKEN': credentials['AWS_SESSION_TOKEN'],
            'timestamp': datetime.now()
        }
        log_debug(f"[캐싱 저장] 자격증명 캐시 저장: {account_id} (만료: {_CACHE_EXPIRY_MINUTES}분, 캐시 크기: {len(_credentials_cache)})")


def get_crossaccount_session(account_id: str) -> dict:
    """
    Cross-account 세션 생성 (캐싱 포함)
    Reference 코드와 동일한 로직 (User 방식 → Role 방식 폴백)
    
    Args:
        account_id: AWS 계정 ID (12자리)
        
    Returns:
        dict: AWS 환경 변수 또는 None
    """
    log_debug(f"[캐싱 시작] 계정 {account_id}에 대한 자격증명 조회")
    
    # 1. 캐시 확인 (먼저 캐시된 자격증명 사용)
    cached_creds = get_cached_credentials(account_id)
    if cached_creds:
        log_debug(f"[캐싱 성공] 캐시된 자격증명 반환: {account_id}")
        return cached_creds
    
    log_debug(f"[캐싱 미스] 새로운 자격증명 생성 필요: {account_id}")
    
    try:
        log_debug(f"계정 {account_id}에 대한 cross-account 세션 생성 시도")
        access_key, secret_key = get_crossaccount_credentials()
        if access_key and secret_key:
            log_debug("Cross-account 자격증명 확보, STS assume role 시도")
            crossaccount_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
            sts_client = crossaccount_session.client('sts')
            role_arn = f"arn:aws:iam::{account_id}:role/SaltwareCrossAccount"
            log_debug(f"Assume role: {role_arn}")
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"SlackBot-{account_id}"
            )
            credentials = assumed_role['Credentials']
            log_debug("Cross-account 세션 생성 성공")
            
            # 생성된 자격증명 캐시에 저장
            creds_dict = {
                'AWS_ACCESS_KEY_ID': credentials['AccessKeyId'],
                'AWS_SECRET_ACCESS_KEY': credentials['SecretAccessKey'],
                'AWS_SESSION_TOKEN': credentials['SessionToken']
            }
            cache_credentials(account_id, creds_dict)
            
            return creds_dict
        else:
            log_error("Cross-account 자격증명을 가져올 수 없음")
    except Exception as user_error:
        log_debug(f"User 방식 실패: {user_error}")

        # Role 방식 폴백 시도 (2단계)
        try:
            log_debug("Role 방식으로 폴백 시도")

            # 1단계: q-slack-role → crossaccount 역할 assume
            log_debug("1단계: crossaccount 역할 assume")
            sts_client = boto3.client('sts')
            crossaccount_role = sts_client.assume_role(
                RoleArn="arn:aws:iam::370662402529:role/crossaccount",
                RoleSessionName="SlackBot-CrossAccount",
                ExternalId="saltwarec0rp"
            )

            # 2단계: crossaccount 자격증명으로 target account assume
            log_debug("2단계: crossaccount 자격증명으로 target account assume")
            crossaccount_session = boto3.Session(
                aws_access_key_id=crossaccount_role['Credentials']['AccessKeyId'],
                aws_secret_access_key=crossaccount_role['Credentials']['SecretAccessKey'],
                aws_session_token=crossaccount_role['Credentials']['SessionToken']
            )
            crossaccount_sts = crossaccount_session.client('sts')

            role_arn = f"arn:aws:iam::{account_id}:role/SaltwareCrossAccount"
            log_debug(f"Role 방식 Assume role: {role_arn} (with ExternalId)")
            assumed_role = crossaccount_sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"SlackBot-{account_id}",
                ExternalId="saltwarec0rp"
            )
            credentials = assumed_role['Credentials']
            log_debug("Role 방식 Cross-account 세션 생성 성공")
            
            # 생성된 자격증명 캐시에 저장
            creds_dict = {
                'AWS_ACCESS_KEY_ID': credentials['AccessKeyId'],
                'AWS_SECRET_ACCESS_KEY': credentials['SecretAccessKey'],
                'AWS_SESSION_TOKEN': credentials['SessionToken']
            }
            cache_credentials(account_id, creds_dict)
            
            return creds_dict
        except Exception as role_error:
            log_error(f"Role 방식도 실패: {role_error}")

    return None


def validate_account_id(account_id: str) -> bool:
    """
    AWS 계정 ID 유효성 검사
    
    Args:
        account_id: 검사할 계정 ID
        
    Returns:
        bool: 유효한 계정 ID 여부
    """
    if not account_id:
        return False
    
    # 12자리 숫자인지 확인
    if not re.match(r'^\d{12}$', account_id):
        return False
    
    return True
