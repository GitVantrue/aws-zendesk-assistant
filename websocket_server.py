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
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True, path='/zendesk/socket.io')

# 처리 중인 질문 추적
processing_questions = set()

# 활성 세션 추적
active_sessions = set()

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
                RoleSessionName=f"WebSocketBot-{account_id}"
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
                RoleSessionName=f"WebSocketBot-{account_id}",
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
    """출력 텍스트 간단 정리"""
    # ANSI 색상 코드 제거
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    
    # 불필요한 공백 정리
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text

@socketio.on('connect', namespace='/zendesk')
def handle_connect():
    """클라이언트 연결 시"""
    from flask import request
    print(f"[DEBUG] 클라이언트 연결됨: {request.sid}", flush=True)
    active_sessions.add(request.sid)
    print(f"[DEBUG] 활성 세션 목록: {active_sessions}", flush=True)
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
        """클라이언트에게 이벤트 전송하는 통합 헬퍼 함수"""
        try:
            print(f"[DEBUG] 이벤트 전송: {event_type} -> 세션 {session_id}", flush=True)
            socketio.emit(event_type, data, room=session_id, namespace='/zendesk')
            # 이벤트 전송 후 잠시 대기 (버퍼링 방지)
            import time
            time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] 이벤트 전송 실패: {e}", flush=True)
    
    def emit_progress(progress, message):
        """진행률 전송 헬퍼 함수"""
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
        
        # 진행률 50% - AWS 분석 시작
        emit_progress(50, 'AWS 분석을 시작합니다...')
        
        # Service Screener 처리
        if question_type == 'screener':
            socketio.emit('progress', {'progress': 60, 'message': f'계정 {account_id} Service Screener 스캔을 시작합니다...'}, namespace='/zendesk')
            
            try:
                # 기존 Service Screener 결과 삭제 (새로운 스캔을 위해)
                old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
                if os.path.exists(old_result_dir):
                    print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
                    shutil.rmtree(old_result_dir)
                
                # Service Screener 직접 실행
                socketio.emit('progress', {'progress': 70, 'message': 'Service Screener를 실행하고 있습니다...'}, namespace='/zendesk')
                
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
                
                socketio.emit('progress', {'progress': 80, 'message': '스캔 결과를 분석하고 있습니다...'}, namespace='/zendesk')
                
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
                    
                    socketio.emit('progress', {'progress': 100, 'message': '스캔이 완료되었습니다!'}, namespace='/zendesk')
                    socketio.emit('result', {
                        'summary': summary,
                        'reports': [
                            {
                                'name': 'Service Screener 상세 보고서',
                                'url': report_url
                            }
                        ]
                    }, namespace='/zendesk')
                    
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
                    
                    socketio.emit('progress', {'progress': 100, 'message': '스캔 완료 (결과 확인 필요)'}, namespace='/zendesk')
                    socketio.emit('result', {'summary': error_summary}, namespace='/zendesk')
                    
            except subprocess.TimeoutExpired:
                print(f"[ERROR] Service Screener 타임아웃", flush=True)
                timeout_summary = f"""⏰ Service Screener 타임아웃

🏢 계정: {account_id}
스캔 시간이 10분을 초과하여 중단되었습니다.
계정 규모가 큰 경우 더 오래 걸릴 수 있습니다."""
                
                socketio.emit('progress', {'progress': 100, 'message': '스캔 시간 초과'}, namespace='/zendesk')
                socketio.emit('result', {'summary': timeout_summary}, namespace='/zendesk')
                
            except Exception as e:
                print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                
                error_summary = f"""❌ Service Screener 실행 오류

🏢 계정: {account_id}
오류: {str(e)}

시스템 관리자에게 문의하거나 잠시 후 다시 시도해주세요."""
                
                socketio.emit('progress', {'progress': 100, 'message': '스캔 실행 오류'}, namespace='/zendesk')
                socketio.emit('result', {'summary': error_summary}, namespace='/zendesk')
            
        else:
            # 일반 질문 처리 - 실제 Q CLI 실행
            emit_progress(70, 'AWS API를 호출하고 있습니다...')
            
            # 컨텍스트 파일 로드
            context_content = load_context_file(context_path) if context_path else ""
            
            # 한국어 프롬프트 구성
            korean_prompt = f"""다음 컨텍스트를 참고하여 질문에 답변해주세요:

{context_content}

=== 사용자 질문 ===
{query}

위 컨텍스트의 가이드라인을 따라 한국어로 답변해주세요."""
            
            emit_progress(90, 'AI가 결과를 분석하고 있습니다...')
            
            # 실제 Q CLI 실행
            print(f"[DEBUG] Q CLI 실행 시작 - 질문 유형: {question_type}", flush=True)
            
            try:
                # Q CLI 경로 확인 (여러 경로 시도)
                q_paths = [
                    '/root/.local/bin/q',
                    '/home/ec2-user/.local/bin/q', 
                    '/usr/local/bin/q',
                    'q'  # PATH에서 찾기
                ]
                
                q_cmd = None
                for path in q_paths:
                    if path == 'q' or os.path.exists(path):
                        q_cmd = path
                        print(f"[DEBUG] Q CLI 경로 발견: {q_cmd}", flush=True)
                        break
                
                if not q_cmd:
                    raise FileNotFoundError("Q CLI를 찾을 수 없습니다")
                
                # Q CLI 실행 (실제 AWS 분석)
                q_result = subprocess.run(
                    [q_cmd, 'chat', '--no-interactive', korean_prompt],
                    capture_output=True,
                    text=True,
                    env=env_vars,
                    timeout=300  # 5분 타임아웃
                )
                
                if q_result.returncode == 0 and q_result.stdout.strip():
                    # 성공적인 응답
                    clean_response = simple_clean_output(q_result.stdout.strip())
                    print(f"[DEBUG] Q CLI 응답 성공 (길이: {len(clean_response)})", flush=True)
                    
                    emit_progress(100, '분석이 완료되었습니다!')
                    emit_result({'summary': account_prefix + clean_response})
                else:
                    # Q CLI 실행 실패
                    error_msg = q_result.stderr.strip() if q_result.stderr else "Q CLI 실행 실패"
                    print(f"[ERROR] Q CLI 실행 실패: {error_msg}", flush=True)
                    
                    # 폴백: AWS CLI로 기본 정보 조회
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
                            
                            fallback_response = f"""✅ AWS 기본 정보 조회 완료

질문: {query}
유형: {question_type}

🔍 현재 AWS 환경:
• 계정 ID: {account}
• 사용자: {user_arn}
• 리전: {env_vars.get('AWS_DEFAULT_REGION', 'ap-northeast-2')}

💡 Q CLI가 설치되면 더 자세한 분석이 가능합니다:
• 리소스 상세 분석
• 보안 권장사항
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
                    
                    socketio.emit('progress', {'progress': 100, 'message': '기본 분석이 완료되었습니다.'}, namespace='/zendesk')
                    socketio.emit('result', {'summary': account_prefix + fallback_response}, namespace='/zendesk')
                    
            except subprocess.TimeoutExpired:
                print(f"[ERROR] Q CLI 타임아웃 (5분)", flush=True)
                timeout_response = f"""⏰ 분석 시간이 초과되었습니다.

질문: {query}

복잡한 분석의 경우 시간이 오래 걸릴 수 있습니다. 
더 구체적인 질문으로 다시 시도해보세요."""
                
                socketio.emit('progress', {'progress': 100, 'message': '시간 초과로 분석을 중단했습니다.'}, namespace='/zendesk')
                socketio.emit('result', {'summary': account_prefix + timeout_response}, namespace='/zendesk')
                
            except Exception as e:
                print(f"[ERROR] Q CLI 실행 중 예외: {str(e)}", flush=True)
                error_response = f"""❌ 분석 중 오류가 발생했습니다.

질문: {query}
오류: {str(e)}

시스템 관리자에게 문의하거나 잠시 후 다시 시도해주세요."""
                
                socketio.emit('progress', {'progress': 100, 'message': '오류가 발생했습니다.'}, namespace='/zendesk')
                socketio.emit('result', {'summary': account_prefix + error_response}, namespace='/zendesk')
        
    except Exception as e:
        print(f"[ERROR] AWS 질문 처리 중 오류: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        socketio.emit('error', {'message': f'처리 중 오류가 발생했습니다: {str(e)}'}, namespace='/zendesk')
    finally:
        # 정리 작업
        processing_questions.discard(question_key)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[DEBUG] 임시 디렉터리 삭제: {temp_dir}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)

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