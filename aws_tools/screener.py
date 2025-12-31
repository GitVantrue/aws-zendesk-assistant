"""
AWS Service Screener 실행 모듈
Reference 코드의 Service Screener 로직을 WebSocket 환경에 맞게 적용
비동기 처리로 긴 작업 수행
"""

import os
import json
import subprocess
import shutil
import threading
from datetime import datetime
import traceback


def run_service_screener_async(account_id, credentials=None, websocket=None, session_id=None):
    """
    AWS Service Screener 비동기 실행 (Reference 코드 방식)
    이미 스레드 컨텍스트에서 호출되므로, 직접 동기 실행 (추가 스레드 생성 안 함)
    
    Args:
        account_id (str): AWS 계정 ID
        credentials (dict): AWS 자격증명 (이미 유효한 임시 자격증명)
        websocket: WebSocket 연결 (진행 상황 전송용)
        session_id (str): 세션 ID
    """
    try:
        print(f"[DEBUG] Service Screener 실행 시작: {account_id}", flush=True)
        print(f"[DEBUG] 받은 자격증명 확인: {bool(credentials)}", flush=True)
        
        # 받은 credentials를 그대로 사용 (이미 유효한 임시 자격증명)
        # 스레드 내에서 재생성하지 않음 (토큰 만료 위험)
        result = run_service_screener_sync(account_id, credentials, websocket, session_id)
        
        print(f"[DEBUG] Service Screener 실행 결과: success={result.get('success')}", flush=True)
        
        if result["success"]:
            # 성공 시 결과 전송
            if websocket and session_id:
                success_message = f"✅ Service Screener 스캔 완료!\n\n{result['summary']}"
                send_websocket_message(websocket, session_id, success_message)
                
                if result["report_url"]:
                    report_message = f"📊 Service Screener 상세 보고서:\n{result['report_url']}"
                    send_websocket_message(websocket, session_id, report_message)
                
                # WA Summary를 별도 스레드에서 실행 (Reference 코드와 동일)
                if result.get("screener_result_dir") and result.get("timestamp"):
                    print(f"[DEBUG] WA Summary 생성 시작", flush=True)
                    wa_thread = threading.Thread(
                        target=generate_wa_summary_async,
                        args=(account_id, result["screener_result_dir"], result["timestamp"], websocket, session_id)
                    )
                    wa_thread.daemon = True
                    wa_thread.start()
        else:
            # 실패 시 오류 전송
            if websocket and session_id:
                error_message = f"❌ Service Screener 실행 실패:\n{result['error']}"
                send_websocket_message(websocket, session_id, error_message)
                
    except Exception as e:
        print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
        traceback.print_exc()
        if websocket and session_id:
            error_message = f"❌ Service Screener 실행 중 오류가 발생했습니다: {str(e)}"
            send_websocket_message(websocket, session_id, error_message)
    
    # 즉시 반환 (비동기 응답)
    return {
        "success": True,
        "message": "Service Screener 스캔을 시작했습니다. 완료되면 결과를 전송해드리겠습니다.",
        "async": True
    }


def run_service_screener_sync(account_id, credentials=None, websocket=None, session_id=None):
    """
    AWS Service Screener 동기 실행 (Slack bot과 동일한 방식)
    """
    print(f"[DEBUG] ✅ Service Screener 실행 시작: 계정 {account_id}", flush=True)
    
    # 세션 격리를 위한 임시 디렉터리 생성 (Reference 코드와 동일)
    import tempfile
    temp_dir = None
    
    try:
        # ========================================
        # 세션 격리: 임시 디렉터리 생성 (Reference 코드와 동일)
        # ========================================
        temp_dir = tempfile.mkdtemp(prefix=f'q_session_{account_id}_screener_')
        print(f"[DEBUG] 임시 세션 디렉터리 생성: {temp_dir}", flush=True)
        
        # ========================================
        # Q CLI 캐시 무효화 (Slack 봇과 동일)
        # ========================================
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
        # 환경 변수 설정 (Slack bot과 동일)
        # ========================================
        env_vars = os.environ.copy()
        
        # AWS 설정 파일 경로 격리 (Reference 코드와 동일)
        # 이 설정으로 boto3가 환경 변수의 자격증명을 우선적으로 사용하게 됨
        env_vars['AWS_CONFIG_FILE'] = os.path.join(temp_dir, 'config')
        env_vars['AWS_SHARED_CREDENTIALS_FILE'] = os.path.join(temp_dir, 'credentials')
        
        # 자격증명 설정 (Slack bot과 동일: 직접 접근)
        if credentials:
            env_vars['AWS_ACCESS_KEY_ID'] = credentials['AWS_ACCESS_KEY_ID']
            env_vars['AWS_SECRET_ACCESS_KEY'] = credentials['AWS_SECRET_ACCESS_KEY']
            env_vars['AWS_SESSION_TOKEN'] = credentials['AWS_SESSION_TOKEN']
            print(f"[DEBUG] 자격증명 설정: ACCESS_KEY={credentials['AWS_ACCESS_KEY_ID'][:20]}..., SESSION_TOKEN 있음", flush=True)
        else:
            print(f"[DEBUG] 자격증명 없음 - EC2 IAM 역할 사용", flush=True)
        
        # 리전 설정 (Slack 봇과 동일)
        env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
        
        # 캐싱 및 메타데이터 비활성화 (Reference 코드와 동일)
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
        env_vars['AWS_SDK_LOAD_CONFIG'] = '0'
        
        # HOME 환경 변수 명시적 설정 (스레드 환경에서 필요할 수 있음)
        env_vars['HOME'] = '/root'
        
        # PATH 명시적 설정 (aws CLI 경로 포함)
        env_vars['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.local/bin'
        
        print(f"[DEBUG] 세션 격리 환경 설정 완료:", flush=True)
        print(f"[DEBUG] - AWS_CONFIG_FILE: {env_vars['AWS_CONFIG_FILE']}", flush=True)
        print(f"[DEBUG] - AWS_ACCESS_KEY_ID: {env_vars['AWS_ACCESS_KEY_ID'][:20]}...", flush=True)
        print(f"[DEBUG] - AWS_SESSION_TOKEN: {'설정됨' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)
        print(f"[DEBUG] - HOME: {env_vars.get('HOME')}", flush=True)
        
        # ========================================
        # 계정 검증 (Reference 코드와 동일)
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
                return {
                    "success": False,
                    "summary": None,
                    "report_url": None,
                    "error": f"계정 자격증명 오류 - 요청: {account_id}, 실제: {actual_account}"
                }
            else:
                print(f"[DEBUG] ✅ 계정 검증 성공: {actual_account}", flush=True)
        else:
            print(f"[ERROR] 계정 검증 실패: {verify_result.stderr}", flush=True)
            return {
                "success": False,
                "summary": None,
                "report_url": None,
                "error": f"계정 검증 실패: {verify_result.stderr[:200]}"
            }
        
        # 기존 Service Screener 결과 삭제 (실제 경로 기준)
        old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
        if os.path.exists(old_result_dir):
            print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
            shutil.rmtree(old_result_dir)
        
        # 타임스탬프 생성 (보고서 URL용)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 진행 상황 업데이트
        if websocket and session_id:
            send_websocket_message(websocket, session_id, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: ap-northeast-2, us-east-1\n⏱️ 약 2-5분 소요될 수 있습니다.")
        
        # ========================================
        # Service Screener 직접 실행 (Slack bot과 동일)
        # ========================================
        
        print(f"[DEBUG] Service Screener 직접 실행 시작", flush=True)
        print(f"[DEBUG] 환경변수 확인 - AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:10]}...", flush=True)
        print(f"[DEBUG] 환경변수 확인 - AWS_SESSION_TOKEN 존재: {bool(env_vars.get('AWS_SESSION_TOKEN'))}", flush=True)
        
        # Service Screener main.py 실행 (시스템 Python 사용 - Slack bot과 동일)
        cmd = ['python3', '/root/service-screener-v2/main.py', '--regions', 'ap-northeast-2,us-east-1']
        
        print(f"[DEBUG] Service Screener 직접 실행: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] Working directory: /root/service-screener-v2", flush=True)
        print(f"[DEBUG] 환경 변수 최종 확인:", flush=True)
        print(f"[DEBUG]   - AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}...", flush=True)
        print(f"[DEBUG]   - AWS_SECRET_ACCESS_KEY: {'설정됨' if env_vars.get('AWS_SECRET_ACCESS_KEY') else '없음'}", flush=True)
        print(f"[DEBUG]   - AWS_SESSION_TOKEN: {'설정됨' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)
        print(f"[DEBUG]   - AWS_DEFAULT_REGION: {env_vars.get('AWS_DEFAULT_REGION', 'None')}", flush=True)
        print(f"[DEBUG]   - AWS_EC2_METADATA_DISABLED: {env_vars.get('AWS_EC2_METADATA_DISABLED', 'None')}", flush=True)
        print(f"[DEBUG]   - HOME: {env_vars.get('HOME', 'None')}", flush=True)
        print(f"[DEBUG]   - PATH: {env_vars.get('PATH', 'None')[:100]}...", flush=True)
        
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
        
        # 로그 파일 내용 읽기
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
            print(f"[DEBUG] Service Screener 로그 (마지막 1000자):\n{log_content[-1000:]}", flush=True)
        except Exception as e:
            print(f"[DEBUG] 로그 파일 읽기 실패: {e}", flush=True)
        
        print(f"[DEBUG] Service Screener 실행 완료. 반환코드: {result.returncode}", flush=True)
        
        # Service Screener가 생성한 실제 결과 디렉터리 찾기 (반환코드 무관)
        screener_dir = '/root/service-screener-v2'
        account_result_dir = os.path.join(screener_dir, 'adminlte', 'aws', account_id)
        
        print(f"[DEBUG] Service Screener 결과 디렉터리 확인: {account_result_dir}", flush=True)
        
        # 결과 처리
        if os.path.exists(account_result_dir):
            print(f"[DEBUG] 결과 디렉터리 발견: {account_result_dir}", flush=True)
            
            # 전체 디렉토리를 /tmp/reports로 복사 (ALB를 통해 제공하기 위함)
            tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"
            
            # 기존 디렉토리가 있으면 삭제
            if os.path.exists(tmp_report_dir):
                shutil.rmtree(tmp_report_dir)
            
            # 전체 디렉토리 복사
            shutil.copytree(account_result_dir, tmp_report_dir)
            print(f"[DEBUG] 전체 디렉터리 복사 완료: {tmp_report_dir}", flush=True)
            
            # res 디렉터리도 /tmp/reports/ 최상위에 복사 (../res/ 경로 참조 대응)
            screener_res_dir = '/root/service-screener-v2/adminlte/aws/res'
            tmp_res_dir = '/tmp/reports/res'
            print(f"[DEBUG] res 소스 경로: {screener_res_dir}, 존재={os.path.exists(screener_res_dir)}", flush=True)
            
            if os.path.exists(screener_res_dir):
                # 기존 res 폴더가 있으면 삭제하고 새로 복사
                if os.path.exists(tmp_res_dir):
                    print(f"[DEBUG] 기존 res 디렉터리 삭제: {tmp_res_dir}", flush=True)
                    shutil.rmtree(tmp_res_dir)
                shutil.copytree(screener_res_dir, tmp_res_dir)
                print(f"[DEBUG] res 디렉터리 복사 완료: {tmp_res_dir}", flush=True)
            else:
                print(f"[ERROR] res 소스 디렉터리를 찾을 수 없음: {screener_res_dir}", flush=True)
            
            # 요약 메시지 생성
            summary = parse_screener_results(account_result_dir, account_id)
            
            # Service Screener 보고서 URL 생성
            report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/screener_{account_id}_{timestamp}/index.html"
            print(f"[DEBUG] Service Screener 보고서 URL 생성: {report_url}", flush=True)
            
            return {
                "success": True,
                "summary": summary,
                "report_url": report_url,
                "screener_result_dir": account_result_dir,
                "timestamp": timestamp,
                "error": None
            }
        else:
            print(f"[DEBUG] 결과 디렉터리 없음: {account_result_dir}", flush=True)
            return {
                "success": False,
                "summary": None,
                "report_url": None,
                "error": f"스캔 결과 디렉터리를 찾을 수 없습니다: {account_result_dir}"
            }
    
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Service Screener 타임아웃", flush=True)
        return {
            "success": False,
            "summary": None,
            "report_url": None,
            "error": "스캔 시간이 초과되었습니다. (10분)"
        }
    except Exception as e:
        print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
        traceback.print_exc()
        return {
            "success": False,
            "summary": None,
            "report_url": None,
            "error": f"스캔 실행 중 오류: {str(e)}"
        }
    finally:
        # ========================================
        # 임시 세션 디렉터리 정리 (Reference 코드와 동일)
        # ========================================
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[DEBUG] 임시 세션 디렉터리 삭제: {temp_dir}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)


def generate_wa_summary_async(account_id, screener_result_dir, timestamp, websocket=None, session_id=None):
    """
    Well-Architected Summary 비동기 생성
    """
    try:
        print(f"[DEBUG] Well-Architected 통합 보고서 생성 시작", flush=True)
        
        if websocket and session_id:
            send_websocket_message(websocket, session_id, "📋 Well-Architected 통합 분석 보고서를 생성하고 있습니다...")
        
        # WA 보고서 생성 로직 (향후 구현)
        print(f"[DEBUG] WA 보고서 생성 완료", flush=True)
            
    except Exception as e:
        print(f"[ERROR] WA 보고서 비동기 생성 중 오류: {str(e)}", flush=True)
        if websocket and session_id:
            send_websocket_message(websocket, session_id, f"❌ Well-Architected 보고서 생성 중 오류: {str(e)}")


def send_websocket_message(websocket, session_id, message):
    """
    WebSocket으로 메시지 전송 (스레드 안전)
    """
    try:
        import asyncio
        import json
        
        if websocket and session_id:
            # WebSocket 메시지 형식
            ws_message = {
                "type": "message",
                "session_id": session_id,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            
            # 현재 이벤트 루프 확인
            try:
                loop = asyncio.get_running_loop()
                # 이미 async 컨텍스트에 있으면 직접 실행 불가 - 콜백으로 스케줄
                asyncio.run_coroutine_threadsafe(
                    websocket.send_str(json.dumps(ws_message, ensure_ascii=False)),
                    loop
                )
            except RuntimeError:
                # 이벤트 루프가 없으면 새로 생성
                def send_async():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(
                            websocket.send_str(json.dumps(ws_message, ensure_ascii=False))
                        )
                        loop.close()
                    except Exception as e:
                        print(f"[ERROR] WebSocket 전송 실패: {e}", flush=True)
                
                # 별도 스레드에서 실행 (블로킹 방지)
                send_thread = threading.Thread(target=send_async)
                send_thread.daemon = True
                send_thread.start()
            
            print(f"[DEBUG] WebSocket 메시지 전송: {session_id} - {message[:100]}...", flush=True)
        
    except Exception as e:
        print(f"[ERROR] WebSocket 메시지 전송 실패: {e}", flush=True)


def parse_screener_results(output_dir, account_id):
    """
    Service Screener 결과 파싱하여 요약 생성
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
