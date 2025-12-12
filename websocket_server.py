#!/usr/bin/env python3
"""
Saltware AWS Assistant - WebSocket Server
기존 Slack bot 로직을 WebSocket으로 포팅한 서버
"""

import os
import json
import subprocess
import threading
import re
import boto3
from datetime import datetime, timedelta, date
from flask import Flask, request
from flask_socketio import SocketIO, emit
import requests
import tempfile
import shutil

# Flask 앱 및 SocketIO 설정
app = Flask(__name__)
app.config['SECRET_KEY'] = 'saltware-aws-assistant-secret'

# CORS 설정 강화
from flask_cors import CORS
CORS(app, 
     origins=["http://localhost:8080", "http://127.0.0.1:8080", "*"],
     allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
     supports_credentials=True)

socketio = SocketIO(
    app, 
    cors_allowed_origins=["http://localhost:8080", "http://127.0.0.1:8080", "*"], 
    logger=True, 
    engineio_logger=True, 
    path='/zendesk/socket.io',
    ping_timeout=60,  # ping 타임아웃 1분으로 조정
    ping_interval=25,  # ping 간격 25초로 조정
    allow_upgrades=False,  # WebSocket 업그레이드 비활성화
    transports=['polling'],  # polling만 사용
    async_mode='threading'  # 비동기 모드 명시
)

# 처리 중인 질문 추적
processing_questions = set()

# 활성 세션 추적
active_sessions = set()

# 현재 진행 상태 추적 (질문별)
current_progress = {}

# /tmp/reports 디렉터리 생성
os.makedirs('/tmp/reports', exist_ok=True)

# WebSocket 이벤트 핸들러
@socketio.on('connect', namespace='/zendesk')
def handle_connect():
    """클라이언트 연결 처리"""
    print(f"[DEBUG] 클라이언트 연결됨: {request.sid}", flush=True)
    active_sessions.add(request.sid)
    emit('response', {'data': '연결되었습니다'})

@socketio.on('disconnect', namespace='/zendesk')
def handle_disconnect():
    """클라이언트 연결 해제 처리"""
    print(f"[DEBUG] 클라이언트 연결 해제: {request.sid}", flush=True)
    active_sessions.discard(request.sid)
    current_progress.pop(request.sid, None)

@socketio.on('message', namespace='/zendesk')
def handle_message(data):
    """메시지 수신 처리"""
    print(f"[DEBUG] 메시지 수신: {data}", flush=True)
    emit('response', {'data': '메시지를 받았습니다'})

def convert_datetime_to_json_serializable(obj):
    """
    datetime 객체를 JSON 직렬화 가능한 형식으로 변환하는 재귀 함수
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_datetime_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        return [convert_datetime_to_json_serializable(item) for item in obj]
    else:
        return obj

def get_crossaccount_credentials():
    """Parameter Store에서 Cross-account 자격증명 가져오기"""
    try:
        print(f"[DEBUG] Parameter Store에서 cross-account 자격증명 로드 시도", flush=True)
        ssm_client = boto3.client('ssm', region_name='ap-northeast-2')
        access_key = ssm_client.get_parameter(Name='/access-key/crossaccount', WithDecryption=True)['Parameter']['Value']
        secret_key = ssm_client.get_parameter(Name='/secret-key/crossaccount', WithDecryption=True)['Parameter']['Value']
        print(f"[DEBUG] Cross-account 자격증명 로드 성공", flush=True)
        return access_key, secret_key
    except Exception as e:
        print(f"[ERROR] Cross-account 자격증명 로드 실패: {e}", flush=True)
        return None, None

def extract_account_id(text):
    """텍스트에서 계정 ID 추출"""
    account_pattern = r'\d{12}'
    match = re.search(account_pattern, text)
    result = match.group() if match else None
    print(f"[DEBUG] 계정 ID 추출 시도: '{text}' -> '{result}'", flush=True)
    return result

def get_crossaccount_session(account_id):
    """Cross-account 세션 생성"""
    try:
        print(f"[DEBUG] 계정 {account_id}에 대한 cross-account 세션 생성 시도", flush=True)
        access_key, secret_key = get_crossaccount_credentials()
        if access_key and secret_key:
            print(f"[DEBUG] Cross-account 자격증명 확보, STS assume role 시도", flush=True)
            crossaccount_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
            sts_client = crossaccount_session.client('sts')
            role_arn = f"arn:aws:iam::{account_id}:role/SaltwareCrossAccount"
            print(f"[DEBUG] Assume role: {role_arn}", flush=True)
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"ZendeskBot-{account_id}"
            )
            credentials = assumed_role['Credentials']
            print(f"[DEBUG] Cross-account 세션 생성 성공", flush=True)
            return {
                'AWS_ACCESS_KEY_ID': credentials['AccessKeyId'],
                'AWS_SECRET_ACCESS_KEY': credentials['SecretAccessKey'],
                'AWS_SESSION_TOKEN': credentials['SessionToken']
            }
        else:
            print(f"[ERROR] Cross-account 자격증명을 가져올 수 없음", flush=True)
    except Exception as user_error:
        print(f"[DEBUG] User 방식 실패: {user_error}", flush=True)

        # Role 방식 폴백 시도 (2단계)
        try:
            print(f"[DEBUG] Role 방식으로 폴백 시도", flush=True)

            # 1단계: q-slack-role → crossaccount 역할 assume
            print(f"[DEBUG] 1단계: crossaccount 역할 assume", flush=True)
            sts_client = boto3.client('sts')
            crossaccount_role = sts_client.assume_role(
                RoleArn="arn:aws:iam::370662402529:role/crossaccount",
                RoleSessionName="WebSocketBot-CrossAccount",
                ExternalId="saltwarec0rp"
            )

            # 2단계: crossaccount 자격증명으로 target account assume
            print(f"[DEBUG] 2단계: crossaccount 자격증명으로 target account assume", flush=True)
            crossaccount_session = boto3.Session(
                aws_access_key_id=crossaccount_role['Credentials']['AccessKeyId'],
                aws_secret_access_key=crossaccount_role['Credentials']['SecretAccessKey'],
                aws_session_token=crossaccount_role['Credentials']['SessionToken']
            )
            crossaccount_sts = crossaccount_session.client('sts')

            role_arn = f"arn:aws:iam::{account_id}:role/SaltwareCrossAccount"
            print(f"[DEBUG] Role 방식 Assume role: {role_arn} (with ExternalId)", flush=True)
            assumed_role = crossaccount_sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"ZendeskBot-{account_id}",
                ExternalId="saltwarec0rp"
            )
            credentials = assumed_role['Credentials']
            print(f"[DEBUG] Role 방식 Cross-account 세션 생성 성공", flush=True)
            return {
                'AWS_ACCESS_KEY_ID': credentials['AccessKeyId'],
                'AWS_SECRET_ACCESS_KEY': credentials['SecretAccessKey'],
                'AWS_SESSION_TOKEN': credentials['SessionToken']
            }
        except Exception as role_error:
            print(f"[ERROR] Role 방식도 실패: {role_error}", flush=True)

    return None

def analyze_question_type(question):
    """질문 유형 분석 및 적절한 컨텍스트 파일 경로 반환"""
    question_lower = question.lower()
    print(f"[DEBUG] 질문 타입 분석 시작: '{question_lower}'", flush=True)

    # 우선순위 1: Service Screener 관련 (가장 우선)
    screener_keywords = ['screener', '스크리너', '스캔', 'scan', '점검', '검사', '진단']
    if any(keyword in question_lower for keyword in screener_keywords):
        print(f"[DEBUG] 질문 타입: screener", flush=True)
        return 'screener', None

    # 우선순위 2: 보고서 생성 관련 (가장 구체적)
    report_keywords = ['보고서', 'report', '리포트', '감사보고서', '보안보고서']
    if any(keyword in question_lower for keyword in report_keywords):
        return 'report', 'reference_contexts/security_report.md'

    # 우선순위 3: CloudTrail/감사 관련 (활동 추적)
    cloudtrail_keywords = ['cloudtrail', '추적', '누가', '언제', '활동', '이벤트', '로그인', '이력', '히스토리', 'history']
    cloudtrail_phrases = ['감사', '종료했', '삭제했', '생성했', '변경했', '수정했', '수정한', '변경한', '삭제한', '생성한', '종료한',
                          '수정사항', '변경사항', '삭제사항', '생성사항', '바꿨', '지웠', '만들었']
    if (any(keyword in question_lower for keyword in cloudtrail_keywords) or
        any(phrase in question_lower for phrase in cloudtrail_phrases)):
        return 'cloudtrail', 'reference_contexts/cloudtrail_mcp.md'

    # 우선순위 4: CloudWatch/모니터링 관련
    cloudwatch_keywords = ['cloudwatch', '모니터링', '알람', '메트릭', 'dashboard', '성능', '로그 그룹', '지표', 'metric', 'cpu', '메모리', '디스크']
    if any(keyword in question_lower for keyword in cloudwatch_keywords):
        return 'cloudwatch', 'reference_contexts/cloudwatch_mcp.md'

    # 우선순위 5: 일반 AWS 질문
    print(f"[DEBUG] 질문 타입: general", flush=True)
    return 'general', 'reference_contexts/general_aws.md'

def load_context_file(context_path):
    """컨텍스트 파일 로드"""
    try:
        with open(context_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"[DEBUG] 컨텍스트 파일 로드 성공: {context_path}", flush=True)
        return content
    except Exception as e:
        print(f"[DEBUG] 컨텍스트 파일 로드 실패: {context_path} - {e}", flush=True)
        return ""

def simple_clean_output(text):
    """일반 질문 응답 정리 - 도구 사용 내역 제거, 결과만 추출 (Slack bot과 동일)"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)

    # 도구 사용 및 명령어 실행 관련 라인 제거 (Slack bot과 동일한 패턴)
    tool_patterns = [
        r'🛠️.*',
        r'●\s+.*',
        r'✓\s+.*',
        r'↳\s+Purpose:.*',
        r'Service name:.*',
        r'Operation name:.*',
        r'Parameters:.*',
        r'Region:.*',
        r'Label:.*',
        r'⋮.*',
        r'.*Using tool:.*',
        r'.*Running.*command:.*',
        r'.*Completed in.*',
        r'.*Execution.*',
        r'.*Reading (file|directory):.*',
        r'.*Successfully read.*',
        r'.*I will run the following.*',
        r'^>.*',
        r'- Name:.*',
        r'- MaxItems:.*',
        r'- Bucket:.*',
        r'- UserName:.*',
        r'\+\s+\d+:.*',
        r'^\s*\d+:.*',
        r'^total \d+',
        r'^drwx.*',
        r'^-rw.*',
        r'^lrwx.*',
        r'^/root/.*',
        r'.*which:.*',
        r'.*pip.*install.*',
        r'.*apt.*update.*',
        r'.*yum.*install.*',
        r'.*git clone.*',
        r'.*bash: line.*',
        r'.*command not found.*',
        r'.*Package.*is already installed.*',
        r'.*Dependencies resolved.*',
        r'.*Transaction Summary.*',
        r'.*Downloading Packages.*',
        r'.*Running transaction.*',
        r'.*Installing.*:.*',
        r'.*Verifying.*:.*',
        r'.*Complete!.*',
        r'.*ERROR: Could not find.*',
        r'.*WARNING:.*pip version.*',
        r'.*Last metadata expiration.*',
        r'.*Nothing to do.*',
        r'.*fatal: destination path.*',
        r'.*cd /root.*',
        r'.*ls -la.*',
        r'.*A newer release.*',
        r'.*Available Versions.*',
        r'.*Run the following command.*',
        r'.*dnf upgrade.*',
        r'.*Release notes.*',
        r'.*Installed:.*',
        r'.*Total download size:.*',
        r'.*Installed size:.*',
        r'.*MB/s.*',
        r'.*kB.*00:00.*',
        r'.*Transaction check.*',
        r'.*Transaction test.*',
        r'.*Preparing.*:.*'
    ]

    lines = clean_text.split('\n')
    filtered_lines = []

    for line in lines:
        stripped = line.strip()
        
        # 불필요한 도구 실행 패턴 제거
        skip_line = False
        for pattern in tool_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break

        # 패턴에 매칭되지 않고 내용이 있는 줄만 유지
        if not skip_line and stripped:
            filtered_lines.append(stripped)

    # 결과 정리
    result = '\n'.join(filtered_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # 월간 보고서 로컬 파일 경로를 웹 URL로 변환 (Slack bot과 동일한 로직)
    result = convert_local_paths_to_urls(result)

    return result.strip() if result.strip() else "응답을 처리할 수 없습니다."

def convert_local_paths_to_urls(text):
    """로컬 파일 경로를 웹 접근 가능한 URL로 변환"""
    try:
        # /tmp/reports/ 경로를 웹 URL로 변환
        # 패턴: /tmp/reports/filename.html -> http://domain/reports/filename.html
        url_pattern = r'/tmp/reports/([^/\s]+\.html)'
        base_url = 'http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports'
        
        def replace_path(match):
            filename = match.group(1)
            web_url = f"{base_url}/{filename}"
            print(f"[DEBUG] 로컬 경로 변환: {match.group(0)} -> {web_url}", flush=True)
            return web_url
        
        converted_text = re.sub(url_pattern, replace_path, text)
        
        # 변환이 발생했는지 확인
        if converted_text != text:
            print(f"[DEBUG] 월간 보고서 URL 변환 완료", flush=True)
        
        return converted_text
        
    except Exception as e:
        print(f"[ERROR] URL 변환 중 오류: {e}", flush=True)
        return text

def collect_raw_security_data(account_id, start_date_str, end_date_str, region='ap-northeast-2', credentials=None):
    """
    boto3를 사용하여 AWS raw 보안 데이터를 수집 (Q CLI 분석용)
    
    Args:
        account_id (str): AWS 계정 ID
        start_date_str (str): 시작 날짜 (YYYY-MM-DD) - UTC+9 기준
        end_date_str (str): 종료 날짜 (YYYY-MM-DD) - UTC+9 기준
        region (str): AWS 리전
        credentials (dict): AWS 자격증명 (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    
    Returns:
        dict: Raw 보안 데이터 JSON
    """
    print(f"[DEBUG] ✅ boto3로 raw 데이터 수집 시작: 계정 {account_id}, 리전 {region}", flush=True)
    print(f"[DEBUG] 분석 기간: {start_date_str} ~ {end_date_str} (UTC+9)", flush=True)
    
    # 자격증명 가져오기 (파라미터 우선, 없으면 환경 변수)
    if credentials:
        access_key = credentials.get('AWS_ACCESS_KEY_ID')
        secret_key = credentials.get('AWS_SECRET_ACCESS_KEY')
        session_token = credentials.get('AWS_SESSION_TOKEN')
    else:
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        session_token = os.environ.get('AWS_SESSION_TOKEN')
    
    print(f"[DEBUG] 자격증명 확인: ACCESS_KEY={access_key[:20] if access_key else 'None'}..., SESSION_TOKEN={'있음' if session_token else '없음'}", flush=True)
    
    # boto3 세션 생성 (환경 변수의 임시 자격증명 사용)
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region
    )
    
    # boto3 클라이언트 생성
    ec2 = session.client('ec2', region_name=region)
    s3 = session.client('s3', region_name=region)
    iam = session.client('iam', region_name=region)
    support = session.client('support', region_name='us-east-1')  # TA는 us-east-1만 지원
    cloudtrail = session.client('cloudtrail', region_name=region)
    cloudwatch = session.client('cloudwatch', region_name=region)
    
    print(f"[DEBUG] boto3 클라이언트 생성 완료 (임시 자격증명 사용)", flush=True)
    
    report_data = {
        "metadata": {
            "account_id": account_id,
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "period_start": start_date_str,
            "period_end": end_date_str,
            "region": region
        },
        "resources": {},
        "iam_security": {},
        "security_groups": {},
        "encryption": {},
        "trusted_advisor": {},
        "cloudtrail_events": {},
        "cloudwatch": {},
        "recommendations": []
    }
    
    # 1. EC2 인스턴스 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 EC2 인스턴스 수집 중...", flush=True)
    try:
        ec2_response = ec2.describe_instances()
        
        # Raw 인스턴스 데이터 추출 (모든 필드 포함)
        instances_raw = []
        for reservation in ec2_response['Reservations']:
            for instance in reservation['Instances']:
                instances_raw.append(instance)
        
        # 요약 정보 계산
        total = len(instances_raw)
        running = sum(1 for i in instances_raw if i['State']['Name'] == 'running')
        stopped = sum(1 for i in instances_raw if i['State']['Name'] == 'stopped')
        
        report_data['resources']['ec2'] = {
            "summary": {
                "total": total,
                "running": running,
                "stopped": stopped
            },
            "instances": instances_raw  # Raw 데이터 (datetime 변환은 나중에 일괄 처리)
        }
        print(f"[DEBUG] ✅ EC2 수집 완료: {total}개 (running: {running}, stopped: {stopped})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ EC2 수집 실패: {e}", flush=True)
        report_data['resources']['ec2'] = {"summary": {"total": 0, "running": 0, "stopped": 0}, "instances": []}
    
    # 2. S3 버킷 수집 (Raw 데이터 + 추가 정보)
    print(f"[DEBUG] 📦 S3 버킷 수집 중...", flush=True)
    try:
        s3_response = s3.list_buckets()
        buckets_raw = []
        
        for bucket in s3_response['Buckets']:
            bucket_name = bucket['Name']
            bucket_data = bucket.copy()  # 기본 정보 복사
            
            try:
                # 버킷 리전 확인
                location = s3.get_bucket_location(Bucket=bucket_name)
                bucket_data['Location'] = location.get('LocationConstraint') or 'us-east-1'
                
                # 암호화 확인
                try:
                    encryption_response = s3.get_bucket_encryption(Bucket=bucket_name)
                    bucket_data['Encryption'] = encryption_response.get('ServerSideEncryptionConfiguration')
                except:
                    bucket_data['Encryption'] = None
                
                # 버저닝 확인
                try:
                    versioning_response = s3.get_bucket_versioning(Bucket=bucket_name)
                    bucket_data['Versioning'] = versioning_response
                except:
                    bucket_data['Versioning'] = None
                
                # 퍼블릭 액세스 블록 확인
                try:
                    public_access_response = s3.get_public_access_block(Bucket=bucket_name)
                    bucket_data['PublicAccessBlock'] = public_access_response.get('PublicAccessBlockConfiguration')
                except:
                    bucket_data['PublicAccessBlock'] = None  # 블록 설정 없음 = 퍼블릭 가능
                
                buckets_raw.append(bucket_data)
            except Exception as e:
                print(f"[DEBUG] 버킷 {bucket_name} 상세 정보 수집 실패: {e}", flush=True)
                buckets_raw.append(bucket_data)  # 기본 정보라도 저장
        
        # 요약 정보 계산
        encrypted_count = sum(1 for b in buckets_raw if b.get('Encryption') is not None)
        public_count = sum(1 for b in buckets_raw if b.get('PublicAccessBlock') is None)
        
        report_data['resources']['s3'] = {
            "summary": {
                "total": len(buckets_raw),
                "encrypted": encrypted_count,
                "public": public_count
            },
            "buckets": buckets_raw  # Raw 데이터 (모든 버킷, 모든 필드)
        }
        print(f"[DEBUG] ✅ S3 수집 완료: {len(buckets_raw)}개 (암호화: {encrypted_count}, 퍼블릭: {public_count})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ S3 수집 실패: {e}", flush=True)
        report_data['resources']['s3'] = {"summary": {"total": 0, "encrypted": 0, "public": 0}, "buckets": []}
    
    # 3. Lambda 함수 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 Lambda 함수 수집 중...", flush=True)
    try:
        lambda_client = session.client('lambda', region_name=region)
        lambda_response = lambda_client.list_functions()
        functions_raw = lambda_response.get('Functions', [])
        
        report_data['resources']['lambda'] = {
            "summary": {
                "total": len(functions_raw)
            },
            "functions": functions_raw  # Raw 데이터 (모든 필드 포함)
        }
        print(f"[DEBUG] ✅ Lambda 수집 완료: {len(functions_raw)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ Lambda 수집 실패: {e}", flush=True)
        report_data['resources']['lambda'] = {"summary": {"total": 0}, "functions": []}
    
    # 4. RDS 인스턴스 수집 (Raw 데이터 저장 - Multi-AZ, 엔진, 백업 등 모든 정보 포함)
    print(f"[DEBUG] 📦 RDS 인스턴스 수집 중...", flush=True)
    try:
        rds_client = session.client('rds', region_name=region)
        rds_response = rds_client.describe_db_instances()
        db_instances_raw = rds_response.get('DBInstances', [])
        
        report_data['resources']['rds'] = {
            "summary": {
                "total": len(db_instances_raw)
            },
            "instances": db_instances_raw  # Raw 데이터 (Multi-AZ, Engine, BackupRetentionPeriod 등 모두 포함)
        }
        print(f"[DEBUG] ✅ RDS 수집 완료: {len(db_instances_raw)}개", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ RDS 수집 실패: {e}", flush=True)
        report_data['resources']['rds'] = {"summary": {"total": 0}, "instances": []}
    
    # 5. IAM 사용자 수집
    print(f"[DEBUG] 📦 IAM 사용자 수집 중...", flush=True)
    try:
        iam_response = iam.list_users()
        users = []
        issues = []
        
        for user in iam_response['Users']:
            username = user['UserName']
            
            # MFA 확인
            mfa_devices = iam.list_mfa_devices(UserName=username)
            has_mfa = len(mfa_devices['MFADevices']) > 0
            
            # 액세스 키 확인
            access_keys = iam.list_access_keys(UserName=username)
            
            users.append({
                "username": username,
                "mfa": has_mfa,
                "access_keys": access_keys['AccessKeyMetadata'],
                "policies": [],
                "groups": []
            })
            
            # MFA 미설정 이슈
            if not has_mfa:
                issues.append({
                    "severity": "critical",
                    "type": "no_mfa",
                    "user": username,
                    "description": "MFA 미설정"
                })
        
        report_data['iam_security'] = {
            "users": {
                "total": len(users),
                "mfa_enabled": sum(1 for u in users if u['mfa']),
                "details": users
            },
            "issues": issues
        }
        print(f"[DEBUG] ✅ IAM 수집 완료: {len(users)}명 (MFA 활성화: {sum(1 for u in users if u['mfa'])}명)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ IAM 수집 실패: {e}", flush=True)
        report_data['iam_security'] = {"users": {"total": 0, "mfa_enabled": 0, "details": []}, "issues": []}
    
    # 6. 보안 그룹 수집
    print(f"[DEBUG] 📦 보안 그룹 수집 중...", flush=True)
    try:
        sg_response = ec2.describe_security_groups()
        risky_sgs = []
        total_risky_rules = 0
        
        for sg in sg_response['SecurityGroups']:
            risky_rules = []
            for rule in sg.get('IpPermissions', []):
                for ip_range in rule.get('IpRanges', []):
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        port = rule.get('FromPort', 'all')
                        risky_rules.append({
                            "port": port,
                            "protocol": rule.get('IpProtocol', 'all'),
                            "source": "0.0.0.0/0",
                            "risk_level": "high" if port in [22, 3389, 3306, 5432] else "medium",
                            "description": f"포트 {port} 전체 오픈"
                        })
            
            if risky_rules:
                risky_sgs.append({
                    "id": sg['GroupId'],
                    "name": sg['GroupName'],
                    "vpc": sg.get('VpcId', 'N/A'),
                    "risky_rules": risky_rules
                })
                total_risky_rules += len(risky_rules)
        
        report_data['security_groups'] = {
            "total": len(sg_response['SecurityGroups']),
            "risky": total_risky_rules,
            "details": risky_sgs[:5]  # 처음 5개만 표시
        }
        print(f"[DEBUG] ✅ 보안 그룹 수집 완료: {len(sg_response['SecurityGroups'])}개 (위험 규칙: {total_risky_rules}개)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ 보안 그룹 수집 실패: {e}", flush=True)
        report_data['security_groups'] = {"total": 0, "risky": 0, "details": []}
    
    # 7. 암호화 상태 수집
    print(f"[DEBUG] 📦 암호화 상태 수집 중...", flush=True)
    try:
        volumes_response = ec2.describe_volumes()
        volumes = volumes_response['Volumes']
        encrypted_volumes = [v for v in volumes if v.get('Encrypted', False)]
        unencrypted_volumes = [v['VolumeId'] for v in volumes if not v.get('Encrypted', False)]
        
        # S3, RDS 요약 정보 가져오기 (새 구조 반영)
        s3_total = report_data['resources']['s3']['summary']['total']
        s3_encrypted = report_data['resources']['s3']['summary']['encrypted']
        rds_total = report_data['resources']['rds']['summary']['total']
        
        # RDS 암호화 상태 계산
        rds_instances = report_data['resources']['rds'].get('instances', [])
        rds_encrypted = sum(1 for instance in rds_instances if instance.get('StorageEncrypted', False))
        rds_encrypted_rate = rds_encrypted / rds_total if rds_total > 0 else 0.0
        
        report_data['encryption'] = {
            "ebs": {
                "total": len(volumes),
                "encrypted": len(encrypted_volumes),
                "unencrypted_volumes": unencrypted_volumes[:16]  # 처음 16개만
            },
            "s3": {
                "total": s3_total,
                "encrypted": s3_encrypted,
                "encrypted_rate": s3_encrypted / s3_total if s3_total > 0 else 0.0
            },
            "rds": {
                "total": rds_total,
                "encrypted": rds_encrypted,
                "encrypted_rate": rds_encrypted_rate
            }
        }
        print(f"[DEBUG] ✅ 암호화 수집 완료: EBS {len(encrypted_volumes)}/{len(volumes)} 암호화됨", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ 암호화 상태 수집 실패: {e}", flush=True)
        report_data['encryption'] = {"ebs": {"total": 0, "encrypted": 0, "unencrypted_volumes": []}, "s3": {"total": 0, "encrypted": 0, "encrypted_rate": 0.0}, "rds": {"total": 0, "encrypted": 0, "encrypted_rate": 0.0}}
    
    # 8. Trusted Advisor 수집 (가장 중요!)
    print(f"[DEBUG] 🔍 Trusted Advisor 수집 중... (이게 핵심!)", flush=True)
    try:
        # TA 체크 목록 가져오기
        ta_checks_response = support.describe_trusted_advisor_checks(language='en')
        checks = ta_checks_response['checks']
        print(f"[DEBUG] TA 전체 체크 개수: {len(checks)}개", flush=True)
        
        ta_results = []
        for check in checks:
            check_id = check['id']
            check_name = check['name']
            check_category = check['category']
            
            try:
                # 각 체크 결과 가져오기
                result_response = support.describe_trusted_advisor_check_result(checkId=check_id, language='en')
                result = result_response['result']
                
                status = result['status']
                flagged_resources = len(result.get('flaggedResources', []))
                
                # 문제가 있는 체크만 포함
                if status in ['warning', 'error'] and flagged_resources > 0:
                    # 한글 번역
                    category_kr = {
                        'security': '보안',
                        'cost_optimizing': '비용 최적화',
                        'performance': '성능',
                        'fault_tolerance': '내결함성',
                        'service_limits': '서비스 한도'
                    }.get(check_category, check_category)
                    
                    ta_results.append({
                        "category": category_kr,
                        "name": check_name,  # 영문 그대로 (한글 번역은 템플릿에서)
                        "status": status,
                        "flagged_resources": flagged_resources,
                        "details": []  # 상세 정보는 생략 (개수만 표시)
                    })
                    print(f"[DEBUG] TA 이슈 발견: [{category_kr}] {check_name} - {flagged_resources}개", flush=True)
            except Exception as e:
                print(f"[DEBUG] TA 체크 {check_name} 결과 수집 실패: {e}", flush=True)
        
        report_data['trusted_advisor'] = {
            "available": True,
            "checks": ta_results
        }
        print(f"[DEBUG] ✅ Trusted Advisor 수집 완료: {len(ta_results)}개 이슈 발견!", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ Trusted Advisor 수집 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        report_data['trusted_advisor'] = {"available": False, "checks": []}
    
    # 9. CloudTrail 이벤트 수집 (정확한 기간, UTC+9)
    print(f"[DEBUG] 📦 CloudTrail 이벤트 수집 중 ({start_date_str} ~ {end_date_str})...", flush=True)
    try:
        from datetime import datetime as dt, timezone
        
        # UTC+9 (한국 시간) 적용
        kst = timezone(timedelta(hours=9))
        
        # 시작일 00:00:00 KST → UTC 변환
        start_time_kst = dt.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, tzinfo=kst)
        start_time_utc = start_time_kst.astimezone(timezone.utc)
        
        # 종료일 23:59:59 KST → UTC 변환
        end_time_kst = dt.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=kst)
        end_time_utc = end_time_kst.astimezone(timezone.utc)
        
        print(f"[DEBUG] CloudTrail 조회 기간 (UTC): {start_time_utc} ~ {end_time_utc}", flush=True)
        
        # 보안 관점에서 중요한 이벤트 목록 (우선순위 순)
        critical_events = {
            # 🔴 Critical - 데이터 손실 및 서비스 중단
            'DeleteBucket': {'severity': 'critical', 'category': 'data_loss', 'description': 'S3 버킷 삭제'},
            'DeleteDBInstance': {'severity': 'critical', 'category': 'data_loss', 'description': 'RDS 인스턴스 삭제'},
            'TerminateInstances': {'severity': 'critical', 'category': 'service_disruption', 'description': 'EC2 인스턴스 종료'},
            'DeleteUser': {'severity': 'critical', 'category': 'account_security', 'description': 'IAM 사용자 삭제'},
            'DeleteAccessKey': {'severity': 'critical', 'category': 'account_security', 'description': 'IAM 액세스 키 삭제'},
            
            # 🟡 High - 보안 설정 변경
            'PutBucketPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'S3 버킷 정책 변경'},
            'AuthorizeSecurityGroupIngress': {'severity': 'high', 'category': 'network_security', 'description': '보안 그룹 인바운드 규칙 추가'},
            'CreateAccessKey': {'severity': 'high', 'category': 'account_security', 'description': '새 액세스 키 생성'},
            'PutUserPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'IAM 사용자 정책 변경'},
            'AttachUserPolicy': {'severity': 'high', 'category': 'permission_change', 'description': 'IAM 사용자 정책 연결'},
        }
        
        # 각 중요 이벤트별로 수집
        critical_events_data = {}
        total_collected = 0
        
        for event_name, event_info in critical_events.items():
            print(f"[DEBUG] 🔍 {event_name} 이벤트 조회 중...", flush=True)
            
            try:
                # 해당 이벤트만 조회 (최대 50개)
                events_response = cloudtrail.lookup_events(
                    StartTime=start_time_utc,
                    EndTime=end_time_utc,
                    LookupAttributes=[
                        {'AttributeKey': 'EventName', 'AttributeValue': event_name}
                    ],
                    MaxResults=50
                )
                
                events = events_response.get('Events', [])
                
                if events:
                    critical_events_data[event_name] = {
                        'severity': event_info['severity'],
                        'category': event_info['category'],
                        'description': event_info['description'],
                        'count': len(events),
                        'events': events  # Raw 이벤트 데이터
                    }
                    total_collected += len(events)
                    print(f"[DEBUG] ✅ {event_name}: {len(events)}개 발견", flush=True)
                else:
                    # 이벤트가 없어도 기록 (0건)
                    critical_events_data[event_name] = {
                        'severity': event_info['severity'],
                        'category': event_info['category'],
                        'description': event_info['description'],
                        'count': 0,
                        'events': []
                    }
                    
            except Exception as e:
                print(f"[DEBUG] ⚠️ {event_name} 조회 실패: {e}", flush=True)
                critical_events_data[event_name] = {
                    'severity': event_info['severity'],
                    'category': event_info['category'],
                    'description': event_info['description'],
                    'count': 0,
                    'events': [],
                    'error': str(e)
                }
        
        period_days = (end_time_kst - start_time_kst).days + 1
        
        report_data['cloudtrail_events'] = {
            "summary": {
                "period_days": period_days,
                "total_critical_events": total_collected,
                "monitored_event_types": len(critical_events)
            },
            "critical_events": critical_events_data  # 이벤트 타입별로 구조화된 데이터
        }
        print(f"[DEBUG] ✅ CloudTrail 중요 이벤트 수집 완료: {total_collected}개 ({period_days}일간)", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudTrail 수집 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        report_data['cloudtrail_events'] = {"summary": {"period_days": 30, "total_critical_events": 0, "monitored_event_types": 0}, "critical_events": {}}
    
    # 10. CloudWatch 알람 수집 (Raw 데이터 저장)
    print(f"[DEBUG] 📦 CloudWatch 알람 수집 중...", flush=True)
    try:
        alarms_response = cloudwatch.describe_alarms()
        alarms_raw = alarms_response['MetricAlarms']
        
        # 요약 정보 계산
        total = len(alarms_raw)
        in_alarm = sum(1 for a in alarms_raw if a['StateValue'] == 'ALARM')
        ok = sum(1 for a in alarms_raw if a['StateValue'] == 'OK')
        insufficient_data = sum(1 for a in alarms_raw if a['StateValue'] == 'INSUFFICIENT_DATA')
        
        report_data['cloudwatch'] = {
            "summary": {
                "total": total,
                "in_alarm": in_alarm,
                "ok": ok,
                "insufficient_data": insufficient_data
            },
            "alarms": alarms_raw  # Raw 데이터 (AlarmName, StateValue, MetricName, Threshold 등 모든 필드)
        }
        print(f"[DEBUG] ✅ CloudWatch 수집 완료: {total}개 알람 (ALARM: {in_alarm}, OK: {ok})", flush=True)
    except Exception as e:
        print(f"[ERROR] ❌ CloudWatch 수집 실패: {e}", flush=True)
        report_data['cloudwatch'] = {"summary": {"total": 0, "in_alarm": 0, "ok": 0, "insufficient_data": 0}, "alarms": []}
    
    # 11. 권장사항 생성
    print(f"[DEBUG] 📝 권장사항 생성 중...", flush=True)
    recommendations = []
    
    # MFA 권장사항
    if report_data['iam_security']['users']['mfa_enabled'] < report_data['iam_security']['users']['total']:
        recommendations.append({
            "priority": "critical",
            "category": "security",
            "title": "모든 IAM 사용자에 MFA 설정 필요",
            "description": f"{report_data['iam_security']['users']['total'] - report_data['iam_security']['users']['mfa_enabled']}명의 IAM 사용자가 MFA를 설정하지 않았습니다.",
            "affected_resources": [u['username'] for u in report_data['iam_security']['users']['details'] if not u['mfa']],
            "action": "모든 IAM 사용자에 대해 MFA를 활성화하고 정기적으로 검토하세요."
        })
    
    # 보안 그룹 권장사항
    if report_data['security_groups']['risky'] > 0:
        recommendations.append({
            "priority": "critical",
            "category": "security",
            "title": "보안 그룹 규칙 강화 필요",
            "description": f"{report_data['security_groups']['risky']}개의 위험한 보안 그룹 규칙이 발견되었습니다.",
            "affected_resources": [sg['id'] for sg in report_data['security_groups']['details']],
            "action": "보안 그룹 규칙을 검토하고 필요한 IP 범위로만 제한하세요."
        })
    
    # EBS 암호화 권장사항
    if report_data['encryption']['ebs']['total'] > 0 and report_data['encryption']['ebs']['encrypted'] < report_data['encryption']['ebs']['total']:
        recommendations.append({
            "priority": "high",
            "category": "security",
            "title": "EBS 볼륨 암호화 활성화",
            "description": f"{report_data['encryption']['ebs']['total'] - report_data['encryption']['ebs']['encrypted']}개의 EBS 볼륨이 암호화되지 않았습니다.",
            "affected_resources": report_data['encryption']['ebs']['unencrypted_volumes'][:5],
            "action": "새로운 EBS 볼륨에 대해 기본 암호화를 활성화하고 기존 볼륨을 암호화된 볼륨으로 마이그레이션하세요."
        })
    
    # S3 암호화 권장사항 (새 구조 반영)
    s3_total = report_data['resources']['s3']['summary']['total']
    s3_encrypted = report_data['resources']['s3']['summary']['encrypted']
    if s3_total > 0 and s3_encrypted < s3_total:
        # 암호화되지 않은 버킷 찾기
        unencrypted_buckets = [b['Name'] for b in report_data['resources']['s3']['buckets'] if b.get('Encryption') is None]
        recommendations.append({
            "priority": "high",
            "category": "security",
            "title": "S3 버킷 암호화 설정",
            "description": f"{s3_total - s3_encrypted}개의 S3 버킷이 암호화되지 않았습니다.",
            "affected_resources": unencrypted_buckets[:5],
            "action": "모든 S3 버킷에 대해 서버 측 암호화(SSE)를 활성화하세요."
        })
    
    report_data['recommendations'] = recommendations
    print(f"[DEBUG] ✅ 권장사항 생성 완료: {len(recommendations)}개", flush=True)
    
    print(f"[DEBUG] 🎉 boto3 데이터 수집 완료! 정확한 데이터를 수집했습니다.", flush=True)
    
    # datetime 객체를 JSON 직렬화 가능한 형식으로 변환
    print(f"[DEBUG] 📝 datetime 객체 변환 중...", flush=True)
    report_data = convert_datetime_to_json_serializable(report_data)
    print(f"[DEBUG] ✅ datetime 변환 완료", flush=True)
    
    return report_data





def generate_ec2_rows(instances):
    """EC2 인스턴스 테이블 행 생성"""
    if not instances:
        return '<tr><td colspan="8" class="no-data">EC2 인스턴스가 없습니다</td></tr>'
    
    rows = []
    for instance in instances:
        name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), instance.get('InstanceId', 'N/A'))
        instance_id = instance.get('InstanceId', 'N/A')
        instance_type = instance.get('InstanceType', 'N/A')
        state = instance.get('State', {}).get('Name', 'N/A')
        public_ip = instance.get('PublicIpAddress', '없음')
        
        # IMDSv2 설정
        metadata_options = instance.get('MetadataOptions', {})
        imdsv2 = metadata_options.get('HttpTokens', 'optional')
        imdsv2_class = 'ok' if imdsv2 == 'required' else 'warning'
        
        # 상세 모니터링
        monitoring = instance.get('Monitoring', {}).get('State', 'disabled')
        monitoring_class = 'ok' if monitoring == 'enabled' else 'warning'
        
        # EBS 삭제 방지
        delete_protection = 'N/A'
        for bdm in instance.get('BlockDeviceMappings', []):
            if bdm.get('Ebs', {}).get('DeleteOnTermination') == False:
                delete_protection = '설정됨'
                break
        else:
            delete_protection = '미설정'
        
        delete_class = 'ok' if delete_protection == '설정됨' else 'warning'
        
        rows.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{instance_id}</td>
            <td>{instance_type}</td>
            <td><span class="badge badge-{'ok' if state == 'running' else 'warning'}">{state}</span></td>
            <td class="{'warning' if public_ip != '없음' else 'ok'}">{public_ip}</td>
            <td class="{imdsv2_class}">{imdsv2}</td>
            <td class="{monitoring_class}">{monitoring}</td>
            <td class="{delete_class}">{delete_protection}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_s3_rows(buckets):
    """S3 버킷 테이블 행 생성"""
    if not buckets:
        return '<tr><td colspan="6" class="no-data">S3 버킷이 없습니다</td></tr>'
    
    rows = []
    for bucket in buckets:
        name = bucket.get('Name', 'N/A')
        location = bucket.get('Location', 'N/A')
        
        # 암호화 설정
        encryption = bucket.get('Encryption', {})
        if encryption.get('Rules'):
            encryption_status = '설정됨'
            encryption_class = 'ok'
        else:
            encryption_status = '미설정'
            encryption_class = 'error'
        
        # 버저닝 설정
        versioning = bucket.get('Versioning', {})
        versioning_status = versioning.get('Status', '미설정')
        versioning_class = 'ok' if versioning_status == 'Enabled' else 'warning'
        
        # 퍼블릭 액세스 차단
        public_access = bucket.get('PublicAccessBlock')
        if public_access and all([
            public_access.get('BlockPublicAcls', False),
            public_access.get('IgnorePublicAcls', False),
            public_access.get('BlockPublicPolicy', False),
            public_access.get('RestrictPublicBuckets', False)
        ]):
            public_status = '차단됨'
            public_class = 'ok'
        else:
            public_status = '미차단'
            public_class = 'error'
        
        creation_date = bucket.get('CreationDate', 'N/A')
        if creation_date != 'N/A':
            creation_date = creation_date.split('T')[0]
        
        rows.append(f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{location}</td>
            <td class="{encryption_class}">{encryption_status}</td>
            <td class="{versioning_class}">{versioning_status}</td>
            <td class="{public_class}">{public_status}</td>
            <td>{creation_date}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_rds_content(instances):
    """RDS 인스턴스 콘텐츠 생성"""
    if not instances:
        return '<div class="no-data">RDS 인스턴스가 없습니다</div>'
    
    rows = []
    for instance in instances:
        db_id = instance.get('DBInstanceIdentifier', 'N/A')
        engine = instance.get('Engine', 'N/A')
        db_class = instance.get('DBInstanceClass', 'N/A')
        multi_az = instance.get('MultiAZ', False)
        encrypted = instance.get('StorageEncrypted', False)
        backup_retention = instance.get('BackupRetentionPeriod', 0)
        deletion_protection = instance.get('DeletionProtection', False)
        public_access = instance.get('PubliclyAccessible', False)
        status = instance.get('DBInstanceStatus', 'N/A')
        
        rows.append(f"""
        <tr>
            <td><strong>{db_id}</strong></td>
            <td>{engine}</td>
            <td>{db_class}</td>
            <td class="{'ok' if multi_az else 'error'}">{'예' if multi_az else '아니오'}</td>
            <td class="{'ok' if encrypted else 'error'}">{'예' if encrypted else '아니오'}</td>
            <td class="{'ok' if backup_retention >= 30 else 'warning' if backup_retention >= 7 else 'error'}">{backup_retention}일</td>
            <td class="{'ok' if deletion_protection else 'warning'}">{'예' if deletion_protection else '아니오'}</td>
            <td class="{'error' if public_access else 'ok'}">{'예' if public_access else '아니오'}</td>
            <td><span class="badge badge-{'ok' if status == 'available' else 'warning'}">{status}</span></td>
        </tr>
        """)
    
    table = f"""
    <table>
        <thead>
            <tr>
                <th>DB 식별자</th>
                <th>엔진</th>
                <th>타입</th>
                <th>Multi-AZ</th>
                <th>암호화</th>
                <th>백업 보관</th>
                <th>삭제 방지</th>
                <th>퍼블릭 액세스</th>
                <th>상태</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    
    return table

def generate_lambda_content(functions):
    """Lambda 함수 콘텐츠 생성"""
    if not functions:
        return '<div class="no-data">Lambda 함수가 없습니다</div>'
    
    rows = []
    for func in functions:
        func_name = func.get('FunctionName', 'N/A')
        runtime = func.get('Runtime', 'N/A')
        memory = func.get('MemorySize', 'N/A')
        timeout = func.get('Timeout', 'N/A')
        
        rows.append(f"""
        <tr>
            <td><strong>{func_name}</strong></td>
            <td>{runtime}</td>
            <td>{memory}MB</td>
            <td>{timeout}s</td>
        </tr>
        """)
    
    table = f"""
    <table>
        <thead>
            <tr>
                <th>함수명</th>
                <th>런타임</th>
                <th>메모리</th>
                <th>타임아웃</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    
    return table

def generate_iam_users_rows(users):
    """IAM 사용자 테이블 행 생성"""
    if not users:
        return '<tr><td colspan="5" class="no-data">IAM 사용자가 없습니다</td></tr>'
    
    rows = []
    for user in users:
        username = user.get('username', 'N/A')
        mfa = user.get('mfa', False)
        access_keys = user.get('access_keys', [])
        
        key_count = len(access_keys)
        key_date = 'N/A'
        key_age_class = 'ok'
        
        if access_keys:
            oldest_key = min(access_keys, key=lambda k: k.get('CreateDate', ''))
            key_date = oldest_key.get('CreateDate', 'N/A')
            if key_date != 'N/A':
                key_date = key_date.split('T')[0]
                from datetime import datetime, timedelta
                try:
                    create_date = datetime.strptime(key_date, '%Y-%m-%d')
                    if datetime.now() - create_date > timedelta(days=90):
                        key_age_class = 'warning'
                except:
                    pass
        
        security_issues = []
        if not mfa:
            security_issues.append('MFA 미설정')
        if key_count > 1:
            security_issues.append('다중 액세스 키')
        if key_age_class == 'warning':
            security_issues.append('오래된 키')
        
        security_status = ', '.join(security_issues) if security_issues else '양호'
        security_class = 'error' if security_issues else 'ok'
        
        rows.append(f"""
        <tr>
            <td><strong>{username}</strong></td>
            <td class="{'ok' if mfa else 'error'}">{'활성화' if mfa else '미설정'}</td>
            <td>{key_count}개</td>
            <td class="{key_age_class}">{key_date}</td>
            <td class="{security_class}">{security_status}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_sg_risky_rows(security_groups):
    """보안 그룹 위험 규칙 테이블 행 생성"""
    rows = []
    
    for sg in security_groups:
        sg_id = sg.get('id', 'N/A')
        sg_name = sg.get('name', 'N/A')
        vpc = sg.get('vpc', 'N/A')
        
        for rule in sg.get('risky_rules', []):
            port = rule.get('port', 'N/A')
            protocol = rule.get('protocol', 'N/A')
            source = rule.get('source', 'N/A')
            risk_level = rule.get('risk_level', 'medium')
            
            risk_class = {
                'critical': 'critical',
                'high': 'high', 
                'medium': 'medium',
                'low': 'low'
            }.get(risk_level, 'medium')
            
            rows.append(f"""
            <tr>
                <td>{sg_id}</td>
                <td>{sg_name}</td>
                <td>{vpc}</td>
                <td class="{risk_class}">{port}</td>
                <td>{protocol}</td>
                <td class="error">{source}</td>
                <td><span class="badge badge-{risk_class}">{risk_level.upper()}</span></td>
            </tr>
            """)
    
    if not rows:
        return '<tr><td colspan="7" class="no-data">위험한 보안 그룹 규칙이 없습니다</td></tr>'
    
    return ''.join(rows)

def get_compliance_class(rate):
    """준수율에 따른 CSS 클래스 반환"""
    if rate >= 90:
        return 'ok'
    elif rate >= 70:
        return 'warning'
    else:
        return 'critical'

def calculate_critical_issues(data):
    """Critical 이슈 계산 (중복 제거 및 그룹화)"""
    issues = []
    
    # IAM MFA 이슈 그룹화
    iam_issues = data.get('iam_security', {}).get('issues', [])
    mfa_issues = [issue for issue in iam_issues if issue.get('severity') == 'critical' and issue.get('type') == 'no_mfa']
    
    if mfa_issues:
        # MFA 미설정 사용자들을 하나로 그룹화
        mfa_users = [issue.get('user', 'N/A') for issue in mfa_issues]
        issues.append({
            'type': 'no_mfa',
            'description': f"MFA 미설정 ({len(mfa_users)}명: {', '.join(mfa_users[:5])}{'...' if len(mfa_users) > 5 else ''})",
            'severity': 'critical',
            'count': len(mfa_users)
        })
    
    # 보안 그룹 이슈 그룹화 (포트별)
    sg_data = data.get('security_groups', {})
    sg_issues_by_port = {}  # 포트별로 그룹화
    
    for sg in sg_data.get('details', []):
        for rule in sg.get('risky_rules', []):
            if rule.get('risk_level') in ['critical', 'high'] and rule.get('source') == '0.0.0.0/0':
                port = rule.get('port')
                if port in [22, 3389]:  # SSH, RDP만
                    if port not in sg_issues_by_port:
                        sg_issues_by_port[port] = []
                    sg_issues_by_port[port].append(sg.get('id'))
    
    # 포트별로 그룹화된 이슈 추가
    for port, sg_ids in sg_issues_by_port.items():
        port_name = "SSH (22)" if port == 22 else "RDP (3389)"
        issues.append({
            'type': 'risky_sg_rule',
            'description': f"위험한 보안 그룹 규칙 - {port_name} 전체 오픈 ({len(sg_ids)}개: {', '.join(sg_ids[:5])}{'...' if len(sg_ids) > 5 else ''})",
            'severity': 'critical',
            'count': len(sg_ids)
        })
    
    # EBS 암호화 미설정 (그룹화)
    encryption = data.get('encryption', {})
    unencrypted_volumes = encryption.get('ebs', {}).get('unencrypted_volumes', [])
    if unencrypted_volumes:
        issues.append({
            'type': 'unencrypted_ebs',
            'description': f"EBS 볼륨 암호화 미설정 ({len(unencrypted_volumes)}개)",
            'severity': 'critical',
            'count': len(unencrypted_volumes)
        })
    
    return issues

def generate_critical_issues_section(issues):
    """Critical 이슈 섹션 생성"""
    if not issues:
        return ''
    
    issue_items = []
    for issue in issues:
        issue_items.append(f"""
        <div class="issue-item">
            <strong>{issue.get('type', 'Unknown').replace('_', ' ').title()}:</strong> {issue.get('description', 'N/A')}
        </div>
        """)
    
    return f"""
    <div class="alert-box critical">
        <h4>⚠️ 즉시 조치 필요 항목 ({len(issues)}개)</h4>
        {''.join(issue_items)}
    </div>
    """

def process_trusted_advisor_data(checks):
    """Trusted Advisor 데이터 처리"""
    categories = {
        '보안': {'error': 0, 'warning': 0},
        '내결함성': {'error': 0, 'warning': 0},
        '비용 최적화': {'error': 0, 'warning': 0},
        'operational_excellence': {'error': 0, 'warning': 0}
    }
    
    error_rows = []
    
    for check in checks:
        category = check.get('category', '기타')
        status = check.get('status', 'ok')
        
        if category in categories:
            if status == 'error':
                categories[category]['error'] += 1
                error_rows.append(f"""
                <tr>
                    <td>{category}</td>
                    <td>{check.get('name', 'N/A')}</td>
                    <td class="error">ERROR</td>
                    <td class="error">{check.get('flagged_resources', 0)}</td>
                </tr>
                """)
            elif status == 'warning':
                categories[category]['warning'] += 1
    
    return {
        'ta_security_error': categories['보안']['error'],
        'ta_security_warning': categories['보안']['warning'],
        'ta_fault_tolerance_error': categories['내결함성']['error'],
        'ta_fault_tolerance_warning': categories['내결함성']['warning'],
        'ta_cost_warning': categories['비용 최적화']['warning'],
        'ta_performance_warning': categories['operational_excellence']['warning'],
        'ta_error_rows': ''.join(error_rows) if error_rows else '<tr><td colspan="4" class="no-data">Error 항목이 없습니다</td></tr>'
    }

def generate_cloudtrail_rows(critical_events):
    """CloudTrail 중요 이벤트 테이블 행 생성 (발생 횟수 0인 항목 제외)"""
    rows = []
    has_events = False
    
    for event_type, event_data in critical_events.items():
        count = event_data.get('count', 0)
        
        # 발생 횟수가 0이면 스킵
        if count == 0:
            continue
        
        has_events = True
        severity = event_data.get('severity', 'medium')
        category = event_data.get('category', 'unknown')
        description = event_data.get('description', 'N/A')
        
        severity_class = {
            'critical': 'critical',
            'high': 'high',
            'medium': 'medium'
        }.get(severity, 'medium')
        
        rows.append(f"""
        <tr>
            <td><strong>{event_type}</strong></td>
            <td><span class="badge badge-{severity_class}">{severity.upper()}</span></td>
            <td>{category.replace('_', ' ').title()}</td>
            <td class="warning">{count}</td>
            <td>{description}</td>
        </tr>
        """)
    
    # 발생한 이벤트가 없으면 "특이사항 없음" 메시지
    if not has_events:
        return '<tr><td colspan="5" class="no-data">✅ 특이사항 없음 - 모든 이벤트 발생 횟수 0회</td></tr>'
    
    return ''.join(rows)

def generate_cloudwatch_rows(alarms):
    """CloudWatch 알람 테이블 행 생성"""
    if not alarms:
        return '<tr><td colspan="4" class="no-data">CloudWatch 알람이 없습니다</td></tr>'
    
    rows = []
    for alarm in alarms:
        name = alarm.get('AlarmName', 'N/A')
        state = alarm.get('StateValue', 'UNKNOWN')
        metric = alarm.get('MetricName', 'N/A')
        threshold = alarm.get('Threshold', 'N/A')
        
        state_class = {
            'OK': 'ok',
            'ALARM': 'error',
            'INSUFFICIENT_DATA': 'warning'
        }.get(state, 'warning')
        
        rows.append(f"""
        <tr>
            <td>{name}</td>
            <td><span class="badge badge-{state_class}">{state}</span></td>
            <td>{metric}</td>
            <td>{threshold}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_ebs_unencrypted_section(ebs_data):
    """EBS 미암호화 볼륨 섹션 생성"""
    unencrypted_volumes = ebs_data.get('unencrypted_volumes', [])
    
    if not unencrypted_volumes:
        return ''
    
    volume_items = []
    for volume_id in unencrypted_volumes[:10]:
        volume_items.append(f'<li>{volume_id}</li>')
    
    more_text = f' (외 {len(unencrypted_volumes) - 10}개)' if len(unencrypted_volumes) > 10 else ''
    
    return f"""
    <div class="section">
        <h2>💿 EBS 볼륨 (암호화 미설정 {len(unencrypted_volumes)}개)</h2>
        <div class="alert-box">
            <h4>암호화가 필요한 EBS 볼륨</h4>
            <ul>
                {''.join(volume_items)}{more_text}
            </ul>
        </div>
    </div>
    """

def generate_s3_security_issues_section(buckets):
    """S3 보안 이슈 섹션 생성"""
    versioning_issues = []
    public_access_issues = []
    
    for bucket in buckets:
        name = bucket.get('Name', '')
        
        versioning = bucket.get('Versioning', {})
        if versioning.get('Status') != 'Enabled':
            versioning_issues.append(name)
        
        public_access = bucket.get('PublicAccessBlock')
        if not public_access or not all([
            public_access.get('BlockPublicAcls', False),
            public_access.get('IgnorePublicAcls', False),
            public_access.get('BlockPublicPolicy', False),
            public_access.get('RestrictPublicBuckets', False)
        ]):
            public_access_issues.append(name)
    
    if not versioning_issues and not public_access_issues:
        return ''
    
    content = '<div class="section"><h2>🪣 S3 버킷 보안 이슈</h2>'
    
    if versioning_issues:
        content += f"""
        <div class="alert-box">
            <h4>버저닝 미설정 버킷 ({len(versioning_issues)}개)</h4>
            <ul>
                {''.join(f'<li>{bucket}</li>' for bucket in versioning_issues[:10])}
            </ul>
        </div>
        """
    
    if public_access_issues:
        content += f"""
        <div class="alert-box">
            <h4>퍼블릭 액세스 차단 미설정 버킷 ({len(public_access_issues)}개)</h4>
            <ul>
                {''.join(f'<li>{bucket}</li>' for bucket in public_access_issues[:10])}
            </ul>
        </div>
        """
    
    content += '</div>'
    return content

def generate_html_report(json_file_path):
    """JSON 데이터를 월간 보안 점검 HTML 보고서로 변환"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # HTML 템플릿 읽기
        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'json_report_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # 기본 메타데이터
        metadata = data.get('metadata', {})
        
        # 템플릿 변수 생성
        template_vars = {
            'account_id': metadata.get('account_id', 'Unknown'),
            'region': metadata.get('region', 'ap-northeast-2'),
            'report_date': metadata.get('report_date', ''),
            'period_start': metadata.get('period_start', ''),
            'period_end': metadata.get('period_end', ''),
        }
        
        # EC2 데이터 처리
        ec2_data = data.get('resources', {}).get('ec2', {})
        template_vars.update({
            'ec2_total': ec2_data.get('summary', {}).get('total', 0),
            'ec2_running': ec2_data.get('summary', {}).get('running', 0),
            'ec2_stopped': ec2_data.get('summary', {}).get('stopped', 0),
            'ec2_rows': generate_ec2_rows(ec2_data.get('instances', [])),
        })
        
        # S3 데이터 처리
        s3_data = data.get('resources', {}).get('s3', {})
        s3_total = s3_data.get('summary', {}).get('total', 0)
        s3_encrypted = s3_data.get('summary', {}).get('encrypted', 0)
        s3_encrypted_rate = round((s3_encrypted / max(s3_total, 1)) * 100, 1) if s3_total > 0 else 0
        
        template_vars.update({
            's3_total': s3_total,
            's3_encrypted': s3_encrypted,
            's3_encrypted_rate': s3_encrypted_rate,
            's3_rows': generate_s3_rows(s3_data.get('buckets', [])),
        })
        
        # RDS 데이터 처리
        rds_data = data.get('resources', {}).get('rds', {})
        rds_instances = rds_data.get('instances', [])
        rds_multi_az = sum(1 for instance in rds_instances if instance.get('MultiAZ', False))
        template_vars.update({
            'rds_total': rds_data.get('summary', {}).get('total', 0),
            'rds_multi_az': rds_multi_az,
            'rds_content': generate_rds_content(rds_instances),
        })
        
        # Lambda 데이터 처리
        lambda_data = data.get('resources', {}).get('lambda', {})
        template_vars.update({
            'lambda_total': lambda_data.get('summary', {}).get('total', 0),
            'lambda_content': generate_lambda_content(lambda_data.get('functions', [])),
        })
        
        # IAM 데이터 처리
        iam_data = data.get('iam_security', {})
        iam_users = iam_data.get('users', {})
        iam_total = iam_users.get('total', 0)
        iam_mfa_enabled = iam_users.get('mfa_enabled', 0)
        iam_mfa_rate = round((iam_mfa_enabled / max(iam_total, 1)) * 100, 1) if iam_total > 0 else 0
        
        template_vars.update({
            'iam_users_total': iam_total,
            'iam_mfa_enabled': iam_mfa_enabled,
            'iam_mfa_rate': iam_mfa_rate,
            'iam_users_rows': generate_iam_users_rows(iam_users.get('details', [])),
        })
        
        # 보안 그룹 데이터 처리
        sg_data = data.get('security_groups', {})
        template_vars.update({
            'sg_total': sg_data.get('total', 0),
            'sg_risky': sg_data.get('risky', 0),
            'sg_risky_rows': generate_sg_risky_rows(sg_data.get('details', [])),
        })
        
        # 암호화 데이터 처리
        encryption_data = data.get('encryption', {})
        ebs_data = encryption_data.get('ebs', {})
        rds_encryption = encryption_data.get('rds', {})
        
        ebs_total = ebs_data.get('total', 0)
        ebs_encrypted = ebs_data.get('encrypted', 0)
        ebs_rate = round((ebs_encrypted / max(ebs_total, 1)) * 100, 1) if ebs_total > 0 else 0
        
        template_vars.update({
            'ebs_total': ebs_total,
            'ebs_encrypted': ebs_encrypted,
            'ebs_rate': ebs_rate,
            'rds_encrypted': rds_encryption.get('encrypted', 0),
            'rds_encrypted_rate': round(rds_encryption.get('encrypted_rate', 0) * 100, 1),
        })
        
        # 준수율 클래스 설정
        template_vars.update({
            'ebs_compliance_class': get_compliance_class(template_vars['ebs_rate']),
            's3_compliance_class': get_compliance_class(template_vars['s3_encrypted_rate']),
            'rds_compliance_class': get_compliance_class(template_vars['rds_encrypted_rate']),
        })
        
        # Critical 이슈 계산
        critical_issues = calculate_critical_issues(data)
        template_vars.update({
            'critical_issues_count': len(critical_issues),
            'critical_issues_section': generate_critical_issues_section(critical_issues),
        })
        
        # Trusted Advisor 데이터 처리
        ta_data = data.get('trusted_advisor', {})
        ta_summary = process_trusted_advisor_data(ta_data.get('checks', []))
        template_vars.update(ta_summary)
        
        # CloudTrail 데이터 처리
        ct_data = data.get('cloudtrail_events', {})
        template_vars.update({
            'cloudtrail_days': ct_data.get('summary', {}).get('period_days', 31),
            'cloudtrail_critical_rows': generate_cloudtrail_rows(ct_data.get('critical_events', {})),
        })
        
        # CloudWatch 데이터 처리
        cw_data = data.get('cloudwatch', {})
        cw_summary = cw_data.get('summary', {})
        template_vars.update({
            'cloudwatch_alarms_total': cw_summary.get('total', 0),
            'cloudwatch_alarms_in_alarm': cw_summary.get('in_alarm', 0),
            'cloudwatch_alarms_ok': cw_summary.get('ok', 0),
            'cloudwatch_alarms_insufficient': cw_summary.get('insufficient_data', 0),
            'cloudwatch_alarm_rows': generate_cloudwatch_rows(cw_data.get('alarms', [])),
        })
        
        # EBS 미암호화 섹션
        template_vars['ebs_unencrypted_section'] = generate_ebs_unencrypted_section(ebs_data)
        
        # S3 보안 이슈 섹션
        template_vars['s3_security_issues_section'] = generate_s3_security_issues_section(s3_data.get('buckets', []))
        
        # 템플릿에 변수 적용
        html_content = template.format(**template_vars)
        
        # HTML 파일 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_filename = f"security_report_{metadata.get('account_id', 'unknown')}_{timestamp}.html"
        html_file_path = os.path.join('/tmp/reports', html_filename)
        
        os.makedirs('/tmp/reports', exist_ok=True)
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[DEBUG] ✅ HTML 보고서 생성 완료: {html_file_path}", flush=True)
        return html_file_path
        
    except Exception as e:
        print(f"[ERROR] ❌ HTML 보고서 생성 실패: {str(e)}", flush=True)
        import traceback
        print(f"[ERROR] {traceback.format_exc()}", flush=True)
        return None

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3001, debug=False, allow_unsafe_werkzeug=True)
