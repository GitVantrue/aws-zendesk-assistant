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
    
    Args:
        account_id (str): AWS 계정 ID
        credentials (dict): AWS 자격증명
        websocket: WebSocket 연결 (진행 상황 전송용)
        session_id (str): 세션 ID
    """
    def screener_worker():
        """백그라운드에서 실행되는 Service Screener 작업"""
        try:
            # 실제 Service Screener 실행
            result = run_service_screener_sync(account_id, credentials, websocket, session_id)
            
            if result["success"]:
                # 성공 시 결과 전송
                if websocket and session_id:
                    success_message = f"✅ Service Screener 스캔 완료!\n\n{result['summary']}"
                    send_websocket_message(websocket, session_id, success_message)
                    
                    if result["report_url"]:
                        report_message = f"📊 Service Screener 상세 보고서:\n{result['report_url']}"
                        send_websocket_message(websocket, session_id, report_message)
                    
                    # WA Summary를 별도 스레드에서 실행
                    if result.get("screener_result_dir") and result.get("timestamp"):
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
            print(f"[ERROR] Service Screener 비동기 실행 중 오류: {str(e)}", flush=True)
            traceback.print_exc()
            if websocket and session_id:
                error_message = f"❌ Service Screener 실행 중 오류가 발생했습니다: {str(e)}"
                send_websocket_message(websocket, session_id, error_message)
    
    # 백그라운드 스레드에서 실행
    thread = threading.Thread(target=screener_worker)
    thread.daemon = True
    thread.start()
    
    # 즉시 반환 (비동기)
    return {
        "success": True,
        "message": "Service Screener 스캔을 시작했습니다. 완료되면 결과를 전송해드리겠습니다.",
        "async": True
    }

def run_service_screener_sync(account_id, credentials=None, websocket=None, session_id=None):
    """
    AWS Service Screener 동기 실행 (Reference 코드 방식)
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
        
        # 환경 변수 설정 (Reference 코드와 동일)
        env_vars = os.environ.copy()
        
        # AWS 설정 파일 경로 격리 (Reference 코드와 동일)
        env_vars['AWS_CONFIG_FILE'] = os.path.join(temp_dir, 'config')
        env_vars['AWS_SHARED_CREDENTIALS_FILE'] = os.path.join(temp_dir, 'credentials')
        
        # 자격증명 설정 (파라미터 우선, 없으면 환경 변수)
        if credentials:
            env_vars['AWS_ACCESS_KEY_ID'] = credentials.get('AWS_ACCESS_KEY_ID', '')
            env_vars['AWS_SECRET_ACCESS_KEY'] = credentials.get('AWS_SECRET_ACCESS_KEY', '')
            env_vars['AWS_SESSION_TOKEN'] = credentials.get('AWS_SESSION_TOKEN', '')
        
        # 캐싱 및 메타데이터 비활성화 (Reference 코드와 동일)
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
        env_vars['AWS_SDK_LOAD_CONFIG'] = '0'
        
        print(f"[DEBUG] 자격증명 확인: ACCESS_KEY={env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}..., SESSION_TOKEN={'있음' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)
        
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
        
        # 기존 Service Screener 결과 삭제 (Reference 코드와 동일)
        old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
        if os.path.exists(old_result_dir):
            print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
            shutil.rmtree(old_result_dir)
        
        # 기본 리전: 서울(ap-northeast-2), 버지니아(us-east-1)
        scan_regions = ['ap-northeast-2', 'us-east-1']
        
        # ========================================
        # Reference 코드 방식: 환경 변수만 사용 (crossAccounts.json 없이)
        # ========================================
        print(f"[DEBUG] 스캔 대상 리전: {', '.join(scan_regions)}", flush=True)
        
        # ========================================
        # Reference 코드 방식: Service Screener 직접 실행 (main.py 방식)
        # ========================================
        
        # 진행 상황 업데이트
        if websocket and session_id:
            send_websocket_message(websocket, session_id, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: ap-northeast-2, us-east-1\n⏱️ 약 2-5분 소요될 수 있습니다.")
        
        # Service Screener 직접 실행 (Reference 코드와 동일)
        cmd = ['python3', '/root/service-screener-v2/main.py', '--regions', 'ap-northeast-2,us-east-1']
        
        print(f"[DEBUG] Service Screener 직접 실행: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] 환경변수 전달 확인: AWS_ACCESS_KEY_ID={env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}...", flush=True)
        print(f"[DEBUG] 환경변수 전달 확인: AWS_EC2_METADATA_DISABLED={env_vars.get('AWS_EC2_METADATA_DISABLED', 'None')}", flush=True)
        
        print(f"[DEBUG] Service Screener 시작 시간: {datetime.now()}", flush=True)
        
        # 로그 파일 생성 (Reference 코드와 동일)
        log_file = f'/tmp/screener_{account_id}.log'
        
        # Reference 코드와 동일: Service Screener 실행 (타임아웃 10분)
        with open(log_file, 'w') as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env_vars,
                timeout=600,  # 10분 타임아웃
                cwd='/root/service-screener-v2'
            )
        
        print(f"[DEBUG] Service Screener 종료 시간: {datetime.now()}", flush=True)
        print(f"[DEBUG] Service Screener 완료 - 반환코드: {result.returncode}", flush=True)
        
        # 로그 파일 내용 읽기 (Reference 코드와 동일)
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
            print(f"[DEBUG] Service Screener 로그 (마지막 1000자):\n{log_content[-1000:]}", flush=True)
        except Exception as e:
            print(f"[DEBUG] 로그 파일 읽기 실패: {e}", flush=True)
        
        # 임시 파일 정리 (crossAccounts.json 없으므로 생략)
        
        # Reference 코드와 동일: Service Screener가 생성한 실제 결과 디렉터리 찾기
        screener_dir = '/root/service-screener-v2'
        
        # Reference 코드와 동일: 결과 디렉터리 패턴 확인
        # 1. adminlte/aws/{account_id} (새 버전)
        # 2. aws/{account_id} (구 버전)
        possible_dirs = [
            os.path.join(screener_dir, 'adminlte', 'aws', account_id),
            os.path.join(screener_dir, 'aws', account_id)
        ]
        
        account_result_dir = None
        for dir_path in possible_dirs:
            if os.path.exists(dir_path):
                account_result_dir = dir_path
                print(f"[DEBUG] 결과 디렉터리 발견: {account_result_dir}", flush=True)
                break
        
        if not account_result_dir:
            print(f"[DEBUG] 결과 디렉터리를 찾을 수 없음. 확인된 경로들:", flush=True)
            for dir_path in possible_dirs:
                print(f"[DEBUG]   - {dir_path}: 존재={os.path.exists(dir_path)}", flush=True)
        
        # 결과 처리
        if account_result_dir and os.path.exists(account_result_dir):
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
                tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"
                
                # 기존 디렉토리가 있으면 삭제
                if os.path.exists(tmp_report_dir):
                    shutil.rmtree(tmp_report_dir)
                
                # 전체 디렉토리 복사 (index.html이 있는 디렉토리)
                source_dir = os.path.dirname(index_html_path)
                shutil.copytree(source_dir, tmp_report_dir)
                print(f"[DEBUG] 전체 디렉터리 복사 완료: {tmp_report_dir}", flush=True)
                
                # res 디렉토리도 복사 (CSS/JS/이미지 파일들) - Reference 코드와 동일
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
                    # 대체 경로 시도 (Reference 코드와 동일)
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
                print(f"[DEBUG] index.html을 찾을 수 없음", flush=True)
                return {
                    "success": True,
                    "summary": f"📊 계정 {account_id} 스캔이 완료되었으나 index.html을 찾을 수 없습니다.",
                    "report_url": None,
                    "error": None
                }
        else:
            print(f"[DEBUG] 결과 디렉터리 없음. 추가 대기 중...", flush=True)
            
            # Reference 코드와 동일: CloudFormation 오류가 있어도 추가 대기
            # 스캔이 백그라운드에서 계속 진행될 수 있음
            import time
            for wait_count in range(450):  # 900초 = 450 * 2초 (15분)
                time.sleep(2)
                
                # 다시 결과 디렉터리 찾기
                for dir_path in possible_dirs:
                    if os.path.exists(dir_path):
                        account_result_dir = dir_path
                        print(f"[DEBUG] 지연 성공! 결과 디렉터리 생성됨: {account_result_dir} (대기시간: {(wait_count+1)*2}초)", flush=True)
                        break
                
                if account_result_dir and os.path.exists(account_result_dir):
                    break
                
                # 진행 상황 업데이트 (30초마다)
                if websocket and session_id and (wait_count + 1) % 15 == 0:
                    elapsed_minutes = ((wait_count+1)*2) // 60
                    send_websocket_message(websocket, session_id, f"⏳ 스캔 진행 중... ({elapsed_minutes}분 경과)")
            
            # 대기 후 다시 확인
            if not account_result_dir or not os.path.exists(account_result_dir):
                print(f"[DEBUG] 900초(15분) 대기 후에도 결과 디렉터리 없음", flush=True)
                
                return {
                    "success": False,
                    "summary": None,
                    "report_url": None,
                    "error": f"스캔이 15분 대기 후에도 결과 디렉터리를 찾을 수 없습니다. 확인된 경로: {', '.join(possible_dirs)}"
                }
            else:
                print(f"[DEBUG] 대기 후 결과 디렉터리 발견: {account_result_dir}", flush=True)
    
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
        
        wa_report_url = generate_wa_summary_report(account_id, screener_result_dir, timestamp)
        
        if wa_report_url:
            if websocket and session_id:
                wa_message = f"📋 Well-Architected 통합 분석 보고서 완성!\n{wa_report_url}"
                send_websocket_message(websocket, session_id, wa_message)
            print(f"[DEBUG] WA 보고서 URL 전송 완료: {wa_report_url}", flush=True)
        else:
            if websocket and session_id:
                send_websocket_message(websocket, session_id, "⚠️ Well-Architected 보고서 생성에 실패했습니다.")
            print(f"[DEBUG] WA 보고서 생성 실패", flush=True)
            
    except Exception as e:
        print(f"[ERROR] WA 보고서 비동기 생성 중 오류: {str(e)}", flush=True)
        if websocket and session_id:
            send_websocket_message(websocket, session_id, f"❌ Well-Architected 보고서 생성 중 오류: {str(e)}")

def send_websocket_message(websocket, session_id, message):
    """
    WebSocket으로 메시지 전송
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
            
            # 비동기 전송을 위한 코루틴 생성 및 실행
            def send_async():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(websocket.send_str(json.dumps(ws_message)))
                    loop.close()
                except Exception as e:
                    print(f"[ERROR] WebSocket 전송 실패: {e}", flush=True)
            
            # 별도 스레드에서 실행 (블로킹 방지)
            import threading
            thread = threading.Thread(target=send_async)
            thread.daemon = True
            thread.start()
            
            print(f"[DEBUG] WebSocket 메시지 전송: {session_id} - {message[:100]}...", flush=True)
        
    except Exception as e:
        print(f"[ERROR] WebSocket 메시지 전송 실패: {e}", flush=True)

def parse_screener_results(output_dir, account_id):
    """
    Service Screener 결과 파싱하여 요약 생성
    Reference 코드의 완전한 parse_screener_results 함수
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

def generate_wa_summary_report(account_id, screener_result_dir, timestamp):
    """
    Well-Architected 통합 분석 보고서 생성
    Reference 코드의 완전한 generate_wa_summary_report 함수
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
        print(f"[ERROR] WA Summarizer 실행 중 오류: {str(e)}", flush=True)
        traceback.print_exc()
        return None