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
from flask import Flask
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
        start_date_str (str): 시작 날짜 (YYYY-MM-DD)
        end_date_str (str): 종료 날짜 (YYYY-MM-DD)
        region (str): AWS 리전
        credentials (dict): AWS 자격증명 (선택사항)
    
    Returns:
        dict: 수집된 보안 데이터
    """
    try:
        print(f"[DEBUG] Raw 보안 데이터 수집 시작: {account_id}, {start_date_str} ~ {end_date_str}", flush=True)
        
        # boto3 세션 생성
        if credentials:
            session = boto3.Session(
                aws_access_key_id=credentials['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=credentials['AWS_SECRET_ACCESS_KEY'],
                aws_session_token=credentials['AWS_SESSION_TOKEN'],
                region_name=region
            )
        else:
            session = boto3.Session(region_name=region)
        
        # 클라이언트 생성
        ec2 = session.client('ec2')
        s3 = session.client('s3')
        iam = session.client('iam')
        cloudtrail = session.client('cloudtrail')
        cloudwatch = session.client('cloudwatch')
        
        # 메타데이터
        metadata = {
            'account_id': account_id,
            'report_date': datetime.now().strftime('%Y-%m-%d'),
            'period_start': start_date_str,
            'period_end': end_date_str,
            'region': region
        }
        
        # EC2 인스턴스 수집
        print(f"[DEBUG] EC2 인스턴스 수집 중...", flush=True)
        ec2_instances = []
        try:
            response = ec2.describe_instances()
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    # 인스턴스 이름 추출
                    name = 'N/A'
                    for tag in instance.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break
                    
                    ec2_instances.append({
                        'id': instance['InstanceId'],
                        'name': name,
                        'type': instance['InstanceType'],
                        'state': instance['State']['Name'],
                        'private_ip': instance.get('PrivateIpAddress', 'N/A'),
                        'public_ip': instance.get('PublicIpAddress', 'N/A'),
                        'launch_time': instance.get('LaunchTime')
                    })
        except Exception as e:
            print(f"[ERROR] EC2 데이터 수집 실패: {e}", flush=True)
        
        # S3 버킷 수집
        print(f"[DEBUG] S3 버킷 수집 중...", flush=True)
        s3_buckets = []
        try:
            response = s3.list_buckets()
            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                
                # 암호화 상태 확인
                encrypted = False
                try:
                    s3.get_bucket_encryption(Bucket=bucket_name)
                    encrypted = True
                except:
                    pass
                
                s3_buckets.append({
                    'name': bucket_name,
                    'creation_date': bucket['CreationDate'],
                    'encrypted': encrypted,
                    'region': region
                })
        except Exception as e:
            print(f"[ERROR] S3 데이터 수집 실패: {e}", flush=True)
        
        # IAM 사용자 수집
        print(f"[DEBUG] IAM 사용자 수집 중...", flush=True)
        iam_users = []
        try:
            response = iam.list_users()
            for user in response['Users']:
                username = user['UserName']
                
                # MFA 디바이스 확인
                mfa_devices = iam.list_mfa_devices(UserName=username)
                has_mfa = len(mfa_devices['MFADevices']) > 0
                
                # 액세스 키 확인
                access_keys = iam.list_access_keys(UserName=username)
                
                iam_users.append({
                    'username': username,
                    'creation_date': user['CreateDate'],
                    'mfa': has_mfa,
                    'access_keys': [key['AccessKeyId'] for key in access_keys['AccessKeyMetadata']]
                })
        except Exception as e:
            print(f"[ERROR] IAM 데이터 수집 실패: {e}", flush=True)
        
        # 보안 그룹 수집
        print(f"[DEBUG] 보안 그룹 수집 중...", flush=True)
        security_groups = []
        try:
            response = ec2.describe_security_groups()
            for sg in response['SecurityGroups']:
                # 위험한 규칙 확인 (0.0.0.0/0 허용)
                risky_rules = []
                for rule in sg.get('IpPermissions', []):
                    for ip_range in rule.get('IpRanges', []):
                        if ip_range.get('CidrIp') == '0.0.0.0/0':
                            risky_rules.append({
                                'protocol': rule.get('IpProtocol'),
                                'port': rule.get('FromPort'),
                                'cidr': '0.0.0.0/0'
                            })
                
                security_groups.append({
                    'id': sg['GroupId'],
                    'name': sg['GroupName'],
                    'description': sg['Description'],
                    'risky_rules': risky_rules,
                    'is_risky': len(risky_rules) > 0
                })
        except Exception as e:
            print(f"[ERROR] 보안 그룹 데이터 수집 실패: {e}", flush=True)
        
        # 데이터 구조화
        raw_data = {
            'metadata': metadata,
            'resources': {
                'ec2': {
                    'total': len(ec2_instances),
                    'running': len([i for i in ec2_instances if i['state'] == 'running']),
                    'instances': ec2_instances
                },
                's3': {
                    'total': len(s3_buckets),
                    'encrypted': len([b for b in s3_buckets if b['encrypted']]),
                    'buckets': s3_buckets
                },
                'lambda': {'total': 0, 'functions': []},  # 추후 구현
                'rds': {'total': 0, 'instances': []}  # 추후 구현
            },
            'iam_security': {
                'users': {
                    'total': len(iam_users),
                    'mfa_enabled': len([u for u in iam_users if u['mfa']]),
                    'details': iam_users
                },
                'issues': []  # 추후 분석
            },
            'security_groups': {
                'total': len(security_groups),
                'risky': len([sg for sg in security_groups if sg['is_risky']]),
                'details': security_groups
            },
            'encryption': {
                'ebs': {'total': 0, 'encrypted': 0, 'unencrypted_volumes': []},
                's3': {
                    'total': len(s3_buckets),
                    'encrypted': len([b for b in s3_buckets if b['encrypted']]),
                    'encrypted_rate': (len([b for b in s3_buckets if b['encrypted']]) / len(s3_buckets) * 100) if s3_buckets else 0
                },
                'rds': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0}
            },
            'trusted_advisor': {'available': False, 'checks': []},
            'cloudtrail_events': {
                'period_days': 30,
                'total_events': 0,
                'critical_events': [],
                'failed_logins': 0,
                'permission_changes': 0,
                'resource_deletions': 0
            },
            'cloudwatch': {
                'alarms': {'total': 0, 'in_alarm': 0, 'ok': 0, 'insufficient_data': 0, 'details': []},
                'high_cpu_instances': []
            },
            'recommendations': []
        }
        
        print(f"[DEBUG] Raw 보안 데이터 수집 완료", flush=True)
        return raw_data
        
    except Exception as e:
        print(f"[ERROR] Raw 보안 데이터 수집 중 오류: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {}



def generate_html_from_json(data):
    """JSON 데이터를 HTML 보고서로 변환 (Slack bot과 동일한 로직)"""
    try:
        # 기본 HTML 템플릿
        html_template = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS 월간 보안 점검 보고서 - {report_date}</title>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; margin: 20px; }}
        .header {{ background: #232F3E; color: white; padding: 20px; border-radius: 5px; }}
        .summary {{ background: #f8f9fa; padding: 15px; margin: 20px 0; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .alert {{ padding: 15px; margin: 20px 0; border-radius: 5px; }}
        .alert-danger {{ background-color: #f8d7da; border: 1px solid #f5c6cb; }}
        .section {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AWS 월간 보안 점검 보고서</h1>
        <p>계정: {account_id} | 보고서 생성일: {report_date}</p>
        <p>분석 기간: {period_start} ~ {period_end}</p>
    </div>
    
    <div class="summary">
        <h2>📊 요약</h2>
        <ul>
            <li><strong>EC2 인스턴스:</strong> 총 {ec2_total}개 (실행 중: {ec2_running}개)</li>
            <li><strong>S3 버킷:</strong> 총 {s3_total}개 (암호화: {s3_encrypted}개)</li>
            <li><strong>IAM 사용자:</strong> 총 {iam_total}개 (MFA 활성화: {iam_mfa}개)</li>
            <li><strong>보안 그룹:</strong> 총 {sg_total}개 (위험: {sg_risky}개)</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>🖥️ EC2 인스턴스</h2>
        {ec2_table}
    </div>
    
    <div class="section">
        <h2>🪣 S3 버킷</h2>
        {s3_table}
    </div>
    
    <div class="section">
        <h2>👤 IAM 보안</h2>
        {iam_table}
    </div>
    
    <div class="section">
        <h2>🛡️ 보안 그룹</h2>
        {sg_table}
    </div>
</body>
</html>"""
        
        # 데이터 추출
        metadata = data.get('metadata', {})
        resources = data.get('resources', {})
        iam = data.get('iam_security', {})
        sg = data.get('security_groups', {})
        
        # 테이블 생성
        ec2_table = generate_ec2_table(resources.get('ec2', {}).get('instances', []))
        s3_table = generate_s3_table(resources.get('s3', {}).get('buckets', []))
        iam_table = generate_iam_table(iam.get('users', {}).get('details', []))
        sg_table = generate_sg_table(sg.get('details', []))
        
        # HTML 생성
        html = html_template.format(
            account_id=metadata.get('account_id', 'Unknown'),
            report_date=metadata.get('report_date', 'Unknown'),
            period_start=metadata.get('period_start', 'Unknown'),
            period_end=metadata.get('period_end', 'Unknown'),
            ec2_total=resources.get('ec2', {}).get('total', 0),
            ec2_running=resources.get('ec2', {}).get('running', 0),
            s3_total=resources.get('s3', {}).get('total', 0),
            s3_encrypted=resources.get('s3', {}).get('encrypted', 0),
            iam_total=iam.get('users', {}).get('total', 0),
            iam_mfa=iam.get('users', {}).get('mfa_enabled', 0),
            sg_total=sg.get('total', 0),
            sg_risky=sg.get('risky', 0),
            ec2_table=ec2_table,
            s3_table=s3_table,
            iam_table=iam_table,
            sg_table=sg_table
        )
        
        return html
        
    except Exception as e:
        print(f"[ERROR] HTML 생성 실패: {e}", flush=True)
        return "<html><body><h1>보고서 생성 실패</h1></body></html>"

def generate_ec2_table(instances):
    """EC2 인스턴스 테이블 생성"""
    if not instances:
        return '<p>EC2 인스턴스가 없습니다.</p>'
    
    html = '<table><thead><tr><th>ID</th><th>이름</th><th>타입</th><th>상태</th><th>IP</th></tr></thead><tbody>'
    for inst in instances:
        html += f'''<tr>
            <td>{inst.get('id', 'N/A')}</td>
            <td>{inst.get('name', 'N/A')}</td>
            <td>{inst.get('type', 'N/A')}</td>
            <td>{inst.get('state', 'N/A')}</td>
            <td>{inst.get('private_ip', 'N/A')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html

def generate_s3_table(buckets):
    """S3 버킷 테이블 생성"""
    if not buckets:
        return '<p>S3 버킷이 없습니다.</p>'
    
    html = '<table><thead><tr><th>이름</th><th>리전</th><th>암호화</th><th>생성일</th></tr></thead><tbody>'
    for bucket in buckets:
        html += f'''<tr>
            <td>{bucket.get('name', 'N/A')}</td>
            <td>{bucket.get('region', 'N/A')}</td>
            <td>{'예' if bucket.get('encrypted') else '아니오'}</td>
            <td>{bucket.get('creation_date', 'N/A')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html

def generate_iam_table(users):
    """IAM 사용자 테이블 생성"""
    if not users:
        return '<p>IAM 사용자가 없습니다.</p>'
    
    html = '<table><thead><tr><th>사용자명</th><th>MFA</th><th>액세스 키</th><th>생성일</th></tr></thead><tbody>'
    for user in users:
        html += f'''<tr>
            <td>{user.get('username', 'N/A')}</td>
            <td>{'활성화' if user.get('mfa') else '비활성화'}</td>
            <td>{len(user.get('access_keys', []))}개</td>
            <td>{user.get('creation_date', 'N/A')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html

def generate_sg_table(security_groups):
    """보안 그룹 테이블 생성"""
    if not security_groups:
        return '<p>보안 그룹이 없습니다.</p>'
    
    html = '<table><thead><tr><th>ID</th><th>이름</th><th>설명</th><th>위험 규칙</th></tr></thead><tbody>'
    for sg in security_groups:
        risky_count = len(sg.get('risky_rules', []))
        html += f'''<tr>
            <td>{sg.get('id', 'N/A')}</td>
            <td>{sg.get('name', 'N/A')}</td>
            <td>{sg.get('description', 'N/A')}</td>
            <td>{risky_count}개</td>
        </tr>'''
    html += '</tbody></table>'
    return html

def generate_html_report(json_file_path):
    """JSON 데이터를 월간 보안 점검 HTML 보고서로 변환 (Slack bot과 동일)"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # HTML 템플릿 경로 (여러 경로 시도)
        template_paths = [
            'reference_templates/json_report_template.html',
            '/tmp/reports/json_report_template.html',
            'json_report_template.html'
        ]
        
        template = None
        for template_path in template_paths:
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = f.read()
                print(f"[DEBUG] 템플릿 로드 성공: {template_path}", flush=True)
                break
            except FileNotFoundError:
                continue
        
        # 템플릿이 없으면 기본 HTML 생성 함수 사용
        if not template:
            print(f"[DEBUG] 템플릿 파일 없음, 기본 HTML 생성 사용", flush=True)
            # 기본 HTML 생성
            html_content = generate_html_from_json(data)
            
            # 파일 저장
            metadata = data.get('metadata', {})
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            html_filename = f"security_report_{metadata.get('account_id', 'unknown')}_{timestamp}.html"
            html_path = f"/tmp/reports/{html_filename}"
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"[DEBUG] HTML 보고서 생성 완료: {html_path}", flush=True)
            return html_path

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

# 월간 보고서 생성에 필요한 헬퍼 함수들 (Slack bot에서 복사)
def generate_ec2_rows(instances):
    """EC2 인스턴스 테이블 행 생성"""
    if not instances:
        return '<tr><td colspan="6" class="no-data">EC2 인스턴스가 없습니다</td></tr>'
    
    rows = []
    for instance in instances:
        # 인스턴스 이름 추출
        name = "이름 없음"
        for tag in instance.get('Tags', []):
            if tag.get('Key') == 'Name':
                name = tag.get('Value', '이름 없음')
                break
        
        # 상태에 따른 아이콘
        state = instance.get('State', {}).get('Name', 'unknown')
        state_icon = '🟢' if state == 'running' else '🔴' if state == 'stopped' else '🟡'
        
        # 보안 그룹 정보
        security_groups = []
        for sg in instance.get('SecurityGroups', []):
            security_groups.append(sg.get('GroupName', 'Unknown'))
        sg_text = ', '.join(security_groups[:2])  # 최대 2개만 표시
        if len(security_groups) > 2:
            sg_text += f" 외 {len(security_groups) - 2}개"
        
        rows.append(f"""
        <tr>
            <td>{name}</td>
            <td>{instance.get('InstanceId', 'Unknown')}</td>
            <td>{state_icon} {state}</td>
            <td>{instance.get('InstanceType', 'Unknown')}</td>
            <td>{instance.get('Placement', {}).get('AvailabilityZone', 'Unknown')}</td>
            <td>{sg_text}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_s3_rows(buckets):
    """S3 버킷 테이블 행 생성"""
    if not buckets:
        return '<tr><td colspan="5" class="no-data">S3 버킷이 없습니다</td></tr>'
    
    rows = []
    for bucket in buckets:
        # 암호화 상태
        encryption = bucket.get('encryption', {})
        encrypted = encryption.get('enabled', False)
        encryption_icon = '🔒' if encrypted else '🔓'
        encryption_text = '활성화' if encrypted else '비활성화'
        
        # 버전 관리
        versioning = bucket.get('versioning', {})
        versioning_enabled = versioning.get('enabled', False)
        versioning_icon = '✅' if versioning_enabled else '❌'
        
        # 퍼블릭 액세스
        public_access = bucket.get('public_access', {})
        is_public = public_access.get('is_public', False)
        public_icon = '⚠️' if is_public else '🔒'
        public_text = '퍼블릭' if is_public else '프라이빗'
        
        rows.append(f"""
        <tr>
            <td>{bucket.get('name', 'Unknown')}</td>
            <td>{bucket.get('region', 'Unknown')}</td>
            <td>{encryption_icon} {encryption_text}</td>
            <td>{versioning_icon} {'활성화' if versioning_enabled else '비활성화'}</td>
            <td>{public_icon} {public_text}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_rds_content(instances):
    """RDS 인스턴스 콘텐츠 생성"""
    if not instances:
        return '<div class="no-data">RDS 인스턴스가 없습니다</div>'
    
    table = '<table class="data-table">'
    table += '''
    <thead>
        <tr>
            <th>인스턴스 ID</th>
            <th>엔진</th>
            <th>상태</th>
            <th>Multi-AZ</th>
            <th>암호화</th>
        </tr>
    </thead>
    <tbody>
    '''
    
    for instance in instances:
        multi_az = instance.get('MultiAZ', False)
        multi_az_icon = '✅' if multi_az else '❌'
        
        encrypted = instance.get('StorageEncrypted', False)
        encryption_icon = '🔒' if encrypted else '🔓'
        
        table += f'''
        <tr>
            <td>{instance.get('DBInstanceIdentifier', 'Unknown')}</td>
            <td>{instance.get('Engine', 'Unknown')}</td>
            <td>{instance.get('DBInstanceStatus', 'Unknown')}</td>
            <td>{multi_az_icon} {'활성화' if multi_az else '비활성화'}</td>
            <td>{encryption_icon} {'활성화' if encrypted else '비활성화'}</td>
        </tr>
        '''
    
    table += '</tbody></table>'
    return table

def generate_lambda_content(functions):
    """Lambda 함수 콘텐츠 생성"""
    if not functions:
        return '<div class="no-data">Lambda 함수가 없습니다</div>'
    return '<div class="no-data">Lambda 함수가 없습니다</div>'

def generate_iam_users_rows(users):
    """IAM 사용자 테이블 행 생성"""
    if not users:
        return '<tr><td colspan="4" class="no-data">IAM 사용자가 없습니다</td></tr>'
    
    rows = []
    for user in users:
        mfa_enabled = user.get('mfa_enabled', False)
        mfa_icon = '✅' if mfa_enabled else '❌'
        
        # 마지막 로그인 시간
        last_login = user.get('password_last_used', 'N/A')
        if last_login and last_login != 'N/A':
            try:
                # ISO 형식 날짜를 파싱하여 표시
                from datetime import datetime
                login_date = datetime.fromisoformat(last_login.replace('Z', '+00:00'))
                last_login = login_date.strftime('%Y-%m-%d')
            except:
                pass
        
        rows.append(f"""
        <tr>
            <td>{user.get('username', 'Unknown')}</td>
            <td>{mfa_icon} {'활성화' if mfa_enabled else '비활성화'}</td>
            <td>{user.get('access_keys_count', 0)}</td>
            <td>{last_login}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_sg_risky_rows(security_groups):
    """보안 그룹 위험 규칙 테이블 행 생성"""
    rows = []
    for sg in security_groups:
        if not sg.get('risky_rules'):
            continue
            
        for rule in sg.get('risky_rules', []):
            risk_level = rule.get('risk_level', 'medium')
            risk_icon = '🔴' if risk_level == 'high' else '🟡'
            
            rows.append(f"""
            <tr>
                <td>{sg.get('group_name', 'Unknown')}</td>
                <td>{rule.get('protocol', 'Unknown')}</td>
                <td>{rule.get('port_range', 'Unknown')}</td>
                <td>{rule.get('source', 'Unknown')}</td>
                <td>{risk_icon} {risk_level.upper()}</td>
            </tr>
            """)
    
    return ''.join(rows)

def get_compliance_class(rate):
    """준수율에 따른 CSS 클래스 반환"""
    if rate >= 90:
        return 'good'
    elif rate >= 70:
        return 'warning'
    else:
        return 'critical'

def calculate_critical_issues(data):
    """Critical 이슈 계산"""
    issues = []
    # 간단한 구현 - 실제로는 더 복잡한 로직 필요
    return issues

def generate_critical_issues_section(issues):
    """Critical 이슈 섹션 생성"""
    if not issues:
        return '<div class="no-data">Critical 이슈가 없습니다</div>'
    return '<div class="no-data">Critical 이슈가 없습니다</div>'

def process_trusted_advisor_data(checks):
    """Trusted Advisor 데이터 처리"""
    return {
        'ta_cost_optimization': 0,
        'ta_security': 0,
        'ta_fault_tolerance': 0,
        'ta_performance': 0,
        'ta_service_limits': 0,
    }

def generate_cloudtrail_rows(critical_events):
    """CloudTrail 중요 이벤트 테이블 행 생성"""
    if not critical_events:
        return '<tr><td colspan="3" class="no-data">중요 이벤트가 없습니다</td></tr>'
    
    rows = []
    for event_name, count in critical_events.items():
        if count > 0:
            rows.append(f"""
            <tr>
                <td>{event_name}</td>
                <td>{count}</td>
                <td>{'🔴 높음' if count > 10 else '🟡 보통'}</td>
            </tr>
            """)
    
    return ''.join(rows) if rows else '<tr><td colspan="3" class="no-data">중요 이벤트가 없습니다</td></tr>'

def generate_cloudwatch_rows(alarms):
    """CloudWatch 알람 테이블 행 생성"""
    if not alarms:
        return '<tr><td colspan="4" class="no-data">CloudWatch 알람이 없습니다</td></tr>'
    
    rows = []
    for alarm in alarms:
        state = alarm.get('state', 'UNKNOWN')
        state_icon = '🔴' if state == 'ALARM' else '🟢' if state == 'OK' else '🟡'
        
        rows.append(f"""
        <tr>
            <td>{alarm.get('name', 'Unknown')}</td>
            <td>{state_icon} {state}</td>
            <td>{alarm.get('metric_name', 'Unknown')}</td>
            <td>{alarm.get('threshold', 'Unknown')}</td>
        </tr>
        """)
    
    return ''.join(rows)

def generate_ebs_unencrypted_section(ebs_data):
    """EBS 미암호화 섹션 생성"""
    return '<div class="no-data">EBS 미암호화 볼륨이 없습니다</div>'

def generate_s3_security_issues_section(buckets):
    """S3 보안 이슈 섹션 생성"""
    return '<div class="no-data">S3 보안 이슈가 없습니다</div>'

# Flask 라우트: 보고서 파일 제공 (여러 경로 지원)
def serve_report_impl(filename):
    """보고서 파일 제공 구현"""
    try:
        from flask import send_file, abort
        
        # 보안: 경로 조작 방지
        if '..' in filename or filename.startswith('/'):
            abort(400)
        
        file_path = os.path.join('/tmp/reports', filename)
        
        # 파일 존재 여부 확인
        if not os.path.exists(file_path):
            print(f"[DEBUG] 보고서 파일 없음: {file_path}", flush=True)
            abort(404)
        
        # 디렉터리인 경우 index.html 제공
        if os.path.isdir(file_path):
            index_path = os.path.join(file_path, 'index.html')
            if os.path.exists(index_path):
                print(f"[DEBUG] 디렉터리 인덱스 제공: {index_path}", flush=True)
                return send_file(index_path, mimetype='text/html')
            else:
                abort(404)
        
        # 파일 제공
        print(f"[DEBUG] 보고서 파일 제공: {file_path}", flush=True)
        
        # MIME 타입 결정
        if filename.endswith('.html'):
            mimetype = 'text/html'
        elif filename.endswith('.css'):
            mimetype = 'text/css'
        elif filename.endswith('.js'):
            mimetype = 'application/javascript'
        elif filename.endswith('.json'):
            mimetype = 'application/json'
        elif filename.endswith('.png'):
            mimetype = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif filename.endswith('.gif'):
            mimetype = 'image/gif'
        elif filename.endswith('.svg'):
            mimetype = 'image/svg+xml'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(file_path, mimetype=mimetype)
        
    except Exception as e:
        print(f"[ERROR] 보고서 파일 제공 중 오류: {str(e)}", flush=True)
        abort(500)

# 경로 1: /reports/
@app.route('/reports/<path:filename>')
def serve_report(filename):
    """보고서 파일 제공 (/reports/)"""
    return serve_report_impl(filename)

# 경로 2: /zendesk/reports/ (ALB가 /zendesk/ 경로를 라우팅하는 경우)
@app.route('/zendesk/reports/<path:filename>')
def serve_report_zendesk(filename):
    """보고서 파일 제공 (/zendesk/reports/)"""
    return serve_report_impl(filename)

@socketio.on('connect', namespace='/zendesk')
def handle_connect():
    """클라이언트 연결 시"""
    from flask import request
    print(f"[DEBUG] 클라이언트 연결됨: {request.sid}", flush=True)
    active_sessions.add(request.sid)
    print(f"[DEBUG] 활성 세션 목록: {active_sessions}", flush=True)
    
    # 진행 중인 작업이 있는지 확인하고 상태 복구
    ongoing_tasks = [q for q in processing_questions if q.startswith('zendesk_user:')]
    if ongoing_tasks:
        print(f"[DEBUG] 진행 중인 작업 발견: {ongoing_tasks}", flush=True)
        
        # 가장 최근 진행 상태 찾기
        latest_progress = None
        for task in ongoing_tasks:
            if task in current_progress:
                latest_progress = current_progress[task]
                break
        
        if latest_progress:
            print(f"[DEBUG] 최근 진행 상태 복구: {latest_progress}", flush=True)
            emit('progress', latest_progress)
        else:
            emit('progress', {'progress': 50, 'message': '이전 작업을 계속 진행하고 있습니다...'})
    
    emit('connected', {'message': 'Saltware AWS Assistant에 연결되었습니다!'})

@socketio.on('disconnect', namespace='/zendesk')
def handle_disconnect():
    """클라이언트 연결 해제 시"""
    from flask import request
    print(f"[DEBUG] 클라이언트 연결 해제됨: {request.sid}", flush=True)
    active_sessions.discard(request.sid)
    print(f"[DEBUG] 활성 세션 목록: {active_sessions}", flush=True)

@socketio.on('aws_query', namespace='/zendesk')
def handle_aws_query(data):
    """AWS 질문 처리"""
    try:
        from flask import request
        
        query = data.get('query', '').strip()
        user_id = data.get('user_id', 'unknown')
        ticket_id = data.get('ticket_id', 'unknown')
        
        if not query:
            emit('error', {'message': '질문을 입력해주세요.'})
            return
        
        # 질문 고유 키 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        question_key = f"{user_id}:{ticket_id}:{timestamp}"
        
        if question_key in processing_questions:
            emit('error', {'message': '이미 처리 중인 질문입니다.'})
            return
        
        print(f"[DEBUG] 새 질문 처리: {question_key}", flush=True)
        print(f"[DEBUG] 질문 내용: {query}", flush=True)
        processing_questions.add(question_key)
        
        # 진행률 0% 전송
        emit('progress', {'progress': 0, 'message': '질문을 분석하고 있습니다...'}, namespace='/zendesk')
        
        # 백그라운드에서 처리
        thread = threading.Thread(
            target=process_aws_question_async, 
            args=(query, question_key, user_id, ticket_id, request.sid)
        )
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        print(f"[ERROR] AWS 질문 처리 중 오류: {str(e)}", flush=True)
        emit('error', {'message': f'질문 처리 중 오류가 발생했습니다: {str(e)}'}, namespace='/zendesk')

def process_aws_question_async(query, question_key, user_id, ticket_id, session_id):
    """비동기로 AWS 질문 처리 (기존 Slack bot 로직 포팅)"""
    temp_dir = None
    
    def emit_to_client(event_type, data):
        """클라이언트에게 이벤트 전송하는 통합 헬퍼 함수 (중복 전송 방지)"""
        try:
            print(f"[DEBUG] 이벤트 전송 시도: {event_type}, 데이터: {data}", flush=True)
            
            # 현재 활성 세션 확인
            print(f"[DEBUG] 현재 활성 세션: {active_sessions}", flush=True)
            print(f"[DEBUG] 대상 세션: {session_id}", flush=True)
            
            # 특정 세션으로만 전송 (중복 방지)
            if session_id in active_sessions:
                try:
                    socketio.emit(event_type, data, room=session_id, namespace='/zendesk')
                    print(f"[DEBUG] ✅ 세션별 전송 완료: {event_type} -> 세션 {session_id}", flush=True)
                except Exception as e:
                    print(f"[WARNING] 세션별 전송 실패: {e}", flush=True)
                    # 세션별 전송 실패 시에만 브로드캐스트로 폴백
                    try:
                        socketio.emit(event_type, data, namespace='/zendesk')
                        print(f"[DEBUG] ✅ 폴백 브로드캐스트 전송 완료: {event_type}", flush=True)
                    except Exception as fallback_error:
                        print(f"[ERROR] 폴백 브로드캐스트도 실패: {fallback_error}", flush=True)
            else:
                print(f"[WARNING] 세션 {session_id}가 활성 목록에 없음, 브로드캐스트로 전송", flush=True)
                # 세션이 없을 때만 브로드캐스트
                try:
                    socketio.emit(event_type, data, namespace='/zendesk')
                    print(f"[DEBUG] ✅ 브로드캐스트 전송 완료: {event_type}", flush=True)
                except Exception as e:
                    print(f"[ERROR] 브로드캐스트 전송 실패: {e}", flush=True)
            
        except Exception as e:
            print(f"[ERROR] 이벤트 전송 실패: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    def emit_progress(progress, message):
        """진행률 전송 헬퍼 함수"""
        # 진행 상태 저장
        current_progress[question_key] = {'progress': progress, 'message': message}
        emit_to_client('progress', {'progress': progress, 'message': message})
    
    def emit_result(data):
        """결과 전송 헬퍼 함수"""
        emit_to_client('result', data)
    
    def emit_error(message):
        """에러 전송 헬퍼 함수"""
        emit_to_client('error', {'message': message})
    
    try:
        print(f"[DEBUG] 질문 처리 중: {query} (세션: {session_id})", flush=True)
        
        # 진행률 10% - 계정 ID 추출
        emit_progress(10, '계정 정보를 확인하고 있습니다...')
        
        # 계정 ID 추출
        account_id = extract_account_id(query)
        env_vars = os.environ.copy()
        
        # MCP 서버 초기화 타임아웃 설정
        env_vars['Q_MCP_INIT_TIMEOUT'] = '10000'  # 10초
        
        account_prefix = ""
        korean_prompt = ""  # 변수 초기화
        context_content = ""  # 컨텍스트 내용 초기화
        
        if account_id:
            print(f"[DEBUG] 계정 ID 발견: {account_id}", flush=True)
            
            # 진행률 20% - Cross-account 세션 생성
            emit_progress(20, f'계정 {account_id} 접근 권한을 확인하고 있습니다...')
            
            # Cross-account 세션 생성
            credentials = get_crossaccount_session(account_id)
            if credentials:
                # 세션 격리: 임시 디렉터리 생성
                temp_dir = tempfile.mkdtemp(prefix=f'q_session_{account_id}_{question_key.replace(":", "_")}_')
                print(f"[DEBUG] 임시 세션 디렉터리 생성: {temp_dir}", flush=True)
                
                # Q CLI 캐시 무효화
                q_cache_dirs = [
                    os.path.expanduser('~/.cache/q'),
                    os.path.expanduser('~/.q'),
                    '/tmp/q-cache'
                ]
                
                for cache_dir in q_cache_dirs:
                    if os.path.exists(cache_dir):
                        try:
                            shutil.rmtree(cache_dir)
                            print(f"[DEBUG] Q CLI 캐시 삭제: {cache_dir}", flush=True)
                        except Exception as e:
                            print(f"[DEBUG] 캐시 삭제 실패 (무시): {cache_dir} - {e}", flush=True)
                
                # 환경 변수 설정
                env_vars['AWS_CONFIG_FILE'] = os.path.join(temp_dir, 'config')
                env_vars['AWS_SHARED_CREDENTIALS_FILE'] = os.path.join(temp_dir, 'credentials')
                env_vars['AWS_ACCESS_KEY_ID'] = credentials['AWS_ACCESS_KEY_ID']
                env_vars['AWS_SECRET_ACCESS_KEY'] = credentials['AWS_SECRET_ACCESS_KEY']
                env_vars['AWS_SESSION_TOKEN'] = credentials['AWS_SESSION_TOKEN']
                env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
                env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
                env_vars['AWS_SDK_LOAD_CONFIG'] = '0'
                
                # 진행률 30% - 계정 검증
                emit_progress(30, '계정 접근을 검증하고 있습니다...')
                
                # 계정 검증
                verify_cmd = ['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text']
                verify_result = subprocess.run(
                    verify_cmd,
                    capture_output=True,
                    text=True,
                    env=env_vars,
                    timeout=10
                )
                
                if verify_result.returncode == 0:
                    actual_account = verify_result.stdout.strip()
                    print(f"[DEBUG] 계정 검증 - 요청: {account_id}, 실제: {actual_account}", flush=True)
                    
                    if actual_account != account_id:
                        print(f"[ERROR] 계정 불일치! 요청: {account_id}, 실제: {actual_account}", flush=True)
                        emit_error(f'계정 자격증명 오류\n요청: {account_id}\n실제: {actual_account}')
                        return
                    else:
                        print(f"[DEBUG] ✅ 계정 검증 성공: {actual_account}", flush=True)
                else:
                    print(f"[ERROR] 계정 검증 실패: {verify_result.stderr}", flush=True)
                    emit_error(f'계정 검증 실패: {verify_result.stderr[:200]}')
                    return
                
                account_prefix = f"🏢 계정 {account_id} 결과:\n\n"
                query = re.sub(r'\b\d{12}\b', '', query).strip()
                query = re.sub(r'계정\s*', '', query).strip()
                query = re.sub(r'account\s*', '', query, flags=re.IGNORECASE).strip()
                print(f"[DEBUG] 정리된 질문: {query}", flush=True)
            else:
                print(f"[DEBUG] 계정 {account_id} 접근 실패", flush=True)
                emit_error(f'계정 {account_id}에 접근할 수 없습니다.')
                return
        
        # 진행률 40% - 질문 유형 분석
        emit_progress(40, '질문 유형을 분석하고 있습니다...')
        
        # 질문 유형 분석
        question_type, context_path = analyze_question_type(query)
        print(f"[DEBUG] 질문 유형: {question_type}, 컨텍스트: {context_path}", flush=True)
        
        # 컨텍스트 파일 로드 (모든 경우에 대해)
        context_content = load_context_file(context_path) if context_path else ""
        
        # 기본 한국어 프롬프트 구성 (모든 경우에 대해)
        korean_prompt = f"""다음 컨텍스트를 참고하여 질문에 답변해주세요:

{context_content}

=== 사용자 질문 ===
{query}

위 컨텍스트의 가이드라인을 따라 한국어로 답변해주세요."""
        
        # 진행률 50% - AWS 분석 시작
        emit_progress(50, 'AWS 분석을 시작합니다...')
        
        # Service Screener 처리
        if question_type == 'screener':
            emit_progress(60, f'계정 {account_id} Service Screener 스캔을 시작합니다...')
            
            try:
                # 기존 Service Screener 결과 삭제 (새로운 스캔을 위해)
                old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
                if os.path.exists(old_result_dir):
                    print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
                    shutil.rmtree(old_result_dir)
                
                # Service Screener 직접 실행
                emit_progress(70, 'Service Screener를 실행하고 있습니다...')
                
                cmd = ['python3', '/root/service-screener-v2/main.py', '--regions', 'ap-northeast-2,us-east-1']
                print(f"[DEBUG] Service Screener 실행: {' '.join(cmd)}", flush=True)
                
                log_file = f'/tmp/screener_{account_id}.log'
                with open(log_file, 'w') as f:
                    result = subprocess.run(
                        cmd,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        env=env_vars,
                        timeout=600,  # 10분 타임아웃
                        cwd='/root/service-screener-v2'
                    )
                
                print(f"[DEBUG] Service Screener 실행 완료. 반환코드: {result.returncode}", flush=True)
                
                emit_progress(80, '스캔 결과를 분석하고 있습니다...')
                
                # 결과 디렉터리 확인
                account_result_dir = os.path.join('/root/service-screener-v2/adminlte/aws', account_id)
                
                if os.path.exists(account_result_dir):
                    print(f"[DEBUG] Service Screener 결과 발견: {account_result_dir}", flush=True)
                    
                    # 전체 디렉터리를 /tmp/reports/로 복사
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"
                    
                    # 기존 디렉터리가 있으면 삭제
                    if os.path.exists(tmp_report_dir):
                        shutil.rmtree(tmp_report_dir)
                    
                    # 전체 디렉터리 복사
                    shutil.copytree(account_result_dir, tmp_report_dir)
                    print(f"[DEBUG] 보고서 디렉터리 복사 완료: {tmp_report_dir}", flush=True)
                    
                    # res 디렉터리 복사 (CSS/JS 등)
                    screener_res_dir = '/root/service-screener-v2/adminlte/aws/res'
                    tmp_res_dir = '/tmp/reports/res'
                    
                    if os.path.exists(screener_res_dir):
                        if os.path.exists(tmp_res_dir):
                            shutil.rmtree(tmp_res_dir)
                        shutil.copytree(screener_res_dir, tmp_res_dir)
                        print(f"[DEBUG] res 디렉터리 복사 완료: {tmp_res_dir}", flush=True)
                    
                    # 결과 요약 생성 (간단한 파싱)
                    summary = f"""📊 Service Screener 스캔 결과

🏢 계정: {account_id}
📍 스캔 리전: ap-northeast-2, us-east-1
✅ 스캔이 성공적으로 완료되었습니다.

상세한 분석 결과는 아래 보고서에서 확인하실 수 있습니다."""
                    
                    # 보고서 URL 생성
                    report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/screener_{account_id}_{timestamp}/index.html"
                    
                    emit_progress(100, '스캔이 완료되었습니다!')
                    emit_result({
                        'summary': summary,
                        'reports': [
                            {
                                'name': 'Service Screener 상세 보고서',
                                'url': report_url
                            }
                        ]
                    })
                    
                else:
                    print(f"[DEBUG] Service Screener 결과 디렉터리 없음: {account_result_dir}", flush=True)
                    
                    # 로그 파일 내용 확인
                    try:
                        with open(log_file, 'r') as f:
                            log_content = f.read()
                        print(f"[DEBUG] Service Screener 로그:\n{log_content[-1000:]}", flush=True)
                    except Exception as e:
                        print(f"[DEBUG] 로그 파일 읽기 실패: {e}", flush=True)
                    
                    error_summary = f"""⚠️ Service Screener 실행 완료

🏢 계정: {account_id}
📍 스캔 리전: ap-northeast-2, us-east-1

스캔은 실행되었으나 결과 파일을 찾을 수 없습니다.
로그를 확인하여 문제를 진단해주세요."""
                    
                    emit_progress(100, '스캔 완료 (결과 확인 필요)')
                    emit_result({'summary': error_summary})
                    
            except subprocess.TimeoutExpired:
                print(f"[ERROR] Service Screener 타임아웃", flush=True)
                timeout_summary = f"""⏰ Service Screener 타임아웃

🏢 계정: {account_id}
스캔 시간이 10분을 초과하여 중단되었습니다.
계정 규모가 큰 경우 더 오래 걸릴 수 있습니다."""
                
                emit_progress(100, '스캔 시간 초과')
                emit_result({'summary': timeout_summary})
                
            except Exception as e:
                print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                
                error_summary = f"""❌ Service Screener 실행 오류

🏢 계정: {account_id}
오류: {str(e)}

시스템 관리자에게 문의하거나 잠시 후 다시 시도해주세요."""
                
                emit_progress(100, '스캔 실행 오류')
                emit_result({'summary': error_summary})
            
        else:
            # 질문 유형에 따른 처리
            if question_type == 'report':
                # 월간 보고서 생성 처리
                emit_progress(60, '보안 데이터를 수집하고 있습니다...')
                
                # 날짜 추출 로직 (Slack bot과 동일)
                now = datetime.now()
                target_account = account_id if account_id else "950027134314"
                
                # 질문에서 여러 월 추출 (9월, 10월 등)
                month_matches = re.findall(r'(\d{1,2})월', query)
                year_match = re.search(r'(\d{4})년?', query)
                
                if month_matches:
                    # 여러 월이 있으면 범위로 처리
                    months = [int(m) for m in month_matches]
                    start_month = min(months)
                    end_month = max(months)
                    
                    target_year = year_match.group(1) if year_match else str(now.year)
                    target_year = int(target_year)
                    
                    # 시작일: 첫 번째 월의 1일
                    start_date = date(target_year, start_month, 1)
                    
                    # 종료일: 마지막 월의 말일
                    if end_month == 12:
                        end_date = date(target_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        end_date = date(target_year, end_month + 1, 1) - timedelta(days=1)
                    
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    end_date_str = end_date.strftime("%Y-%m-%d")
                else:
                    # 월 정보 없으면 최근 30일
                    start_date = now.date() - timedelta(days=30)
                    end_date = now.date()
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    end_date_str = end_date.strftime("%Y-%m-%d")
                
                # 타임스탬프 생성 (파일명용)
                from datetime import timezone
                kst = timezone(timedelta(hours=9))
                timestamp = datetime.now(kst).strftime("%Y%m%d_%H%M%S")
                
                raw_json_path = f"/tmp/reports/raw_security_data_{target_account}_{timestamp}.json"
                
                try:
                    # 1단계: boto3로 raw 데이터 수집
                    print(f"[DEBUG] 📦 1단계: boto3로 raw 데이터 수집 시작", flush=True)
                    print(f"[DEBUG] 분석 기간: {start_date_str} ~ {end_date_str} (UTC+9)", flush=True)
                    
                    emit_progress(70, f'AWS 보안 데이터를 수집하고 있습니다... ({start_date_str} ~ {end_date_str})')
                    
                    # boto3로 raw 데이터 수집
                    raw_data = collect_raw_security_data(
                        target_account, 
                        start_date_str, 
                        end_date_str, 
                        region='ap-northeast-2',
                        credentials=credentials if account_id else None
                    )
                    
                    # Raw JSON 파일로 저장
                    with open(raw_json_path, 'w', encoding='utf-8') as f:
                        json.dump(raw_data, f, indent=2, ensure_ascii=False, default=convert_datetime_to_json_serializable)
                    print(f"[DEBUG] ✅ Raw JSON 저장 완료: {raw_json_path}", flush=True)
                    
                    emit_progress(80, 'HTML 보고서를 생성하고 있습니다...')
                    
                    # HTML 보고서 생성
                    html_report_path = generate_html_report(raw_json_path)
                    if html_report_path:
                        print(f"[DEBUG] ✅ HTML 보고서 생성 완료: {html_report_path}", flush=True)
                        
                        # HTML 보고서 URL 생성
                        html_filename = os.path.basename(html_report_path)
                        html_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{html_filename}"
                        
                        emit_progress(100, '보고서 생성이 완료되었습니다!')
                        
                        # 요약 정보 생성
                        ec2_total = raw_data.get('resources', {}).get('ec2', {}).get('total', 0)
                        s3_total = raw_data.get('resources', {}).get('s3', {}).get('total', 0)
                        iam_total = raw_data.get('iam_security', {}).get('users', {}).get('total', 0)
                        sg_risky = raw_data.get('security_groups', {}).get('risky', 0)
                        
                        summary = f"""✅ AWS 월간 보안 보고서 생성 완료!

🏢 계정: {target_account}
📅 분석 기간: {start_date_str} ~ {end_date_str}

📊 주요 현황:
• EC2 인스턴스: {ec2_total}개
• S3 버킷: {s3_total}개  
• IAM 사용자: {iam_total}개
• 위험한 보안 그룹: {sg_risky}개

📋 상세 보고서: {html_url}"""
                        
                        emit_result({'summary': account_prefix + summary})
                    else:
                        emit_error('HTML 보고서 생성에 실패했습니다.')
                    
                except Exception as e:
                    print(f"[ERROR] 월간 보고서 생성 중 오류: {str(e)}", flush=True)
                    import traceback
                    traceback.print_exc()
                    emit_error(f'보고서 생성 중 오류가 발생했습니다: {str(e)}')
                    return  # 오류 발생 시 함수 종료
                
            else:
                # 일반 질문 처리 - 실제 Q CLI 실행
                emit_progress(70, 'AWS API를 호출하고 있습니다...')
                
                emit_progress(90, 'AI가 결과를 분석하고 있습니다...')
                
                # 실제 Q CLI 실행
                print(f"[DEBUG] Q CLI 실행 시작 - 질문 유형: {question_type}", flush=True)
                
                try:
                    # Q CLI 경로 자동 감지 (권한에 따라)
                    q_paths = [
                        '/home/ec2-user/.local/bin/q',  # ec2-user 우선
                        '/root/.local/bin/q',           # root 경로
                        '/usr/local/bin/q',             # 시스템 경로
                        'q'                             # PATH에서 찾기
                    ]
                    
                    q_cmd = None
                    for path in q_paths:
                        try:
                            if path == 'q':
                                # PATH에서 찾기
                                result = subprocess.run(['which', 'q'], capture_output=True, text=True)
                                if result.returncode == 0:
                                    q_cmd = 'q'
                                    break
                            elif os.path.exists(path) and os.access(path, os.X_OK):
                                q_cmd = path
                                break
                        except Exception as e:
                            print(f"[DEBUG] 경로 {path} 확인 실패: {e}", flush=True)
                            continue
                    
                    if not q_cmd:
                        raise FileNotFoundError("실행 가능한 Q CLI를 찾을 수 없습니다")
                    
                    # Q CLI 실행 전 환경 변수 디버깅
                    print(f"[DEBUG] Q CLI 실행 환경:", flush=True)
                    print(f"[DEBUG] - 명령어: {q_cmd}", flush=True)
                    print(f"[DEBUG] - AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:10]}...", flush=True)
                    print(f"[DEBUG] - AWS_DEFAULT_REGION: {env_vars.get('AWS_DEFAULT_REGION', 'None')}", flush=True)
                    print(f"[DEBUG] - 질문 길이: {len(korean_prompt)}", flush=True)
                    
                    # Q CLI 실행 (Slack bot과 동일한 명령어 및 타임아웃)
                    cmd = [q_cmd, 'chat', '--no-interactive', '--trust-all-tools', korean_prompt]
                    print(f"[DEBUG] 실행 명령어: {' '.join(cmd)}", flush=True)
                    print(f"[DEBUG] 타임아웃 설정: 600초 (질문 유형: {question_type})", flush=True)
                    
                    q_result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        env=env_vars,
                        timeout=600  # Slack bot과 동일한 10분 타임아웃
                    )
                    
                    print(f"[DEBUG] Q CLI 실행 완료:", flush=True)
                    print(f"[DEBUG] - 반환 코드: {q_result.returncode}", flush=True)
                    print(f"[DEBUG] - stdout 길이: {len(q_result.stdout) if q_result.stdout else 0}", flush=True)
                    print(f"[DEBUG] - stderr 길이: {len(q_result.stderr) if q_result.stderr else 0}", flush=True)
                    
                    if q_result.stderr:
                        print(f"[DEBUG] Q CLI stderr: {q_result.stderr[:500]}", flush=True)
                    
                    if q_result.returncode == 0 and q_result.stdout.strip():
                        # 성공적인 응답
                        clean_response = simple_clean_output(q_result.stdout.strip())
                        print(f"[DEBUG] Q CLI 응답 성공 (길이: {len(clean_response)})", flush=True)
                        
                        emit_progress(100, '분석이 완료되었습니다!')
                        emit_result({'summary': account_prefix + clean_response})
                    else:
                        # Q CLI 실행 실패
                        error_msg = q_result.stderr.strip() if q_result.stderr else "Q CLI 실행 실패"
                        print(f"[ERROR] Q CLI 실행 실패:", flush=True)
                        print(f"[ERROR] - 반환 코드: {q_result.returncode}", flush=True)
                        print(f"[ERROR] - 에러 메시지: {error_msg}", flush=True)
                        
                        # 폴백: AWS CLI로 실제 리소스 조회
                        try:
                            print(f"[DEBUG] Q CLI 실패, AWS CLI로 폴백 시도", flush=True)
                            
                            # 기본 계정 정보 조회
                            aws_result = subprocess.run(
                                ['aws', 'sts', 'get-caller-identity'],
                                capture_output=True,
                                text=True,
                                env=env_vars,
                                timeout=30
                            )
                            
                            if aws_result.returncode == 0:
                                caller_info = json.loads(aws_result.stdout)
                                account = caller_info.get('Account', 'Unknown')
                                user_arn = caller_info.get('Arn', 'Unknown')
                                
                                # 질문에 따라 실제 AWS 리소스 조회 (Slack bot 수준 상세 정보)
                                resource_info = ""
                                if any(keyword in query.lower() for keyword in ['ec2', '인스턴스', 'instance', '러닝', 'running']):
                                    # EC2 인스턴스 상세 조회 (JSON 형태로)
                                    try:
                                        ec2_result = subprocess.run(
                                            ['aws', 'ec2', 'describe-instances', 
                                             '--filters', 'Name=instance-state-name,Values=running',
                                             '--output', 'json'],
                                            capture_output=True,
                                            text=True,
                                            env=env_vars,
                                            timeout=30
                                        )
                                        if ec2_result.returncode == 0:
                                            ec2_data = json.loads(ec2_result.stdout)
                                            instances = []
                                            
                                            for reservation in ec2_data.get('Reservations', []):
                                                for instance in reservation.get('Instances', []):
                                                    # 인스턴스 이름 추출
                                                    instance_name = "이름 없음"
                                                    for tag in instance.get('Tags', []):
                                                        if tag.get('Key') == 'Name':
                                                            instance_name = tag.get('Value', '이름 없음')
                                                            break
                                                    
                                                    # 보안 그룹 정보 추출
                                                    security_groups = []
                                                    for sg in instance.get('SecurityGroups', []):
                                                        sg_name = sg.get('GroupName', 'Unknown')
                                                        sg_id = sg.get('GroupId', 'Unknown')
                                                        security_groups.append(f"{sg_name} ({sg_id})")
                                                    
                                                    # IAM 역할 추출
                                                    iam_role = "없음"
                                                    if instance.get('IamInstanceProfile'):
                                                        iam_arn = instance['IamInstanceProfile'].get('Arn', '')
                                                        if '/' in iam_arn:
                                                            iam_role = iam_arn.split('/')[-1]
                                                    
                                                    instance_info = f"""🖥️ **{instance_name}**
• **인스턴스 ID**: {instance.get('InstanceId', 'Unknown')}
• **상태**: ✅ {instance.get('State', {}).get('Name', 'Unknown')}
• **인스턴스 타입**: {instance.get('InstanceType', 'Unknown')}
• **시작 시간**: {instance.get('LaunchTime', 'Unknown')}
• **가용 영역**: {instance.get('Placement', {}).get('AvailabilityZone', 'Unknown')}

**네트워크 정보**:
• **프라이빗 IP**: {instance.get('PrivateIpAddress', '없음')}
• **퍼블릭 IP**: {instance.get('PublicIpAddress', '없음')}
• **VPC ID**: {instance.get('VpcId', 'Unknown')}
• **서브넷 ID**: {instance.get('SubnetId', 'Unknown')}
• **보안 그룹**: {', '.join(security_groups) if security_groups else '없음'}

**기타 정보**:
• **키 페어**: {instance.get('KeyName', '없음')}
• **IAM 역할**: {iam_role}
• **플랫폼**: {instance.get('Platform', 'Linux/UNIX')}
• **모니터링**: {'활성화' if instance.get('Monitoring', {}).get('State') == 'enabled' else '비활성화'}
• **EBS 최적화**: {'활성화' if instance.get('EbsOptimized', False) else '비활성화'}
"""
                                                    instances.append(instance_info)
                                            
                                            if instances:
                                                total_count = len(instances)
                                                resource_info = f"\n\n📊 **총 {total_count}개 인스턴스 실행 중**:\n\n" + "\n\n".join(instances)
                                                resource_info += f"\n\n💡 **추가 정보가 필요하시면 특정 인스턴스 ID를 말씀해주세요!**"
                                            else:
                                                resource_info = f"\n\n📭 **실행 중인 EC2 인스턴스가 없습니다.**"
                                        else:
                                            resource_info = f"\n\n⚠️ EC2 인스턴스 조회 실패: {ec2_result.stderr[:200]}"
                                    except Exception as e:
                                        resource_info = f"\n\n⚠️ EC2 조회 중 오류: {str(e)}"
                                
                                fallback_response = f"""✅ AWS 리소스 조회 완료

질문: {query}
유형: {question_type}

🔍 현재 AWS 환경:
• 계정 ID: {account}
• 사용자: {user_arn}
• 리전: {env_vars.get('AWS_DEFAULT_REGION', 'ap-northeast-2')}

{resource_info}

💡 Q CLI가 정상 작동하면 더 자세한 AI 분석이 가능합니다:
• 리소스 상세 분석 및 권장사항
• 보안 취약점 분석
• 비용 최적화 제안
• CloudTrail 이벤트 분석"""
                            else:
                                fallback_response = f"""⚠️ AWS 접근 확인 필요

질문: {query}
유형: {question_type}

현재 상태:
• Q CLI: 설치 필요
• AWS CLI: 설정 확인 필요

설치 가이드:
1. Q CLI 설치: curl -sSL https://install.q.dev | bash
2. AWS 자격증명 확인
3. 서비스 재시작"""
                            
                        except Exception as aws_error:
                            print(f"[ERROR] AWS CLI 폴백도 실패: {aws_error}", flush=True)
                            fallback_response = f"""⚠️ 시스템 설정 확인 필요

질문: {query}

현재 상태:
• Q CLI: 미설치
• AWS CLI: 설정 확인 필요

관리자에게 문의하여 다음을 설치해주세요:
1. Q CLI 설치 및 로그인
2. AWS 자격증명 설정
3. 컨텍스트 파일 복사"""
                        
                        emit_progress(100, '기본 분석이 완료되었습니다.')
                        emit_result({'summary': account_prefix + fallback_response})
                
                except subprocess.TimeoutExpired:
                    print(f"[ERROR] Q CLI 타임아웃 (5분)", flush=True)
                    timeout_response = f"""⏰ 분석 시간이 초과되었습니다.

질문: {query}

복잡한 분석의 경우 시간이 오래 걸릴 수 있습니다. 
더 구체적인 질문으로 다시 시도해보세요."""
                    
                    emit_progress(100, '시간 초과로 분석을 중단했습니다.')
                    emit_result({'summary': account_prefix + timeout_response})
                
                except Exception as e:
                    print(f"[ERROR] Q CLI 실행 중 예외: {str(e)}", flush=True)
                    error_response = f"""❌ 분석 중 오류가 발생했습니다.

질문: {query}
오류: {str(e)}

시스템 관리자에게 문의하거나 잠시 후 다시 시도해주세요."""
                    
                    emit_progress(100, '오류가 발생했습니다.')
                    emit_result({'summary': account_prefix + error_response})
        
    except Exception as e:
        print(f"[ERROR] AWS 질문 처리 중 오류: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        emit_error(f'처리 중 오류가 발생했습니다: {str(e)}')
    finally:
        # 정리 작업
        processing_questions.discard(question_key)
        current_progress.pop(question_key, None)  # 진행 상태도 정리
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[DEBUG] 임시 디렉터리 삭제: {temp_dir}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)

@app.before_request
def handle_preflight():
    """OPTIONS 요청 처리 (CORS preflight)"""
    from flask import request, make_response
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add('Access-Control-Allow-Headers', "*")
        response.headers.add('Access-Control-Allow-Methods', "*")
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response

@app.after_request
def after_request(response):
    """모든 응답에 CORS 헤더 추가"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With,Accept,Origin,Access-Control-Request-Method,Access-Control-Request-Headers')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS,HEAD')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '86400')
    return response

@app.route('/health')
def health_check():
    """헬스 체크 엔드포인트"""
    return {'status': 'healthy', 'service': 'Saltware AWS Assistant WebSocket Server'}

@app.route('/zendesk/health')
def zendesk_health_check():
    """Zendesk WebSocket 헬스 체크 엔드포인트"""
    return {'status': 'healthy', 'service': 'Zendesk WebSocket Server'}



if __name__ == '__main__':
    print("🚀 Saltware AWS Assistant WebSocket Server 시작")
    print("📡 WebSocket 서버: http://localhost:3001")
    print("🔗 Zendesk 앱에서 연결 가능")
    
    # 개발 모드로 실행 (디버그 활성화)
    socketio.run(app, host='0.0.0.0', port=3001, debug=False, allow_unsafe_werkzeug=True)