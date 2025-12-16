import os
import json
import subprocess
import threading
import re
import boto3
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
BOT_USER_ID = 'U09R4V8QZ6U'

# 처리 중인 질문 추적
processing_questions = set()

# /tmp/reports 디렉터리 생성
os.makedirs('/tmp/reports', exist_ok=True)

def convert_datetime_to_json_serializable(obj):
    """
    datetime 객체를 JSON 직렬화 가능한 형식으로 변환하는 재귀 함수

    Args:
        obj: 변환할 Python 객체 (dict, list, datetime 등)

    Returns:
        JSON 직렬화 가능한 객체
    """
    if isinstance(obj, (datetime, date)):
        # datetime 또는 date 객체를 ISO 8601 형식 문자열로 변환
        return obj.isoformat()
    elif isinstance(obj, dict):
        # 딕셔너리의 모든 값을 재귀적으로 변환
        return {key: convert_datetime_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # 리스트의 모든 요소를 재귀적으로 변환
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        # 튜플을 리스트로 변환하고 재귀적으로 처리
        return [convert_datetime_to_json_serializable(item) for item in obj]
    elif isinstance(obj, set):
        # 세트를 리스트로 변환하고 재귀적으로 처리
        return [convert_datetime_to_json_serializable(item) for item in obj]
    else:
        # 기타 타입은 그대로 반환 (str, int, float, bool, None 등)
        return obj

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/reports/<path:filepath>')
def serve_report(filepath):
    """HTML 보고서 파일 제공 (하위 디렉터리 포함)"""
    try:
        from flask import send_from_directory
        return send_from_directory('/tmp/reports', filepath)
    except Exception as e:
        print(f"[ERROR] 파일 서빙 실패: {filepath} - {e}", flush=True)
        return "파일을 찾을 수 없습니다.", 404

@app.route('/slack/events', methods=['POST'])
def slack_events():
    try:
        data = request.json
        print(f"[DEBUG] 이벤트 수신: {data}", flush=True)

        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data.get('challenge')})

        if data.get('type') == 'event_callback':
            event = data.get('event', {})

            # 봇 자신의 메시지만 무시 (bot_id나 bot_profile이 있는 경우)
            if (event.get('bot_id') or event.get('bot_profile', {}).get('id')):
                print(f"[DEBUG] 봇 메시지 무시", flush=True)
                return '', 200

            if event.get('type') != 'message':
                return '', 200

            channel_type = event.get('channel_type', '')
            text = event.get('text', '')

            if channel_type != 'im':
                if f'<@{BOT_USER_ID}>' not in text:
                    return '', 200
                text = text.replace(f'<@{BOT_USER_ID}>', '').strip()

            if not text:
                return '', 200

            # 타임스탬프 기반 중복 방지
            event_ts = event.get('ts', '')
            question_key = f"{event.get('channel')}:{event_ts}"

            if question_key in processing_questions:
                print(f"[DEBUG] 중복 이벤트 무시: {question_key}", flush=True)
                return '', 200

            print(f"[DEBUG] 새 질문 처리: {question_key}", flush=True)
            print(f"[DEBUG] 질문 내용: {text}", flush=True)
            processing_questions.add(question_key)

            channel = event.get('channel')

            # 즉시 처리 중 메시지 전송
            send_message(channel, "🔄 요청을 처리하고 있습니다. 잠시만 기다려주세요...")

            thread = threading.Thread(target=process_question_async, args=(channel, text, question_key))
            thread.daemon = True
            thread.start()

        return '', 200
    except Exception as e:
        print(f"[ERROR] Slack 이벤트 처리 중 오류: {str(e)}", flush=True)
        return '', 500

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
    account_pattern = r'\d{12}'  # 단어 경계 제거
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
                RoleSessionName=f"SlackBot-{account_id}"
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
                RoleSessionName="SlackBot-CrossAccount",
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
                RoleSessionName=f"SlackBot-{account_id}",
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
        return 'report', '/root/core_contexts/security_report.md'

    # 우선순위 3: CloudTrail/감사 관련 (활동 추적)
    cloudtrail_keywords = ['cloudtrail', '추적', '누가', '언제', '활동', '이벤트', '로그인', '이력', '히스토리', 'history']
    cloudtrail_phrases = ['감사', '종료했', '삭제했', '생성했', '변경했', '수정했', '수정한', '변경한', '삭제한', '생성한', '종료한',
                          '수정사항', '변경사항', '삭제사항', '생성사항', '바꿨', '지웠', '만들었']
    if (any(keyword in question_lower for keyword in cloudtrail_keywords) or
        any(phrase in question_lower for phrase in cloudtrail_phrases)):
        return 'cloudtrail', '/root/core_contexts/cloudtrail_mcp.md'

    # 우선순위 4: CloudWatch/모니터링 관련
    cloudwatch_keywords = ['cloudwatch', '모니터링', '알람', '메트릭', 'dashboard', '성능', '로그 그룹', '지표', 'metric', 'cpu', '메모리', '디스크']
    if any(keyword in question_lower for keyword in cloudwatch_keywords):
        return 'cloudwatch', '/root/core_contexts/cloudwatch_mcp.md'

    # 우선순위 5: 일반 AWS 질문
    print(f"[DEBUG] 질문 타입: general", flush=True)
    return 'general', '/root/core_contexts/general_aws.md'


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


def cleanup_old_screener_results(days_to_keep=3):
    """
    오래된 보고서 및 스캔 결과 정리

    Args:
        days_to_keep (int): 보관할 일수 (기본 7일)
    """
    try:
        cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 3600)
        deleted_count = 0

        # 1. Service Screener 원본 결과 정리 (/root/service-screener-v2/aws/)
        screener_dir = '/root/service-screener-v2/aws'
        if os.path.exists(screener_dir):
            for account_dir in os.listdir(screener_dir):
                account_path = os.path.join(screener_dir, account_dir)
                if os.path.isdir(account_path):
                    # 디렉터리 수정 시간 확인
                    if os.path.getmtime(account_path) < cutoff_time:
                        print(f"[DEBUG] 오래된 스캔 결과 삭제: {account_path}", flush=True)
                        import shutil
                        shutil.rmtree(account_path)
                        deleted_count += 1

        # 2. /tmp/reports/ 모든 보고서 정리
        tmp_reports_dir = '/tmp/reports'
        if os.path.exists(tmp_reports_dir):
            for item in os.listdir(tmp_reports_dir):
                item_path = os.path.join(tmp_reports_dir, item)

                # res 디렉터리는 유지 (공통 리소스)
                if item == 'res':
                    continue

                # 디렉터리 정리 (screener_*, wa_*)
                if os.path.isdir(item_path):
                    if item.startswith('screener_') or item.startswith('wa_'):
                        if os.path.getmtime(item_path) < cutoff_time:
                            print(f"[DEBUG] 오래된 보고서 디렉터리 삭제: {item_path}", flush=True)
                            import shutil
                            shutil.rmtree(item_path)
                            deleted_count += 1

                # 파일 정리 (aws_report_*.html, wa_summary_*.html)
                elif os.path.isfile(item_path):
                    if item.startswith('aws_report_') or item.startswith('wa_summary_'):
                        if os.path.getmtime(item_path) < cutoff_time:
                            print(f"[DEBUG] 오래된 보고서 파일 삭제: {item_path}", flush=True)
                            os.remove(item_path)
                            deleted_count += 1

        if deleted_count > 0:
            print(f"[DEBUG] {deleted_count}개의 오래된 보고서 삭제 완료", flush=True)

    except Exception as e:
        print(f"[ERROR] 보고서 정리 중 오류: {str(e)}", flush=True)


def run_service_screener(channel, account_id, env_vars, question_key):
    """
    Service Screener를 실행하여 AWS 계정 스캔

    Args:
        channel (str): Slack 채널 ID
        account_id (str): AWS 계정 ID
        env_vars (dict): 환경 변수 (cross-account 자격증명 포함)
        question_key (str): 질문 고유 키
    """
    # 스캔 시작 전 오래된 결과 정리
    cleanup_old_screener_results(days_to_keep=7)
    try:
        print(f"[DEBUG] Service Screener 실행 시작: 계정 {account_id}", flush=True)

        # 1. 현재 계정 스캔 설정 (이미 assume role 완료된 자격증명 사용)
        # crossAccounts.json에서 IncludeThisAccount를 true로 설정
        # 기본 리전: 서울(ap-northeast-2), 버지니아(us-east-1)
        temp_json_path = f'/tmp/crossAccounts_{account_id}_{question_key.replace(":", "_")}.json'

        # 질문에서 추가 리전 추출 (예: "ap-southeast-1 리전도 스캔해줘")
        default_regions = ['ap-northeast-2', 'us-east-1']  # 서울, 버지니아
        additional_regions = []

        # AWS 리전 패턴 매칭
        region_pattern = r'\b(us|eu|ap|sa|ca|me|af)-(north|south|east|west|central|northeast|southeast)-\d\b'
        found_regions = re.findall(region_pattern, question.lower())
        if found_regions:
            # 튜플을 문자열로 변환
            additional_regions = [f"{r[0]}-{r[1]}-{r[2]}" for r in found_regions]
            additional_regions = [r for r in additional_regions if r not in default_regions]

        # 최종 리전 리스트
        scan_regions = default_regions + additional_regions

        cross_accounts_config = {
            "general": {
                "IncludeThisAccount": True,  # 현재 자격증명으로 스캔
                "Regions": scan_regions  # 스캔할 리전 목록
            }
        }

        with open(temp_json_path, 'w') as f:
            json.dump(cross_accounts_config, f, indent=2)

        print(f"[DEBUG] 스캔 대상 리전: {', '.join(scan_regions)}", flush=True)

        print(f"[DEBUG] crossAccounts.json 생성 완료: {temp_json_path}", flush=True)
        print(f"[DEBUG] 환경 변수 확인: AWS_ACCESS_KEY_ID={env_vars.get('AWS_ACCESS_KEY_ID', 'N/A')[:20]}...", flush=True)
        print(f"[DEBUG] 환경 변수 확인: AWS_SESSION_TOKEN 존재={bool(env_vars.get('AWS_SESSION_TOKEN'))}", flush=True)

        # EC2 메타데이터 서비스 비활성화 (환경 변수 자격증명 우선 사용)
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
        print(f"[DEBUG] EC2 메타데이터 비활성화 설정", flush=True)

        # 2. 사용자에게 시작 메시지 전송
        region_text = ', '.join(scan_regions)
        send_message(channel, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: {region_text}\n⏱️ 약 2-5분 소요될 수 있습니다.")

        # 3. Service Screener 실행
        screener_path = '/root/service-screener-v2/Screener.py'
        output_dir = f'screener_output_{account_id}_{question_key.replace(":", "_")}'

        cmd = [
            'python3',
            screener_path,
            '--crossAccounts', temp_json_path
        ]

        print(f"[DEBUG] 실행 명령어: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] 작업 디렉터리: /root/service-screener-v2", flush=True)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=600,  # 10분 타임아웃
            cwd='/root/service-screener-v2'
        )

        print(f"[DEBUG] Service Screener 완료. 반환코드: {result.returncode}", flush=True)
        print(f"[DEBUG] stdout (처음 1000자): {result.stdout[:1000]}", flush=True)
        print(f"[DEBUG] stderr (처음 1000자): {result.stderr[:1000]}", flush=True)

        # 4. 결과 처리
        if result.returncode == 0:
            # 성공 - 결과 파싱 및 전송
            # Service Screener는 adminlte/aws/{account_id}/ 디렉터리에 결과 생성
            screener_dir = '/root/service-screener-v2'
            account_result_dir = os.path.join(screener_dir, 'adminlte', 'aws', account_id)

            print(f"[DEBUG] 계정 결과 디렉터리 확인: {account_result_dir}", flush=True)

            if os.path.exists(account_result_dir):
                print(f"[DEBUG] 계정 디렉터리 발견: {account_result_dir}", flush=True)

                # index.html 찾기
                index_html_path = None
                for root, dirs, files in os.walk(account_result_dir):
                    for file in files:
                        if file.lower() == 'index.html':
                            index_html_path = os.path.join(root, file)
                            print(f"[DEBUG] index.html 발견: {index_html_path}", flush=True)
                            break
                    if index_html_path:
                        break

                if index_html_path:
                    # 전체 디렉토리를 /tmp/reports로 복사 (ALB를 통해 제공하기 위함)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"

                    import shutil
                    # 기존 디렉토리가 있으면 삭제
                    if os.path.exists(tmp_report_dir):
                        shutil.rmtree(tmp_report_dir)

                    # 전체 디렉토리 복사 (index.html이 있는 디렉토리)
                    source_dir = os.path.dirname(index_html_path)
                    shutil.copytree(source_dir, tmp_report_dir)
                    print(f"[DEBUG] 전체 디렉터리 복사 완료: {tmp_report_dir}", flush=True)

                    # res 디렉토리도 복사 (CSS/JS/이미지 파일들)
                    res_source = os.path.join(screener_dir, 'adminlte')
                    res_dest = os.path.join(tmp_report_dir, 'res')
                    print(f"[DEBUG] res 소스 경로 확인: {res_source}, 존재={os.path.exists(res_source)}", flush=True)
                    if os.path.exists(res_source):
                        if os.path.exists(res_dest):
                            shutil.rmtree(res_dest)
                        shutil.copytree(res_source, res_dest)
                        print(f"[DEBUG] res 디렉터리 복사 완료: {res_dest}", flush=True)
                    else:
                        print(f"[ERROR] res 소스 디렉터리를 찾을 수 없음: {res_source}", flush=True)
                        # 대체 경로 시도
                        alt_paths = [
                            '/root/service-screener-v2/res',
                            '/root/service-screener-v2/templates/res',
                            '/root/service-screener-v2/templates/adminlte'
                        ]
                        for alt_path in alt_paths:
                            print(f"[DEBUG] 대체 경로 확인: {alt_path}, 존재={os.path.exists(alt_path)}", flush=True)
                            if os.path.exists(alt_path):
                                shutil.copytree(alt_path, res_dest)
                                print(f"[DEBUG] 대체 경로에서 res 복사 완료: {alt_path} -> {res_dest}", flush=True)
                                break

                    # 요약 메시지 생성
                    summary = parse_screener_results(account_result_dir, account_id)
                    send_message(channel, f"✅ 스캔 완료!\n\n{summary}")

                    # Service Screener 보고서 URL 생성 및 전송
                    report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/screener_{account_id}_{timestamp}/index.html"
                    send_message(channel, f"📊 Service Screener 상세 보고서 (영문):\n{report_url}")
                    print(f"[DEBUG] Service Screener 보고서 URL 전송 완료: {report_url}", flush=True)

                    # Well-Architected 통합 보고서 생성
                    print(f"[DEBUG] Well-Architected 통합 보고서 생성 시작", flush=True)
                    wa_report_url = generate_wa_summary_report(account_id, account_result_dir, timestamp, channel)
                    if wa_report_url:
                        send_message(channel, f"📋 Well-Architected 통합 분석 보고서 (영문):\n{wa_report_url}")
                        print(f"[DEBUG] WA 보고서 URL 전송 완료: {wa_report_url}", flush=True)
                    else:
                        print(f"[DEBUG] WA 보고서 생성 실패 또는 스킵", flush=True)
                else:
                    print(f"[DEBUG] index.html을 찾을 수 없음", flush=True)
                    send_message(channel, f"✅ 스캔 완료!\n\n📊 계정 {account_id} 스캔이 완료되었으나 index.html을 찾을 수 없습니다.")
            else:
                print(f"[DEBUG] 계정 디렉터리 없음: {account_result_dir}", flush=True)
                send_message(channel, f"✅ 스캔 완료!\n\n📊 계정 {account_id} 스캔이 완료되었습니다.\n⚠️ 출력 디렉터리를 찾을 수 없습니다.")
        else:
            # 실패
            error_msg = result.stderr.strip() if result.stderr else "알 수 없는 오류"
            print(f"[ERROR] Service Screener 실패: {error_msg}", flush=True)
            send_message(channel, f"❌ 스캔 중 오류가 발생했습니다:\n```{error_msg[:500]}```")

        # 5. 임시 파일 정리
        try:
            os.remove(temp_json_path)
            print(f"[DEBUG] 임시 파일 삭제: {temp_json_path}", flush=True)
        except:
            pass

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Service Screener 타임아웃", flush=True)
        send_message(channel, "⏰ 스캔 시간이 초과되었습니다. (10분)")
    except Exception as e:
        print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        send_message(channel, f"❌ 스캔 실행 중 오류: {str(e)}")
    finally:
        processing_questions.discard(question_key)


def generate_wa_summary_report_async(account_id, screener_result_dir, timestamp, channel):
    """
    Well-Architected 통합 분석 보고서 생성 (비동기 버전)
    완료 후 자동으로 Slack에 메시지 전송

    Args:
        account_id (str): AWS 계정 ID
        screener_result_dir (str): Service Screener 결과 디렉터리
        timestamp (str): 타임스탬프
        channel (str): Slack 채널 ID
    """
    try:
        wa_report_url = generate_wa_summary_report(account_id, screener_result_dir, timestamp, channel)
        if wa_report_url:
            send_message(channel, f"✅ Well-Architected 통합 분석 보고서 생성 완료!\n📋 {wa_report_url}")
            print(f"[DEBUG] WA 보고서 URL 전송 완료: {wa_report_url}", flush=True)
        else:
            send_message(channel, "⚠️ Well-Architected 보고서 생성에 실패했습니다.")
            print(f"[DEBUG] WA 보고서 생성 실패", flush=True)
    except Exception as e:
        print(f"[ERROR] WA 보고서 비동기 생성 중 오류: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        send_message(channel, f"❌ Well-Architected 보고서 생성 중 오류가 발생했습니다: {str(e)}")


def generate_wa_summary_report(account_id, screener_result_dir, timestamp, channel):
    """
    Well-Architected 통합 분석 보고서 생성

    Args:
        account_id (str): AWS 계정 ID
        screener_result_dir (str): Service Screener 결과 디렉터리
        timestamp (str): 타임스탬프
        channel (str): Slack 채널 ID

    Returns:
        str: 보고서 URL 또는 None
    """
    try:
        # wa-ss-summarizer 경로 확인
        wa_summarizer_dir = '/root/wa-ss-summarizer'
        wa_script = os.path.join(wa_summarizer_dir, 'run_wa_summarizer.sh')

        if not os.path.exists(wa_script):
            print(f"[DEBUG] wa-ss-summarizer 스크립트 없음: {wa_script}", flush=True)
            return None

        # 실행 권한 확인 및 부여
        if not os.access(wa_script, os.X_OK):
            print(f"[DEBUG] wa-ss-summarizer 스크립트에 실행 권한 부여", flush=True)
            os.chmod(wa_script, 0o755)

        # 임시 디렉터리 생성 (해당 계정만 포함)
        temp_wa_input_dir = f"/tmp/wa_input_{account_id}_{timestamp}"
        os.makedirs(temp_wa_input_dir, exist_ok=True)

        # 해당 계정 폴더만 복사
        import shutil
        temp_account_dir = os.path.join(temp_wa_input_dir, account_id)
        shutil.copytree(screener_result_dir, temp_account_dir)
        print(f"[DEBUG] 계정 폴더 복사: {screener_result_dir} -> {temp_account_dir}", flush=True)

        # res 폴더 복사 (CSS/JS 등 공통 리소스)
        res_source = '/root/service-screener-v2/aws/res'
        res_dest = os.path.join(temp_wa_input_dir, 'res')
        if os.path.exists(res_source):
            shutil.copytree(res_source, res_dest)
            print(f"[DEBUG] res 폴더 복사: {res_source} -> {res_dest}", flush=True)

        # 출력 디렉터리는 wa-ss-summarizer의 기본 output 디렉터리 사용
        wa_output_dir = os.path.join(wa_summarizer_dir, 'output')
        os.makedirs(wa_output_dir, exist_ok=True)

        print(f"[DEBUG] WA Summarizer 실행: {wa_script} -d {temp_wa_input_dir}", flush=True)

        # wa-ss-summarizer 실행 (Q CLI PATH 추가 + 한국어 출력 설정)
        wa_env = os.environ.copy()
        wa_env['PATH'] = f"/root/.local/bin:{wa_env.get('PATH', '')}"
        # Q CLI에게 한국어로 응답하도록 지시
        wa_env['Q_LANGUAGE'] = 'Korean'
        wa_env['LANG'] = 'ko_KR.UTF-8'

        result = subprocess.run(
            [wa_script, '-d', temp_wa_input_dir],
            capture_output=True,
            text=True,
            timeout=900,  # 15분 타임아웃 (한국어 프롬프트 추가로 시간이 더 걸릴 수 있음)
            cwd=wa_summarizer_dir,
            env=wa_env
        )

        # 임시 디렉터리 정리
        try:
            shutil.rmtree(temp_wa_input_dir)
            print(f"[DEBUG] 임시 디렉터리 삭제: {temp_wa_input_dir}", flush=True)
        except Exception as e:
            print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)

        print(f"[DEBUG] WA Summarizer 완료. 반환코드: {result.returncode}", flush=True)
        if result.stdout:
            print(f"[DEBUG] WA stdout (전체): {result.stdout}", flush=True)
        if result.stderr:
            print(f"[DEBUG] WA stderr (전체): {result.stderr}", flush=True)

        if result.returncode == 0:
            # 생성된 HTML 파일 찾기 (최근 생성된 파일 기준)
            html_files = [f for f in os.listdir(wa_output_dir) if f.startswith('wa_summary_report_') and f.endswith('.html')]

            if html_files:
                # 파일 생성 시간 기준으로 가장 최근 파일 선택
                html_files_with_time = [(f, os.path.getmtime(os.path.join(wa_output_dir, f))) for f in html_files]
                html_files_with_time.sort(key=lambda x: x[1], reverse=True)
                html_file = html_files_with_time[0][0]
                html_path = os.path.join(wa_output_dir, html_file)

                print(f"[DEBUG] 최신 WA 보고서 파일 발견: {html_file}", flush=True)

                # /tmp/reports/로 복사 (Flask가 서빙할 수 있도록)
                dest_filename = f"wa_summary_{account_id}_{timestamp}.html"
                dest_path = f"/tmp/reports/{dest_filename}"

                import shutil
                shutil.copy(html_path, dest_path)
                print(f"[DEBUG] WA 보고서 복사 완료: {dest_path}", flush=True)

                # URL 생성
                wa_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{dest_filename}"
                return wa_url
            else:
                print(f"[DEBUG] WA 보고서 HTML 파일을 찾을 수 없음: {wa_output_dir}", flush=True)
                print(f"[DEBUG] 디렉터리 내용: {os.listdir(wa_output_dir) if os.path.exists(wa_output_dir) else '디렉터리 없음'}", flush=True)
                return None
        else:
            print(f"[ERROR] WA Summarizer 실패: {result.stderr[:500]}", flush=True)
            return None

    except subprocess.TimeoutExpired:
        print(f"[ERROR] WA Summarizer 타임아웃 (15분)", flush=True)
        return None
    except Exception as e:
        print(f"[ERROR] WA 보고서 생성 중 오류: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return None


def parse_screener_results(output_dir, account_id):
    """
    Service Screener 결과 파싱하여 요약 생성

    Args:
        output_dir (str): 출력 디렉터리 경로
        account_id (str): AWS 계정 ID

    Returns:
        str: 요약 메시지
    """
    try:
        # JSON 결과 파일 찾기
        json_files = []
        if os.path.exists(output_dir):
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.json') and 'result' in file.lower():
                        json_files.append(os.path.join(root, file))

        if not json_files:
            return f"📊 계정 {account_id} 스캔이 완료되었습니다.\n상세 결과는 첨부된 HTML 보고서를 확인하세요."

        # 첫 번째 JSON 파일 파싱
        with open(json_files[0], 'r') as f:
            data = json.load(f)

        # 요약 정보 추출
        total_resources = 0
        total_issues = 0
        critical_issues = 0
        high_issues = 0

        # 데이터 구조에 따라 파싱 (Service Screener 출력 형식에 맞춰 조정 필요)
        if isinstance(data, dict):
            for service, regions in data.items():
                if isinstance(regions, dict):
                    for region, resources in regions.items():
                        if isinstance(resources, dict):
                            total_resources += len(resources)
                            for resource_id, checks in resources.items():
                                if isinstance(checks, list):
                                    for check in checks:
                                        if isinstance(check, dict):
                                            severity = check.get('severity', '').lower()
                                            if severity in ['critical', 'high', 'medium', 'low']:
                                                total_issues += 1
                                                if severity == 'critical':
                                                    critical_issues += 1
                                                elif severity == 'high':
                                                    high_issues += 1

        summary = f"""📊 Service Screener 스캔 결과 요약

🏢 계정: {account_id}
📦 스캔된 리소스: {total_resources}개
⚠️ 발견된 이슈: {total_issues}개
  - 🔴 Critical: {critical_issues}개
  - 🟠 High: {high_issues}개

📄 상세 내용은 첨부된 HTML 보고서를 확인하세요."""

        return summary

    except Exception as e:
        print(f"[ERROR] 결과 파싱 실패: {str(e)}", flush=True)
        return f"📊 계정 {account_id} 스캔이 완료되었습니다.\n상세 결과는 첨부된 보고서를 확인하세요."


def process_question_async(channel, question, question_key):
    """비동기로 Q CLI 질문 처리 + HTML 보고서 생성 및 Slack 업로드"""
    temp_dir = None  # 정리용

    try:
        print(f"[DEBUG] 질문 처리 중: {question}", flush=True)

        # 계정 ID 추출
        account_id = extract_account_id(question)
        env_vars = os.environ.copy()

        # MCP 서버 초기화 타임아웃 설정 (밀리초)
        env_vars['Q_MCP_INIT_TIMEOUT'] = '10000'  # 10초

        account_prefix = ""

        if account_id:
            print(f"[DEBUG] 계정 ID 발견: {account_id}", flush=True)
            # Cross-account 세션 생성
            credentials = get_crossaccount_session(account_id)
            if credentials:
                # ========================================
                # 세션 격리: 임시 디렉터리 생성
                # ========================================
                import tempfile
                temp_dir = tempfile.mkdtemp(prefix=f'q_session_{account_id}_{question_key.replace(":", "_")}_')
                print(f"[DEBUG] 임시 세션 디렉터리 생성: {temp_dir}", flush=True)

                # ========================================
                # Q CLI 캐시 무효화
                # ========================================
                import shutil
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

                # ========================================
                # 환경 변수 설정 (AWS만 격리, Q CLI 로그인 유지)
                # ========================================
                # AWS 설정 파일 경로 격리 (HOME은 유지)
                env_vars['AWS_CONFIG_FILE'] = os.path.join(temp_dir, 'config')
                env_vars['AWS_SHARED_CREDENTIALS_FILE'] = os.path.join(temp_dir, 'credentials')

                # AWS 자격증명 직접 설정
                env_vars['AWS_ACCESS_KEY_ID'] = credentials['AWS_ACCESS_KEY_ID']
                env_vars['AWS_SECRET_ACCESS_KEY'] = credentials['AWS_SECRET_ACCESS_KEY']
                env_vars['AWS_SESSION_TOKEN'] = credentials['AWS_SESSION_TOKEN']
                env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'

                # 캐싱 및 메타데이터 비활성화
                env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
                env_vars['AWS_SDK_LOAD_CONFIG'] = '0'

                # 디버그 로그
                print(f"[DEBUG] 세션 격리 환경 설정 완료:", flush=True)
                print(f"[DEBUG] - AWS_CONFIG_FILE: {env_vars['AWS_CONFIG_FILE']}", flush=True)
                print(f"[DEBUG] - AWS_ACCESS_KEY_ID: {env_vars['AWS_ACCESS_KEY_ID'][:20]}...", flush=True)
                print(f"[DEBUG] - AWS_SESSION_TOKEN: {'설정됨' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)

                # ========================================
                # 계정 검증 (실행 전)
                # ========================================
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
                        send_message(channel, f"❌ 계정 자격증명 오류\n요청: {account_id}\n실제: {actual_account}")
                        return
                    else:
                        print(f"[DEBUG] ✅ 계정 검증 성공: {actual_account}", flush=True)
                else:
                    print(f"[ERROR] 계정 검증 실패: {verify_result.stderr}", flush=True)
                    send_message(channel, f"❌ 계정 검증 실패: {verify_result.stderr[:200]}")
                    return

                account_prefix = f"🏢 계정 {account_id} 결과:\n\n"
                question = re.sub(r'\b\d{12}\b', '', question).strip()
                question = re.sub(r'계정\s*', '', question).strip()
                question = re.sub(r'account\s*', '', question, flags=re.IGNORECASE).strip()
                print(f"[DEBUG] 정리된 질문: {question}", flush=True)
            else:
                print(f"[DEBUG] 계정 {account_id} 접근 실패", flush=True)
                send_message(channel, f"❌ 계정 {account_id}에 접근할 수 없습니다.")
                return

        # 질문 유형 분석
        question_type, context_path = analyze_question_type(question)
        print(f"[DEBUG] 질문 유형: {question_type}, 컨텍스트: {context_path}", flush=True)

        # Service Screener 처리 - 컨텍스트 파일 기반 오케스트레이션
        if question_type == 'screener':
            # 기존 Service Screener 결과 삭제 (Q CLI가 기존 결과를 읽지 못하게)
            old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
            if os.path.exists(old_result_dir):
                print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
                import shutil
                shutil.rmtree(old_result_dir)

            # Service Screener 컨텍스트 파일 로드
            screener_context_path = '/root/core_contexts/service_screener.md'
            screener_context = load_context_file(screener_context_path)

            # 컨텍스트 기반 프롬프트 구성 (계정 ID 강조 + 명확한 지시)
            korean_prompt = f"""다음 컨텍스트를 참고하여 AWS Service Screener를 실행해주세요:

{screener_context}

=== 필수 요구사항 ===
1. 반드시 계정 {account_id}에 대해서만 스캔하세요
2. 현재 환경 변수에 설정된 AWS 자격증명을 사용하세요 (이미 계정 {account_id}의 자격증명이 설정되어 있습니다)
3. Service Screener를 실제로 실행하세요 (기존 결과를 읽지 마세요)
4. 스캔 완료 후 /root/service-screener-v2/aws/{account_id}/ 디렉터리에 결과가 생성되어야 합니다

=== 사용자 질문 ===
{question}

위 요구사항을 반드시 따라 계정 {account_id}에 대해 Service Screener를 실행하고, 한국어로 상세한 보고서를 작성해주세요."""

            print(f"[DEBUG] 환경 변수 확인 - AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:10]}...", flush=True)
            print(f"[DEBUG] 환경 변수 확인 - AWS_SESSION_TOKEN 존재: {bool(env_vars.get('AWS_SESSION_TOKEN'))}", flush=True)

            # EC2 메타데이터 비활성화
            env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'

            send_message(channel, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: ap-northeast-2, us-east-1\n⏱️ 약 2-5분 소요될 수 있습니다.")

            # Service Screener 직접 실행 (main.py 방식)
            cmd = ['python3', '/root/service-screener-v2/main.py', '--regions', 'ap-northeast-2,us-east-1']
            print(f"[DEBUG] Service Screener 직접 실행: {' '.join(cmd)}", flush=True)

            log_file = f'/tmp/screener_{account_id}.log'
            with open(log_file, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=env_vars,
                    timeout=600,
                    cwd='/root/service-screener-v2'
                )

            print(f"[DEBUG] Service Screener 실행 완료. 반환코드: {result.returncode}", flush=True)

            # 로그 파일 내용 읽기
            try:
                with open(log_file, 'r') as f:
                    log_content = f.read()
                print(f"[DEBUG] Service Screener 로그 (마지막 1000자):\n{log_content[-1000:]}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 로그 파일 읽기 실패: {e}", flush=True)

            # Service Screener가 생성한 실제 결과 디렉터리 찾기
            screener_dir = '/root/service-screener-v2'
            # screener 명령어는 adminlte/aws/에 결과 저장
            account_result_dir = os.path.join(screener_dir, 'adminlte', 'aws', account_id)

            print(f"[DEBUG] Service Screener 결과 디렉터리 확인: {account_result_dir}", flush=True)

            if os.path.exists(account_result_dir):
                # Q CLI로 한글 요약 생성
                print(f"[DEBUG] Q CLI로 한글 요약 생성 시작", flush=True)
                korean_summary_prompt = f"""다음은 계정 {account_id}의 AWS Service Screener 스캔 결과입니다.

결과 디렉터리: {account_result_dir}

위 디렉터리의 결과를 분석하여 한국어로 다음 형식의 요약을 작성해주세요:

### 심각도별 이슈 분포
• Critical: X개 (즉시 조치 필요)
• High: X개 (높은 우선순위)
• Medium: X개 (중간 우선순위)
• Low: X개 (낮은 우선순위)

### 서비스별 주요 발견사항
각 서비스별로 주요 문제점과 권장 조치사항을 요약해주세요.

### 우선 조치 권장사항
즉시 조치, 단기 조치, 중장기 조치로 구분하여 작성해주세요."""

                q_result = subprocess.run(
                    ['/root/.local/bin/q', 'chat', '--no-interactive', korean_summary_prompt],
                    capture_output=True,
                    text=True,
                    env=env_vars,
                    timeout=300
                )

                if q_result.returncode == 0 and q_result.stdout.strip():
                    clean_response = simple_clean_output(q_result.stdout.strip())
                    send_message(channel, f"{account_prefix}{clean_response}")
                    print(f"[DEBUG] 한글 요약 전송 완료", flush=True)

                # 전체 디렉터리를 /tmp/reports/로 복사
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"

                import shutil
                # 기존 디렉터리가 있으면 삭제
                if os.path.exists(tmp_report_dir):
                    shutil.rmtree(tmp_report_dir)

                # 전체 디렉터리 복사
                shutil.copytree(account_result_dir, tmp_report_dir)
                print(f"[DEBUG] 전체 디렉터리 복사 완료: {tmp_report_dir}", flush=True)

                # res 디렉터리도 /tmp/reports/ 최상위에 복사 (../res/ 경로 참조 대응)
                # Service Screener는 adminlte/aws/res/에 res 폴더를 생성함
                screener_res_dir = '/root/service-screener-v2/adminlte/aws/res'
                tmp_res_dir = '/tmp/reports/res'
                print(f"[DEBUG] res 소스 경로: {screener_res_dir}, 존재={os.path.exists(screener_res_dir)}", flush=True)
                print(f"[DEBUG] res 대상 경로: {tmp_res_dir}, 존재={os.path.exists(tmp_res_dir)}", flush=True)

                if os.path.exists(screener_res_dir):
                    # 기존 res 폴더가 있으면 삭제하고 새로 복사
                    if os.path.exists(tmp_res_dir):
                        print(f"[DEBUG] 기존 res 디렉터리 삭제: {tmp_res_dir}", flush=True)
                        shutil.rmtree(tmp_res_dir)
                    shutil.copytree(screener_res_dir, tmp_res_dir)
                    print(f"[DEBUG] res 디렉터리 복사 완료: {tmp_res_dir}", flush=True)
                else:
                    print(f"[ERROR] res 소스 디렉터리를 찾을 수 없음: {screener_res_dir}", flush=True)

                # index.html 경로 확인
                index_html_path = os.path.join(tmp_report_dir, 'index.html')
                if os.path.exists(index_html_path):
                    # Service Screener 보고서 URL 전송
                    report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/screener_{account_id}_{timestamp}/index.html"
                    send_message(channel, f"📊 Service Screener 상세 보고서 (영문):\n{report_url}")
                    print(f"[DEBUG] Service Screener 보고서 URL 전송 완료: {report_url}", flush=True)

                    # Well-Architected 통합 보고서 생성 (백그라운드 스레드로 실행)
                    print(f"[DEBUG] Well-Architected 통합 보고서 생성 시작 (백그라운드)", flush=True)
                    send_message(channel, "⏳ Well-Architected 통합 분석 보고서를 생성 중입니다... (10-15분 소요 예상)")

                    # 백그라운드 스레드로 WA 보고서 생성
                    wa_thread = threading.Thread(
                        target=generate_wa_summary_report_async,
                        args=(account_id, account_result_dir, timestamp, channel)
                    )
                    wa_thread.daemon = True
                    wa_thread.start()
                    print(f"[DEBUG] WA 보고서 생성 백그라운드 스레드 시작됨", flush=True)

                else:
                    print(f"[DEBUG] index.html을 찾을 수 없음: {index_html_path}", flush=True)
                    send_message(channel, f"⚠️ Service Screener 실행은 완료되었으나 index.html을 찾을 수 없습니다.")
            else:
                print(f"[DEBUG] 계정 디렉터리 없음: {account_result_dir}", flush=True)
                send_message(channel, f"⚠️ Service Screener 실행은 완료되었으나 결과 디렉터리를 찾을 수 없습니다.")

            processing_questions.discard(question_key)
            return

        # 컨텍스트 파일 로드
        context_content = load_context_file(context_path)

        # Q CLI 실행
        print(f"[DEBUG] Q CLI 실행 시작 - 질문 유형: {question_type}", flush=True)

        # 날짜 추출 (AWS 리소스 조회 질문일 때만)
        now = datetime.now()
        target_account = account_id if account_id else "950027134314"

        # 질문에서 여러 월 추출 (9월, 10월 등)
        month_matches = re.findall(r'(\d{1,2})월', question)
        year_match = re.search(r'(\d{4})년?', question)

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

            analysis_period = (end_date - start_date).days + 1
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")

            # 월 범위 표시용
            if len(months) > 1:
                month_range_text = f"{start_month}월부터 {end_month}월까지"
            else:
                month_range_text = f"{start_month}월"
        else:
            # 월 정보 없으면 최근 30일
            start_date = now.date() - timedelta(days=30)
            end_date = now.date()
            analysis_period = 30
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
            month_range_text = None

        # 질문 유형에 따라 프롬프트 구성
        if question_type == 'report':
            # 타임스탬프 생성 (파일명용) - UTC+9 (한국 시간)
            from datetime import timezone
            kst = timezone(timedelta(hours=9))
            timestamp = datetime.now(kst).strftime("%Y%m%d_%H%M%S")

            raw_json_path = f"/tmp/reports/raw_security_data_{target_account}_{timestamp}.json"
            enriched_json_path = f"/tmp/reports/enriched_security_data_{target_account}_{timestamp}.json"

            # 1단계: boto3로 raw 데이터 수집
            print(f"[DEBUG] 📦 1단계: boto3로 raw 데이터 수집 시작", flush=True)
            print(f"[DEBUG] 분석 기간: {start_date_str} ~ {end_date_str} (UTC+9)", flush=True)
            send_message(channel, f"🔍 AWS 보안 데이터를 수집하고 있습니다...\n📅 분석 기간: {start_date_str} ~ {end_date_str}")

            try:
                # boto3로 raw 데이터 수집 (정확한 기간 포함, 자격증명 전달)
                raw_data = collect_raw_security_data(
                    target_account,
                    start_date_str,
                    end_date_str,
                    region='ap-northeast-2',
                    credentials=credentials if account_id else None
                )

                # Raw JSON 파일로 저장 (datetime 객체를 문자열로 변환)
                from datetime import datetime as dt

                def datetime_converter(obj):
                    """datetime 객체를 JSON 직렬화 가능한 문자열로 변환"""
                    if isinstance(obj, (dt, date)):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                with open(raw_json_path, 'w', encoding='utf-8') as f:
                    json.dump(raw_data, f, indent=2, ensure_ascii=False, default=datetime_converter)
                print(f"[DEBUG] ✅ Raw JSON 저장 완료: {raw_json_path}", flush=True)

                # Raw JSON 파일 전송
                send_message(channel, f"✅ Raw 데이터 수집 완료!\n📁 파일: {raw_json_path}")

                # HTML 보고서 생성
                print(f"[DEBUG] 📊 HTML 보고서 생성 시작", flush=True)
                send_message(channel, "📊 HTML 보고서를 생성하고 있습니다...")

                html_report_path = generate_html_report(raw_json_path)
                if html_report_path:
                    print(f"[DEBUG] ✅ HTML 보고서 생성 완료: {html_report_path}", flush=True)

                    # HTML 보고서 URL 생성 (ALB를 통해 접근)
                    html_filename = os.path.basename(html_report_path)
                    html_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{html_filename}"

                    send_message(channel, f"✅ HTML 보고서 생성 완료!\n📋 {html_url}")
                else:
                    print(f"[ERROR] HTML 보고서 생성 실패", flush=True)
                    send_message(channel, "⚠️ HTML 보고서 생성에 실패했습니다.")

                # 처리 완료
                processing_questions.discard(question_key)
                return

            # 아래 코드는 Raw JSON 구조 확인 후 활성화 예정 (주석 처리됨)
            # '''
                # 2단계: Q CLI로 섹션별 AI 분석 (청크 방식)
                print(f"[DEBUG] 🤖 2단계: Q CLI로 섹션별 AI 분석 시작 (청크 방식)", flush=True)
                send_message(channel, "🤖 보안 전문가 AI가 데이터를 분석하고 있습니다... (약 2-3분 소요)")

                # Enriched 데이터 초기화 (raw 데이터 복사)
                # datetime 객체를 JSON 직렬화 가능한 형식으로 변환
                print(f"[DEBUG] datetime 객체 변환 시작", flush=True)
                serializable_raw_data = convert_datetime_to_json_serializable(raw_data)
                enriched_data = json.loads(json.dumps(serializable_raw_data))

                # 섹션별로 Q CLI 분석 수행
                sections_to_analyze = [
                    {
                        'name': 'Trusted Advisor',
                        'key': 'trusted_advisor',
                        'prompt_template': """다음은 Trusted Advisor 체크 결과입니다:

{data}

각 체크에 대해 다음 정보를 추가하여 enriched JSON을 생성하세요:
1. 위험도 설명 (한글)
2. 구체적인 조치 방법 (한글)
3. 우선순위 (critical/high/medium/low)
4. 예상 영향

원본 데이터 구조를 유지하면서 각 체크에 "risk_analysis", "remediation", "priority", "impact" 필드를 추가하세요.
JSON 형식으로만 응답하세요."""
                    },
                    {
                        'name': 'IAM 보안',
                        'key': 'iam_security',
                        'prompt_template': """다음은 IAM 보안 현황입니다:

{data}

각 이슈에 대해 다음 정보를 추가하여 enriched JSON을 생성하세요:
1. 위험 시나리오 (한글)
2. 설정 방법 (한글)
3. 우선순위

원본 데이터 구조를 유지하면서 각 이슈에 "risk_scenario", "how_to_fix", "priority" 필드를 추가하세요.
JSON 형식으로만 응답하세요."""
                    },
                    {
                        'name': '보안 그룹',
                        'key': 'security_groups',
                        'prompt_template': """다음은 보안 그룹 분석 결과입니다:

{data}

각 위험 규칙에 대해 다음 정보를 추가하여 enriched JSON을 생성하세요:
1. 공격 벡터 설명 (한글)
2. 수정 방법 (한글)
3. 위험도

원본 데이터 구조를 유지하면서 각 위험 규칙에 "attack_vector", "fix_method", "risk_level" 필드를 추가하세요.
JSON 형식으로만 응답하세요."""
                    }
                ]

                for section in sections_to_analyze:
                    section_name = section['name']
                    section_key = section['key']

                    print(f"[DEBUG] 📊 {section_name} 섹션 분석 중...", flush=True)

                    # 해당 섹션 데이터 추출
                    section_data = raw_data.get(section_key, {})

                    # 데이터가 없으면 스킵
                    if not section_data or (isinstance(section_data, dict) and not section_data.get('checks') and not section_data.get('issues') and not section_data.get('details')):
                        print(f"[DEBUG] {section_name} 데이터 없음, 스킵", flush=True)
                        continue

                    # 섹션 데이터를 JSON 문자열로 변환 (datetime 객체 처리)
                    serializable_section_data = convert_datetime_to_json_serializable(section_data)
                    section_json = json.dumps(serializable_section_data, indent=2, ensure_ascii=False)

                    # 프롬프트 생성
                    prompt = section['prompt_template'].format(data=section_json)

                    # Q CLI 실행
                    try:
                        result = subprocess.run(
                            ['/root/.local/bin/q', 'chat', '--no-interactive', prompt],
                            capture_output=True,
                            text=True,
                            env=env_vars,
                            timeout=120  # 섹션당 2분
                        )

                        if result.returncode == 0 and result.stdout.strip():
                            # JSON 응답 파싱 시도
                            try:
                                # Q CLI 응답에서 JSON 부분만 추출
                                response_text = result.stdout.strip()

                                # JSON 블록 찾기 (```json ... ``` 또는 { ... })
                                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                                if json_match:
                                    enriched_section = json.loads(json_match.group(1))
                                else:
                                    # 직접 JSON 파싱 시도
                                    enriched_section = json.loads(response_text)

                                # Enriched 데이터 병합
                                enriched_data[section_key] = enriched_section
                                print(f"[DEBUG] ✅ {section_name} 분석 완료 및 병합", flush=True)

                            except json.JSONDecodeError as e:
                                print(f"[WARN] {section_name} JSON 파싱 실패: {e}, 원본 데이터 유지", flush=True)
                        else:
                            print(f"[WARN] {section_name} Q CLI 실행 실패, 원본 데이터 유지", flush=True)

                    except subprocess.TimeoutExpired:
                        print(f"[WARN] {section_name} 분석 타임아웃, 원본 데이터 유지", flush=True)
                    except Exception as e:
                        print(f"[WARN] {section_name} 분석 중 오류: {e}, 원본 데이터 유지", flush=True)

                # Enriched JSON 저장
                with open(enriched_json_path, 'w', encoding='utf-8') as f:
                    json.dump(enriched_data, f, indent=2, ensure_ascii=False, default=datetime_converter)
                print(f"[DEBUG] ✅ Enriched JSON 저장 완료: {enriched_json_path}", flush=True)

                # 3단계: Enriched JSON으로 HTML 생성
                print(f"[DEBUG] 📄 3단계: HTML 보고서 생성 시작", flush=True)

                # Enriched JSON 파일 확인 및 로드
                if not os.path.exists(enriched_json_path):
                    print(f"[WARN] Enriched JSON 파일이 생성되지 않음, Raw 데이터 사용: {enriched_json_path}", flush=True)
                    enriched_data = raw_data
                else:
                    # JSON 파일 읽기 및 에러 처리
                    try:
                        with open(enriched_json_path, 'r', encoding='utf-8') as f:
                            enriched_data = json.load(f)
                        print(f"[DEBUG] ✅ Enriched JSON 파싱 성공", flush=True)

                        # 데이터 유효성 검사 - 비어있거나 의미없는 데이터인지 확인
                        if not enriched_data or not isinstance(enriched_data, dict):
                            print(f"[WARN] Enriched JSON이 비어있음, Raw 데이터 사용", flush=True)
                            enriched_data = raw_data
                        else:
                            # resources 섹션 확인 - 핵심 데이터가 있는지 체크
                            resources = enriched_data.get('resources', {})
                            if isinstance(resources, dict):
                                ec2_total = resources.get('ec2', {}).get('total', 0) if isinstance(resources.get('ec2'), dict) else 0
                                s3_total = resources.get('s3', {}).get('total', 0) if isinstance(resources.get('s3'), dict) else 0
                                iam_total = enriched_data.get('iam_security', {}).get('users', {}).get('total', 0)

                                # 모든 값이 0이면 enriched가 제대로 안된 것
                                if ec2_total == 0 and s3_total == 0 and iam_total == 0:
                                    print(f"[WARN] Enriched JSON에 데이터가 없음 (모두 0), Raw 데이터 사용", flush=True)
                                    enriched_data = raw_data
                                else:
                                    print(f"[DEBUG] Enriched JSON 데이터 확인: EC2={ec2_total}, S3={s3_total}, IAM={iam_total}", flush=True)

                    except json.JSONDecodeError as e:
                        print(f"[ERROR] ❌ JSON 파싱 실패: {e}", flush=True)
                        print(f"[DEBUG] JSON 자동 수정 시도 중...", flush=True)

                        # JSON 파일 내용 읽기
                        with open(enriched_json_path, 'r', encoding='utf-8') as f:
                            json_content = f.read()

                        # 일반적인 JSON 오류 자동 수정 시도
                        try:
                            # 1. 연속된 중괄호 사이 쉼표 누락 수정
                            json_content = re.sub(r'"\s*\n\s*"', '",\n  "', json_content)
                            json_content = re.sub(r'}\s*\n\s*"', '},\n  "', json_content)
                            json_content = re.sub(r']\s*\n\s*"', '],\n  "', json_content)

                            # 2. 다시 파싱 시도
                            enriched_data = json.loads(json_content)
                            print(f"[DEBUG] ✅ JSON 자동 수정 성공!", flush=True)

                            # 수정된 JSON 저장
                            fixed_json_path = enriched_json_path.replace('.json', '_fixed.json')
                            with open(fixed_json_path, 'w', encoding='utf-8') as f:
                                json.dump(enriched_data, f, indent=2, ensure_ascii=False)
                            print(f"[DEBUG] 수정된 JSON 저장: {fixed_json_path}", flush=True)

                        except Exception as fix_error:
                            print(f"[ERROR] ❌ JSON 자동 수정 실패: {fix_error}", flush=True)
                            # Raw 데이터로 폴백
                            print(f"[DEBUG] Raw 데이터로 폴백하여 보고서 생성", flush=True)
                            enriched_data = raw_data

                # HTML 생성 전 데이터 검증
                # Enriched 데이터가 비정상이면 Raw 데이터 사용
                html_data = enriched_data
                resources_check = enriched_data.get('resources', {})
                if isinstance(resources_check, dict):
                    ec2_check = resources_check.get('ec2', {}).get('total', 0) if isinstance(resources_check.get('ec2'), dict) else 0
                    s3_check = resources_check.get('s3', {}).get('total', 0) if isinstance(resources_check.get('s3'), dict) else 0

                    # EC2와 S3가 모두 0이면 Raw 데이터 사용
                    if ec2_check == 0 and s3_check == 0:
                        raw_ec2 = raw_data.get('resources', {}).get('ec2', {}).get('total', 0)
                        raw_s3 = raw_data.get('resources', {}).get('s3', {}).get('total', 0)

                        # Raw 데이터에는 값이 있으면 Raw 사용
                        if raw_ec2 > 0 or raw_s3 > 0:
                            print(f"[WARN] Enriched 데이터가 비정상 (EC2=0, S3=0), Raw 데이터로 HTML 생성", flush=True)
                            print(f"[DEBUG] Raw 데이터: EC2={raw_ec2}, S3={raw_s3}", flush=True)
                            html_data = raw_data

                html_content = generate_html_from_json(html_data)

                # HTML 파일 저장
                html_filename = f"aws_report_{target_account}_{timestamp}.html"
                html_path = f"/tmp/reports/{html_filename}"

                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"[DEBUG] ✅ HTML 보고서 생성 완료: {html_path}", flush=True)

                # Slack에 업로드 및 URL 전송
                upload_file_to_slack(channel, html_path, title="AWS 보안 보고서")

                report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{html_filename}"

                # 요약 메시지 생성 (안전한 접근 with 기본값)
                # ⚠️ 중요: Raw 데이터에서 가져와야 정확한 카운트를 얻을 수 있음
                ta_checks = raw_data.get('trusted_advisor', {}).get('checks', [])
                ta_count = len(ta_checks) if isinstance(ta_checks, list) else 0

                # resources 키 안전하게 추출 (Raw 데이터 사용)
                resources = raw_data.get('resources', {})
                ec2_total = resources.get('ec2', {}).get('total', 0) if isinstance(resources, dict) else 0
                s3_total = resources.get('s3', {}).get('total', 0) if isinstance(resources, dict) else 0

                # IAM 정보 안전하게 추출 (Raw 데이터 사용)
                iam_security = raw_data.get('iam_security', {})
                iam_users = iam_security.get('users', {}) if isinstance(iam_security, dict) else {}
                iam_total = iam_users.get('total', 0) if isinstance(iam_users, dict) else 0
                iam_mfa = iam_users.get('mfa_enabled', 0) if isinstance(iam_users, dict) else 0

                # 보안 그룹 정보 안전하게 추출 (Raw 데이터 사용)
                security_groups = raw_data.get('security_groups', {})
                sg_total = security_groups.get('total', 0) if isinstance(security_groups, dict) else 0
                sg_risky = security_groups.get('risky', 0) if isinstance(security_groups, dict) else 0

                print(f"[DEBUG] 📊 요약 데이터: EC2={ec2_total}, S3={s3_total}, IAM={iam_total}, SG={sg_total}", flush=True)

                summary = f"""✅ AWS 보안 보고서 생성 완료!

📊 수집된 데이터:
• EC2 인스턴스: {ec2_total}개
• S3 버킷: {s3_total}개
• IAM 사용자: {iam_total}명 (MFA: {iam_mfa}명)
• 보안 그룹: {sg_total}개 (위험 규칙: {sg_risky}개)
• Trusted Advisor 이슈: {ta_count}개

📄 HTML 보고서: {report_url}"""

                send_message(channel, account_prefix + summary)
                print(f"[DEBUG] 🎉 보고서 생성 완료!", flush=True)

                # 처리 완료 - 함수 종료
                processing_questions.discard(question_key)
                return

            except Exception as e:
                print(f"[ERROR] ❌ 보고서 생성 실패: {e}", flush=True)
                import traceback
                traceback.print_exc()
                send_message(channel, f"❌ 보고서 생성 중 오류가 발생했습니다: {str(e)}")
                processing_questions.discard(question_key)
                return
            # '''

            except Exception as e:
                print(f"[ERROR] ❌ 보고서 생성 실패: {e}", flush=True)
                import traceback
                traceback.print_exc()
                send_message(channel, f"❌ 보고서 생성 중 오류가 발생했습니다: {str(e)}")
                processing_questions.discard(question_key)
                return

        elif question_type in ['cloudtrail', 'cloudwatch']:
            # CloudTrail/CloudWatch: 계정 ID와 기간 필요
            date_instruction = ""
            if month_range_text:
                date_instruction = f"\n\n중요: 사용자가 '{month_range_text}'이라고 했으므로 {target_year}년 {month_range_text} 데이터를 조회하세요. 다른 연도가 아닙니다."

            korean_prompt = f"""다음 컨텍스트를 참고하여 질문에 답변해주세요:

{context_content}

=== 사용자 질문 ===
{question}

계정 ID: {target_account}
분석 기간: {start_date_str} ~ {end_date_str}{date_instruction}

위 컨텍스트의 가이드라인을 따라 한국어로 답변해주세요. ReadOnly 작업만 수행하고, 구체적인 수치와 함께 답변해주세요."""
        else:
            # 일반 질문: 계정 ID와 기간 불필요
            korean_prompt = f"""다음 컨텍스트를 참고하여 질문에 답변해주세요:

{context_content}

=== 사용자 질문 ===
{question}

위 컨텍스트의 가이드라인을 따라 한국어로 답변해주세요."""

        # 타임아웃 설정: 모든 질문 유형 10분 통일
        # 완료되면 즉시 반환되므로, 빠른 질문은 빠르게 응답
        # CloudWatch/CloudTrail 같은 복잡한 쿼리도 충분한 시간 확보
        timeout = 600  # 10분

        cmd = ['/root/.local/bin/q', 'chat', '--no-interactive', '--trust-all-tools', korean_prompt]
        print(f"[DEBUG] 실행 명령어: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] 타임아웃 설정: {timeout}초 (질문 유형: {question_type})", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env_vars, timeout=timeout)
        print(f"[DEBUG] Q CLI 완료. 반환코드: {result.returncode}", flush=True)

        # 오케스트레이션 확인을 위한 로깅
        if "q chat --agent" in result.stdout:
            print(f"[DEBUG] 🔄 오케스트레이션 감지됨!", flush=True)
            orchestration_lines = [line for line in result.stdout.split('\n') if 'q chat --agent' in line]
            for line in orchestration_lines:
                print(f"[DEBUG] 📋 서브에이전트 호출: {line.strip()}", flush=True)

        if result.returncode == 0:
            raw_output = result.stdout.strip()
            print(f"[DEBUG] 원본 출력 길이: {len(raw_output)}", flush=True)
            if raw_output:
                # 보고서 타입일 때는 간단하게, 일반 질문일 때는 상세하게
                if question_type == 'report':
                    # 보고서는 JSON 보존을 위해 최소한의 정리만 (ANSI 코드만 제거)
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    clean_response = ansi_escape.sub('', raw_output)
                else:
                    clean_response = simple_clean_output(raw_output)
                print(f"[DEBUG] 정리된 출력 길이: {len(clean_response)}", flush=True)

                # 슬랙 메시지는 간단한 요약만
                if question_type == 'report':
                    slack_message = account_prefix + "보고서를 생성했습니다."
                else:
                    slack_message = account_prefix + clean_response

                print(f"[DEBUG] 슬랙 메시지 전송 시작", flush=True)
                send_message(channel, slack_message)
                print(f"[DEBUG] 슬랙 메시지 전송 완료", flush=True)

                # ---- HTML 보고서 파일 생성 및 업로드 (보고서 요청시에만) ----
                if question_type == 'report':
                    try:
                        print(f"[DEBUG] Security Report JSON 파일 확인: {output_json_path}", flush=True)

                        # 1. 지정된 경로에 파일 존재 확인
                        if not os.path.exists(output_json_path):
                            error_msg = f"❌ 보고서 파일이 생성되지 않았습니다: {output_json_path}"
                            print(f"[ERROR] {error_msg}", flush=True)
                            send_message(channel, error_msg)
                            raise FileNotFoundError(error_msg)

                        # 2. JSON 파일 로드
                        print(f"[DEBUG] JSON 파일 로드 시작", flush=True)
                        with open(output_json_path, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        print(f"[DEBUG] JSON 파일 로드 성공", flush=True)
                        print(f"[DEBUG] JSON 주요 키: {list(json_data.keys())}", flush=True)

                        # 3. security_report 래퍼 처리 (있는 경우)
                        if 'security_report' in json_data and isinstance(json_data['security_report'], dict):
                            print(f"[DEBUG] security_report 래퍼 감지, 언래핑", flush=True)
                            json_data = json_data['security_report']
                            print(f"[DEBUG] 언래핑 후 키: {list(json_data.keys())}", flush=True)

                        # 3.5. JSON 구조 변환 (Q CLI 형식 → 템플릿 형식)
                        json_data = convert_qcli_json_to_template_format(json_data)
                        print(f"[DEBUG] JSON 구조 변환 완료", flush=True)

                        # 4. 템플릿 기반 HTML 생성
                        html_content = generate_html_from_json(json_data)
                        print(f"[DEBUG] HTML 생성 완료", flush=True)

                        # 5. HTML 파일 저장
                        html_filename = f"aws_report_{target_account}_{timestamp}.html"
                        html_path = f"/tmp/reports/{html_filename}"

                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        print(f"[DEBUG] HTML 보고서 생성: {html_path}", flush=True)

                        # 6. Slack에 업로드 및 URL 전송
                        upload_file_to_slack(channel, html_path, title="AWS 보안 보고서")

                        report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{html_filename}"
                        send_message(channel, f"📄 HTML 보고서: {report_url}")
                        print(f"[DEBUG] HTML 보고서 URL 전송 완료", flush=True)

                    except FileNotFoundError as e:
                        print(f"[ERROR] JSON 파일 없음: {e}", flush=True)
                        send_message(channel, f"❌ 보고서 파일을 생성하지 못했습니다. 다시 시도해주세요.")
                    except json.JSONDecodeError as e:
                        print(f"[ERROR] JSON 파싱 실패: {e}", flush=True)
                        send_message(channel, f"❌ 보고서 데이터 형식이 올바르지 않습니다.")
                    except Exception as e:
                        print(f"[ERROR] Security Report 처리 중 오류: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        send_message(channel, f"❌ 보고서 생성 중 오류가 발생했습니다: {str(e)}")
                else:
                    print(f"[DEBUG] 보고서 키워드 없음 - HTML 파일 생성 생략", flush=True)

            else:
                print(f"[DEBUG] 빈 출력", flush=True)
                send_message(channel, "Q CLI에서 응답이 없습니다.")
        else:
            error_msg = result.stderr.strip() if result.stderr else "알 수 없는 오류"
            print(f"[DEBUG] Q CLI 오류: {error_msg}", flush=True)
            send_message(channel, f"❌ 오류가 발생했습니다:\n{error_msg}")

    except subprocess.TimeoutExpired:
        print(f"[DEBUG] 타임아웃 발생 (질문 유형: {question_type})", flush=True)
        send_message(channel, "⏰ 요청 시간이 초과되었습니다. (10분)")
    except Exception as e:
        print(f"[DEBUG] 예외 발생: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        send_message(channel, f"❌ 실행 중 오류: {str(e)}")
    finally:
        # ========================================
        # 임시 세션 디렉터리 정리
        # ========================================
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
                print(f"[DEBUG] 임시 세션 디렉터리 삭제: {temp_dir}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)

        print(f"[DEBUG] 질문 처리 완료: {question_key}", flush=True)
        processing_questions.discard(question_key)


def convert_qcli_json_to_template_format(data):
    """
    Q CLI가 생성한 JSON 구조를 템플릿 형식으로 변환

    Q CLI 형식: resources.ec2_instances, resources.s3_buckets
    템플릿 형식: resources.ec2, resources.s3
    """
    try:
        print(f"[DEBUG] JSON 구조 변환 시작", flush=True)

        # resources 섹션 변환
        if 'resources' in data:
            resources = data['resources']
            new_resources = {}

            # ec2_instances → ec2
            if 'ec2_instances' in resources:
                new_resources['ec2'] = resources['ec2_instances']
            elif 'ec2' in resources:
                new_resources['ec2'] = resources['ec2']
            else:
                new_resources['ec2'] = {'total': 0, 'running': 0, 'instances': []}

            # s3_buckets → s3
            if 's3_buckets' in resources:
                new_resources['s3'] = resources['s3_buckets']
            elif 's3' in resources:
                new_resources['s3'] = resources['s3']
            else:
                new_resources['s3'] = {'total': 0, 'encrypted': 0, 'buckets': []}

            # lambda 함수 (이미 올바른 키)
            if 'lambda' in resources or 'lambda_functions' in resources:
                new_resources['lambda'] = resources.get('lambda') or resources.get('lambda_functions', {'total': 0, 'functions': []})
            else:
                new_resources['lambda'] = {'total': 0, 'functions': []}

            # rds_instances → rds
            if 'rds_instances' in resources:
                new_resources['rds'] = resources['rds_instances']
            elif 'rds' in resources:
                new_resources['rds'] = resources['rds']
            else:
                new_resources['rds'] = {'total': 0, 'instances': []}

            data['resources'] = new_resources

        # 기본값 설정 (누락된 섹션)
        if 'iam_security' not in data:
            data['iam_security'] = {'users': {'total': 0, 'mfa_enabled': 0, 'details': []}, 'issues': []}

        if 'security_groups' not in data:
            data['security_groups'] = {'total': 0, 'risky': 0, 'details': []}

        if 'encryption' not in data:
            data['encryption'] = {
                'ebs': {'total': 0, 'encrypted': 0, 'unencrypted_volumes': []},
                's3': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0},
                'rds': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0}
            }

        if 'trusted_advisor' not in data:
            data['trusted_advisor'] = {'available': False, 'checks': []}

        if 'cloudtrail_events' not in data:
            data['cloudtrail_events'] = {
                'period_days': 30, 'total_events': 0, 'critical_events': [],
                'failed_logins': 0, 'permission_changes': 0, 'resource_deletions': 0
            }

        if 'cloudwatch' not in data:
            data['cloudwatch'] = {
                'alarms': {'total': 0, 'in_alarm': 0, 'ok': 0, 'insufficient_data': 0, 'details': []},
                'high_cpu_instances': []
            }

        if 'recommendations' not in data:
            data['recommendations'] = []

        print(f"[DEBUG] JSON 구조 변환 완료", flush=True)
        return data

    except Exception as e:
        print(f"[ERROR] JSON 구조 변환 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # 변환 실패 시 원본 반환
        return data


def clean_report_output(text):
    """보고서 응답 정리 - 요약 내용만 추출 (Q CLI 실행 과정 제거)"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)

    # Q CLI 도구 실행 과정 완전 제거
    tool_patterns = [
        r'● Reading file:.*',
        r'● Path:.*',
        r'✓ Successfully read.*',
        r'Creating:.*',
        r'파일 위치:.*',
        r'- max-items:.*',
        r'- start-time:.*',
        r'- end-time:.*',
        r'↳ Purpose:.*',
        r'🛠️.*',
        r'● Running.*',
        r'● Completed.*',
    ]

    lines = clean_text.split('\n')
    filtered_lines = []

    # ### 보고서 주요 내용부터 시작하도록
    start_collecting = False

    for line in lines:
        line = line.strip()

        # 보고서 주요 내용부터 수집 시작
        if '### ' in line and '보고서' in line:
            start_collecting = True

        if not start_collecting:
            continue

        # 도구 실행 패턴 스킵
        skip = False
        for pattern in tool_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                skip = True
                break

        if not skip and line:
            filtered_lines.append(line)

    result = '\n'.join(filtered_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip() if result.strip() else "보고서를 생성했습니다."


def clean_json_string(json_str):
    """JSON 문자열 정리 - trailing commas, 주석, diff 마커 제거"""
    # diff 형식 제거 (여러 패턴 시도)
    # 패턴 1: "-   2     :   " 형식 (줄 번호와 콜론)
    json_str = re.sub(r'^[\s\-+]*\d+\s*:\s*', '', json_str, flags=re.MULTILINE)

    # 패턴 2: 줄 시작의 +/- 기호만 제거
    json_str = re.sub(r'^\s*[\-+]\s*', '', json_str, flags=re.MULTILINE)

    # 주석 제거 (// 또는 /* */ 스타일)
    json_str = re.sub(r'//.*?\n', '\n', json_str)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

    # trailing commas 제거 (배열/객체 끝의 콤마)
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # 연속된 빈 줄 정리
    json_str = re.sub(r'\n\s*\n+', '\n', json_str)

    return json_str.strip()


def generate_text_based_html(text):
    """텍스트 기반 HTML 생성 - JSON 파싱 실패 시 fallback"""
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS 보안 보고서</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #232f3e;
            border-bottom: 3px solid #ff9900;
            padding-bottom: 10px;
        }}
        pre {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>AWS 보안 보고서</h1>
        <pre>{text}</pre>
    </div>
</body>
</html>"""
    return html


def simple_clean_output(text):
    """일반 질문 응답 정리 - 도구 사용 내역 제거, 결과만 추출"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)

    # 도구 사용 및 명령어 실행 관련 라인 제거 (강화된 패턴)
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
        r'.*Preparing.*:.*',
        r'^\s*$'
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

    return result.strip() if result.strip() else "응답을 처리할 수 없습니다."


def normalize_security_report_json(data):
    """
    Q CLI가 생성한 JSON을 템플릿 형식으로 변환

    Q CLI는 다양한 JSON 구조를 생성할 수 있으므로,
    템플릿이 기대하는 표준 형식으로 정규화합니다.
    """
    try:
        # 표준 형식 체크 (이미 올바른 형식인지 확인)
        required_keys = ['metadata', 'resources', 'iam_security', 'security_groups',
                        'encryption', 'trusted_advisor', 'cloudtrail_events', 'cloudwatch', 'recommendations']
        if all(key in data for key in required_keys):
            print(f"[DEBUG] 표준 형식 JSON, 정규화 불필요", flush=True)
            return data

        # Q CLI 형식 감지 (다양한 패턴 지원)
        needs_normalization = (
            'reportMetadata' in data or
            'report_metadata' in data or
            'executive_summary' in data or
            'security_findings' in data or
            'resource_inventory' in data
        )

        if needs_normalization:
            print(f"[DEBUG] Q CLI 비표준 형식 JSON 감지, 정규화 시작", flush=True)
            print(f"[DEBUG] 원본 키: {list(data.keys())}", flush=True)

            # 메타데이터 변환 (다양한 키 패턴 지원)
            report_metadata = data.get('reportMetadata') or data.get('report_metadata') or {}
            metadata = {
                'account_id': (report_metadata.get('accountId') or
                              report_metadata.get('account_id') or
                              data.get('account_id') or 'N/A'),
                'report_date': (report_metadata.get('reportDate') or
                               report_metadata.get('report_date') or
                               data.get('report_date') or 'N/A'),
                'period_start': (report_metadata.get('periodStart') or
                                report_metadata.get('period_start') or
                                data.get('period_start') or 'N/A'),
                'period_end': (report_metadata.get('periodEnd') or
                              report_metadata.get('period_end') or
                              data.get('period_end') or 'N/A'),
                'region': (report_metadata.get('region') or
                          data.get('region') or 'ap-northeast-2')
            }

            # 리소스 인벤토리 변환 (다양한 키 패턴 지원)
            resource_inventory = (data.get('resourceInventory') or
                                 data.get('resource_inventory') or
                                 data.get('resources') or {})
            resources = {
                'ec2': resource_inventory.get('ec2', {'total': 0, 'running': 0, 'instances': []}),
                's3': resource_inventory.get('s3', {'total': 0, 'encrypted': 0, 'buckets': []}),
                'lambda': resource_inventory.get('lambda', {'total': 0, 'functions': []}),
                'rds': resource_inventory.get('rds', {'total': 0, 'instances': []})
            }

            # IAM 보안 변환 (다양한 키 패턴 지원)
            iam_security = (data.get('iamSecurity') or
                           data.get('iam_security') or
                           data.get('security_findings', {}).get('iam') or {
                'users': {'total': 0, 'mfa_enabled': 0, 'details': []},
                'issues': []
            })

            # 보안 그룹 변환 (다양한 키 패턴 지원)
            security_groups = (data.get('securityGroupAnalysis') or
                              data.get('security_groups') or
                              data.get('security_findings', {}).get('security_groups') or {
                'total': 0, 'risky': 0, 'details': []
            })

            # 암호화 상태 변환 (다양한 키 패턴 지원)
            encryption = (data.get('encryptionStatus') or
                         data.get('encryption') or
                         data.get('security_findings', {}).get('encryption') or {
                'ebs': {'total': 0, 'encrypted': 0, 'unencrypted_volumes': []},
                's3': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0},
                'rds': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0}
            })

            # Trusted Advisor 변환 (다양한 키 패턴 지원)
            trusted_advisor = (data.get('trustedAdvisor') or
                              data.get('trusted_advisor') or
                              data.get('trusted_advisor_insights') or {
                'available': False, 'checks': []
            })

            # CloudTrail 이벤트 변환 (다양한 키 패턴 지원)
            cloudtrail_events = (data.get('cloudTrailAnalysis') or
                                data.get('cloudtrail_events') or
                                data.get('cloudtrail_activity') or {
                'period_days': 30, 'total_events': 0, 'critical_events': [],
                'failed_logins': 0, 'permission_changes': 0, 'resource_deletions': 0
            })

            # CloudWatch 변환 (다양한 키 패턴 지원)
            cloudwatch = (data.get('cloudWatchAlarms') or
                         data.get('cloudwatch') or {
                'alarms': {'total': 0, 'in_alarm': 0, 'ok': 0, 'insufficient_data': 0, 'details': []},
                'high_cpu_instances': []
            })

            # 권장사항 변환 (문자열 배열을 딕셔너리 배열로)
            recommendations_raw = data.get('recommendations', [])
            recommendations = []
            if isinstance(recommendations_raw, list):
                for i, rec in enumerate(recommendations_raw):
                    if isinstance(rec, str):
                        # 문자열을 딕셔너리로 변환
                        recommendations.append({
                            'priority': 'high' if i < 3 else 'medium',
                            'category': 'security',
                            'title': f"권장사항 {i+1}",
                            'description': rec,
                            'affected_resources': [],
                            'action': rec
                        })
                    elif isinstance(rec, dict):
                        # 이미 딕셔너리면 그대로 사용
                        recommendations.append(rec)

            # 정규화된 JSON 구조 생성
            normalized = {
                'metadata': metadata,
                'resources': resources,
                'iam_security': iam_security,
                'security_groups': security_groups,
                'encryption': encryption,
                'trusted_advisor': trusted_advisor,
                'cloudtrail_events': cloudtrail_events,
                'cloudwatch': cloudwatch,
                'recommendations': recommendations
            }

            print(f"[DEBUG] JSON 정규화 완료, 키: {list(normalized.keys())}", flush=True)
            return normalized

        # 정규화가 필요 없는 경우 - 빈 템플릿 반환
        print(f"[DEBUG] 알 수 없는 JSON 형식, 빈 템플릿 반환", flush=True)
        print(f"[DEBUG] 키: {list(data.keys())}", flush=True)
        return {
            'metadata': {'account_id': 'N/A', 'report_date': 'N/A', 'period_start': 'N/A', 'period_end': 'N/A', 'region': 'ap-northeast-2'},
            'resources': {'ec2': {'total': 0, 'running': 0, 'instances': []}, 's3': {'total': 0, 'encrypted': 0, 'buckets': []}, 'lambda': {'total': 0, 'functions': []}, 'rds': {'total': 0, 'instances': []}},
            'iam_security': {'users': {'total': 0, 'mfa_enabled': 0, 'details': []}, 'issues': []},
            'security_groups': {'total': 0, 'risky': 0, 'details': []},
            'encryption': {'ebs': {'total': 0, 'encrypted': 0, 'unencrypted_volumes': []}, 's3': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0}, 'rds': {'total': 0, 'encrypted': 0, 'encrypted_rate': 0.0}},
            'trusted_advisor': {'available': False, 'checks': []},
            'cloudtrail_events': {'period_days': 30, 'total_events': 0, 'critical_events': [], 'failed_logins': 0, 'permission_changes': 0, 'resource_deletions': 0},
            'cloudwatch': {'alarms': {'total': 0, 'in_alarm': 0, 'ok': 0, 'insufficient_data': 0, 'details': []}, 'high_cpu_instances': []},
            'recommendations': []
        }

    except Exception as e:
        print(f"[ERROR] JSON 정규화 실패: {e}", flush=True)
        # 정규화 실패 시 원본 반환 (fallback)
        return data


def generate_html_from_json(data):
    """JSON 데이터를 HTML 보고서로 변환"""
    print(f"[DEBUG] generate_html_from_json 시작, 입력 데이터 키: {list(data.keys())}", flush=True)

    # JSON 정규화 (Q CLI 형식 → 템플릿 형식)
    data = normalize_security_report_json(data)
    print(f"[DEBUG] 정규화 후 데이터 키: {list(data.keys())}", flush=True)
    print(f"[DEBUG] metadata: {data.get('metadata', {})}", flush=True)
    print(f"[DEBUG] resources.ec2.total: {data.get('resources', {}).get('ec2', {}).get('total', 'N/A')}", flush=True)

    # 템플릿 로드
    template_path = '/root/templates/json_report_template.html'
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        print(f"[DEBUG] 템플릿 로드 성공: {template_path}", flush=True)
    except:
        # 템플릿 없으면 로컬 경로 시도
        template_path = 'json_report_template.html'
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        print(f"[DEBUG] 템플릿 로드 성공 (로컬): {template_path}", flush=True)

    # 기본 값 추출
    metadata = data.get('metadata', {})
    resources = data.get('resources', {})
    iam = data.get('iam_security', {})
    sg = data.get('security_groups', {})
    encryption = data.get('encryption', {})
    ta = data.get('trusted_advisor', {})
    ct = data.get('cloudtrail_events', {})
    cw = data.get('cloudwatch', {})
    recs = data.get('recommendations', [])

    print(f"[DEBUG] 추출된 값 - EC2 total: {resources.get('ec2', {}).get('total', 0)}", flush=True)
    print(f"[DEBUG] 추출된 값 - S3 total: {resources.get('s3', {}).get('total', 0)}", flush=True)
    print(f"[DEBUG] 추출된 값 - IAM users total: {iam.get('users', {}).get('total', 0)}", flush=True)

    # 계산된 값
    iam_users = iam.get('users', {})
    iam_mfa_rate = (iam_users.get('mfa_enabled', 0) / iam_users.get('total', 1) * 100) if iam_users.get('total', 0) > 0 else 0

    ebs = encryption.get('ebs', {})
    ebs_rate = (ebs.get('encrypted', 0) / ebs.get('total', 1) * 100) if ebs.get('total', 0) > 0 else 0

    # 테이블 생성
    ec2_table = generate_ec2_table(resources.get('ec2', {}).get('instances', []))
    s3_table = generate_s3_table(resources.get('s3', {}).get('buckets', []))
    lambda_table = generate_lambda_table(resources.get('lambda', {}).get('functions', []))
    rds_table = generate_rds_table(resources.get('rds', {}).get('instances', []))
    iam_users_table = generate_iam_users_table(iam_users.get('details', []))
    iam_issues_list = generate_iam_issues_list(iam.get('issues', []))
    sg_table = generate_sg_table(sg.get('details', []))
    ta_content = generate_ta_content(ta)
    ct_events_table = generate_ct_events_table(ct.get('critical_events', []))
    cw_alarms_table = generate_cw_alarms_table(cw.get('alarms', {}).get('details', []))
    recommendations_list = generate_recommendations_list(recs)

    # 템플릿 값 매핑
    html = template.format(
        account_id=metadata.get('account_id', 'N/A'),
        report_date=metadata.get('report_date', 'N/A'),
        period_start=metadata.get('period_start', 'N/A'),
        period_end=metadata.get('period_end', 'N/A'),

        # EC2
        ec2_total=resources.get('ec2', {}).get('total', 0),
        ec2_running=resources.get('ec2', {}).get('running', 0),
        ec2_table=ec2_table,

        # S3
        s3_total=resources.get('s3', {}).get('total', 0),
        s3_encrypted=resources.get('s3', {}).get('encrypted', 0),
        s3_table=s3_table,

        # Lambda
        lambda_total=resources.get('lambda', {}).get('total', 0),
        lambda_table=lambda_table,

        # RDS
        rds_total=resources.get('rds', {}).get('total', 0),
        rds_table=rds_table,

        # IAM
        iam_users_total=iam_users.get('total', 0),
        iam_mfa_enabled=iam_users.get('mfa_enabled', 0),
        iam_mfa_rate=f"{iam_mfa_rate:.1f}",
        iam_issues_count=len(iam.get('issues', [])),
        iam_users_table=iam_users_table,
        iam_issues_list=iam_issues_list,

        # 보안 그룹
        sg_total=sg.get('total', 0),
        sg_risky=sg.get('risky', 0),
        sg_table=sg_table,

        # 암호화
        ebs_total=ebs.get('total', 0),
        ebs_encrypted=ebs.get('encrypted', 0),
        ebs_rate=f"{ebs_rate:.1f}",
        ebs_unencrypted_count=len(ebs.get('unencrypted_volumes', [])),
        s3_encrypted_rate=f"{encryption.get('s3', {}).get('encrypted_rate', 0):.1f}",
        s3_unencrypted_count=encryption.get('s3', {}).get('total', 0) - encryption.get('s3', {}).get('encrypted', 0),
        rds_encrypted=encryption.get('rds', {}).get('encrypted', 0),
        rds_encrypted_rate=f"{encryption.get('rds', {}).get('encrypted_rate', 0):.1f}",
        rds_unencrypted_count=encryption.get('rds', {}).get('total', 0) - encryption.get('rds', {}).get('encrypted', 0),

        # Trusted Advisor
        trusted_advisor_content=ta_content,

        # CloudTrail
        cloudtrail_days=ct.get('period_days', 30),
        cloudtrail_total=ct.get('total_events', 0),
        cloudtrail_failed_logins=ct.get('failed_logins', 0),
        cloudtrail_permission_changes=ct.get('permission_changes', 0),
        cloudtrail_deletions=ct.get('resource_deletions', 0),
        cloudtrail_events_table=ct_events_table,

        # CloudWatch
        cloudwatch_alarms_total=cw.get('alarms', {}).get('total', 0),
        cloudwatch_alarms_in_alarm=cw.get('alarms', {}).get('in_alarm', 0),
        cloudwatch_alarms_ok=cw.get('alarms', {}).get('ok', 0),
        cloudwatch_alarms_table=cw_alarms_table,

        # 권장사항
        recommendations_list=recommendations_list
    )

    return html


def generate_ec2_table(instances):
    """EC2 인스턴스 테이블 생성"""
    if not instances:
        return '<p class="no-data">EC2 인스턴스가 없습니다</p>'

    html = '<table><thead><tr><th>ID</th><th>이름</th><th>타입</th><th>상태</th><th>IP</th></tr></thead><tbody>'
    for inst in instances:
        state_class = 'ok' if inst.get('state') == 'running' else 'warning'
        html += f'''<tr>
            <td>{inst.get('id', 'N/A')}</td>
            <td>{inst.get('name', '-')}</td>
            <td>{inst.get('type', 'N/A')}</td>
            <td class="{state_class}">{inst.get('state', 'N/A')}</td>
            <td>{inst.get('private_ip', '-')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_s3_table(buckets):
    """S3 버킷 테이블 생성"""
    if not buckets:
        return '<p class="no-data">S3 버킷이 없습니다</p>'

    html = '<table><thead><tr><th>이름</th><th>리전</th><th>암호화</th><th>버저닝</th><th>퍼블릭</th></tr></thead><tbody>'
    for bucket in buckets:
        enc_class = 'ok' if bucket.get('encrypted') else 'error'
        pub_class = 'error' if bucket.get('public_access') else 'ok'
        html += f'''<tr>
            <td>{bucket.get('name', 'N/A')}</td>
            <td>{bucket.get('region', 'N/A')}</td>
            <td class="{enc_class}">{'예' if bucket.get('encrypted') else '아니오'}</td>
            <td>{'예' if bucket.get('versioning') else '아니오'}</td>
            <td class="{pub_class}">{'예' if bucket.get('public_access') else '아니오'}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_lambda_table(functions):
    """Lambda 함수 테이블 생성"""
    if not functions:
        return '<p class="no-data">Lambda 함수가 없습니다</p>'

    html = '<table><thead><tr><th>이름</th><th>런타임</th><th>메모리</th><th>타임아웃</th></tr></thead><tbody>'
    for func in functions:
        html += f'''<tr>
            <td>{func.get('name', 'N/A')}</td>
            <td>{func.get('runtime', 'N/A')}</td>
            <td>{func.get('memory_mb', 'N/A')} MB</td>
            <td>{func.get('timeout_sec', 'N/A')}초</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_rds_table(instances):
    """RDS 인스턴스 테이블 생성"""
    if not instances:
        return '<p class="no-data">RDS 인스턴스가 없습니다</p>'

    html = '<table><thead><tr><th>ID</th><th>엔진</th><th>버전</th><th>클래스</th><th>암호화</th></tr></thead><tbody>'
    for inst in instances:
        enc_class = 'ok' if inst.get('encrypted') else 'error'
        html += f'''<tr>
            <td>{inst.get('id', 'N/A')}</td>
            <td>{inst.get('engine', 'N/A')}</td>
            <td>{inst.get('version', 'N/A')}</td>
            <td>{inst.get('instance_class', 'N/A')}</td>
            <td class="{enc_class}">{'예' if inst.get('encrypted') else '아니오'}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_iam_users_table(users):
    """IAM 사용자 테이블 생성"""
    if not users:
        return '<p class="no-data">IAM 사용자 정보가 없습니다</p>'

    html = '<table><thead><tr><th>사용자명</th><th>MFA</th><th>액세스 키</th><th>정책</th></tr></thead><tbody>'
    for user in users:
        mfa_class = 'ok' if user.get('mfa') else 'error'
        keys = user.get('access_keys', [])
        key_info = f"{len(keys)}개" if keys else "없음"
        html += f'''<tr>
            <td>{user.get('username', 'N/A')}</td>
            <td class="{mfa_class}">{'활성화' if user.get('mfa') else '비활성화'}</td>
            <td>{key_info}</td>
            <td>{', '.join(user.get('policies', []))[:50]}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_iam_issues_list(issues):
    """IAM 이슈 리스트 생성"""
    if not issues:
        return '<p class="no-data">발견된 IAM 이슈가 없습니다</p>'

    html = '<div class="issue-list">'
    for issue in issues:
        severity_class = issue.get('severity', 'medium')
        html += f'''<div class="issue-item">
            <span class="badge badge-{severity_class}">{issue.get('severity', 'N/A').upper()}</span>
            <strong>{issue.get('user', 'N/A')}</strong>: {issue.get('description', 'N/A')}
        </div>'''
    html += '</div>'
    return html


def generate_sg_table(security_groups):
    """보안 그룹 테이블 생성"""
    if not security_groups:
        return '<p class="no-data">보안 그룹 정보가 없습니다</p>'

    html = '<table><thead><tr><th>ID</th><th>이름</th><th>VPC</th><th>위험한 규칙</th></tr></thead><tbody>'
    for sg in security_groups:
        risky_count = len(sg.get('risky_rules', []))
        risky_class = 'error' if risky_count > 0 else 'ok'
        html += f'''<tr>
            <td>{sg.get('id', 'N/A')}</td>
            <td>{sg.get('name', 'N/A')}</td>
            <td>{sg.get('vpc', 'N/A')}</td>
            <td class="{risky_class}">{risky_count}개</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_ta_content(ta_data):
    """Trusted Advisor 콘텐츠 생성"""
    if not ta_data.get('available'):
        return '<p class="no-data">Trusted Advisor를 사용할 수 없습니다 (Business/Enterprise 플랜 필요)</p>'

    checks = ta_data.get('checks', [])
    if not checks:
        return '<p class="no-data">Trusted Advisor 체크 결과가 없습니다</p>'

    html = '<table><thead><tr><th>카테고리</th><th>체크명</th><th>상태</th><th>문제 리소스</th></tr></thead><tbody>'
    for check in checks:
        status = check.get('status', 'ok')
        status_class = 'error' if status == 'error' else ('warning' if status == 'warning' else 'ok')
        html += f'''<tr>
            <td>{check.get('category', 'N/A')}</td>
            <td>{check.get('name', 'N/A')}</td>
            <td class="{status_class}">{status.upper()}</td>
            <td>{check.get('flagged_resources', 0)}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_ct_events_table(events):
    """CloudTrail 이벤트 테이블 생성"""
    if not events:
        return '<p class="no-data">주요 이벤트가 없습니다</p>'

    html = '<table><thead><tr><th>날짜</th><th>이벤트</th><th>사용자</th><th>리소스</th><th>결과</th></tr></thead><tbody>'
    for event in events[:10]:  # 최대 10개만
        result_class = 'ok' if event.get('result') == 'success' else 'error'
        html += f'''<tr>
            <td>{event.get('date', 'N/A')}</td>
            <td>{event.get('event_name', 'N/A')}</td>
            <td>{event.get('user', 'N/A')}</td>
            <td>{event.get('resource', 'N/A')}</td>
            <td class="{result_class}">{event.get('result', 'N/A')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_cw_alarms_table(alarms):
    """CloudWatch 알람 테이블 생성"""
    if not alarms:
        return '<p class="no-data">알람이 없습니다</p>'

    html = '<table><thead><tr><th>이름</th><th>상태</th><th>메트릭</th><th>임계값</th></tr></thead><tbody>'
    for alarm in alarms:
        state = alarm.get('state', 'OK')
        state_class = 'error' if state == 'ALARM' else 'ok'
        html += f'''<tr>
            <td>{alarm.get('name', 'N/A')}</td>
            <td class="{state_class}">{state}</td>
            <td>{alarm.get('metric', 'N/A')}</td>
            <td>{alarm.get('threshold', 'N/A')}</td>
        </tr>'''
    html += '</tbody></table>'
    return html


def generate_recommendations_list(recommendations):
    """권장사항 리스트 생성"""
    if not recommendations:
        return '<p class="no-data">권장사항이 없습니다</p>'

    html = ''
    for rec in recommendations:
        priority = rec.get('priority', 'medium')
        html += f'''<div class="recommendation">
            <span class="badge badge-{priority}">{priority.upper()}</span>
            <h3>{rec.get('title', 'N/A')}</h3>
            <p>{rec.get('description', 'N/A')}</p>
            <p><strong>조치:</strong> {rec.get('action', 'N/A')}</p>
            <p><strong>영향받는 리소스:</strong> {', '.join(rec.get('affected_resources', []))}</p>
        </div>'''
    return html


def generate_screener_html_report(account_id, report_content, timestamp):
    """
    Service Screener 보고서를 HTML로 변환

    Args:
        account_id (str): AWS 계정 ID
        report_content (str): 보고서 텍스트 내용
        timestamp (str): 타임스탬프

    Returns:
        str: HTML 문자열
    """
    # 마크다운 스타일 텍스트를 HTML로 변환
    html_content = report_content.replace('\n', '<br>\n')
    html_content = html_content.replace('###', '<h3>').replace('##', '<h2>').replace('#', '<h1>')

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Screener 보고서 - {account_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', Arial, sans-serif;
            background: #f5f7fa;
            padding: 20px;
            line-height: 1.8;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ font-size: 1.1em; opacity: 0.9; }}
        .content {{
            padding: 40px;
            font-size: 1.05em;
        }}
        h1, h2, h3 {{
            color: #2c3e50;
            margin: 20px 0 10px 0;
        }}
        h1 {{ font-size: 2em; border-bottom: 3px solid #667eea; padding-bottom: 10px; }}
        h2 {{ font-size: 1.6em; border-bottom: 2px solid #95a5a6; padding-bottom: 8px; }}
        h3 {{ font-size: 1.3em; color: #34495e; }}
        .footer {{
            text-align: center;
            padding: 30px;
            background: #ecf0f1;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        pre {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Service Screener 보고서</h1>
            <p><strong>계정:</strong> {account_id} | <strong>생성일:</strong> {timestamp}</p>
        </div>

        <div class="content">
            {html_content}
        </div>

        <div class="footer">
            <p>이 보고서는 AWS Service Screener를 통해 자동으로 생성되었습니다</p>
            <p>생성 시간: {timestamp} | 계정: {account_id}</p>
        </div>
    </div>
</body>
</html>"""

    return html


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


def send_message(channel, message):
    """슬랙 메시지 전송"""
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "channel": channel,
        "text": message
    }
    try:
        print(f"[DEBUG] 슬랙 메시지 전송: 길이 {len(message)}", flush=True)
        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"[DEBUG] 메시지 전송 성공", flush=True)
            else:
                print(f"[ERROR] 슬랙 API 오류: {result.get('error')}", flush=True)
        else:
            print(f"[ERROR] HTTP 오류: {response.status_code}", flush=True)

    except Exception as e:
        print(f"[ERROR] 메시지 전송 실패: {str(e)}", flush=True)

def upload_file_to_slack(channel, file_path, title="파일"):
    """Slack 채널에 파일 업로드"""
    url = "https://slack.com/api/files.upload"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
    }
    try:
        print(f"[DEBUG] 파일 업로드 시도: {file_path}", flush=True)
        with open(file_path, "rb") as f:
            response = requests.post(
                url,
                headers=headers,
                files={"file": f},
                data={"channels": channel, "title": title},
                timeout=20
            )
        print(f"[DEBUG] 업로드 응답 코드: {response.status_code}", flush=True)
        if response.status_code == 200:
            result = response.json()
            print(f"[DEBUG] 업로드 응답: {result}", flush=True)
            if result.get('ok'):
                print(f"[DEBUG] 파일 업로드 성공: {file_path}", flush=True)
            else:
                print(f"[ERROR] Slack 파일 업로드 오류: {result.get('error')}", flush=True)
        else:
            print(f"[ERROR] Slack 파일 업로드 HTTP 오류: {response.status_code} - {response.text}", flush=True)
    except Exception as e:
        print(f"[ERROR] Slack 파일 업로드 실패: {str(e)}", flush=True)

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

    return '<div class="no-data">Lambda 함수가 없습니다</div>'

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
    app.run(host='0.0.0.0', port=3000)