"""
AWS Service Screener 실행 모듈
Reference 코드의 Service Screener 로직을 WebSocket 환경에 맞게 적용
"""

import os
import json
import subprocess
import shutil
import threading
from datetime import datetime
import traceback
import tempfile


def run_service_screener_async(account_id, credentials=None, websocket=None, session_id=None):
    """
    AWS Service Screener 비동기 실행
    
    Args:
        account_id (str): AWS 계정 ID
        credentials (dict): AWS 자격증명
        websocket: WebSocket 연결
        session_id (str): 세션 ID
    """
    def screener_worker():
        """백그라운드에서 실행되는 Service Screener 작업"""
        try:
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
                error_message = f"❌ Service Screener 실행 중 오류: {str(e)}"
                send_websocket_message(websocket, session_id, error_message)
    
    # 백그라운드 스레드에서 실행
    thread = threading.Thread(target=screener_worker)
    thread.daemon = True
    thread.start()
    
    return {
        "success": True,
        "message": "Service Screener 스캔을 시작했습니다.",
        "async": True
    }


def run_service_screener_sync(account_id, credentials=None, websocket=None, session_id=None):
    """
    AWS Service Screener 동기 실행 (Reference 코드 방식)
    """
    print(f"[DEBUG] Service Screener 실행 시작: 계정 {account_id}", flush=True)
    
    temp_dir = None
    
    try:
        # 세션 격리: 임시 디렉터리 생성
        temp_dir = tempfile.mkdtemp(prefix=f'q_session_{account_id}_screener_')
        print(f"[DEBUG] 임시 세션 디렉터리 생성: {temp_dir}", flush=True)
        
        # 환경 변수 설정 (참고 코드 방식)
        env_vars = os.environ.copy()
        
        # EC2 IAM 역할 비활성화 (크로스어카운트 자격증명 우선)
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
        env_vars['AWS_SDK_LOAD_CONFIG'] = '0'
        
        # 기존 AWS 자격증명 제거 (크로스어카운트 자격증명만 사용)
        env_vars.pop('AWS_PROFILE', None)
        env_vars.pop('AWS_ROLE_ARN', None)
        env_vars.pop('AWS_WEB_IDENTITY_TOKEN_FILE', None)
        
        if credentials:
            env_vars['AWS_ACCESS_KEY_ID'] = credentials.get('AWS_ACCESS_KEY_ID', '')
            env_vars['AWS_SECRET_ACCESS_KEY'] = credentials.get('AWS_SECRET_ACCESS_KEY', '')
            env_vars['AWS_SESSION_TOKEN'] = credentials.get('AWS_SESSION_TOKEN', '')
        
        env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
        
        print(f"[DEBUG] 환경 변수 설정 - AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'N/A')[:20]}...", flush=True)
        print(f"[DEBUG] 환경 변수 설정 - AWS_SESSION_TOKEN: {'설정됨' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)
        print(f"[DEBUG] 환경 변수 설정 - AWS_EC2_METADATA_DISABLED: {env_vars.get('AWS_EC2_METADATA_DISABLED')}", flush=True)
        
        print(f"[DEBUG] 세션 격리 환경 설정 완료", flush=True)
        
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
                return {
                    "success": False,
                    "summary": None,
                    "report_url": None,
                    "error": f"계정 불일치 - 요청: {account_id}, 실제: {actual_account}"
                }
            else:
                print(f"[DEBUG] ✅ 계정 검증 성공: {actual_account}", flush=True)
        else:
            return {
                "success": False,
                "summary": None,
                "report_url": None,
                "error": f"계정 검증 실패: {verify_result.stderr[:200]}"
            }
        
        # 기존 결과 삭제
        old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
        if os.path.exists(old_result_dir):
            print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
            shutil.rmtree(old_result_dir)
        
        # 타임스탬프 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 진행 상황 업데이트
        if websocket and session_id:
            send_websocket_message(websocket, session_id, 
                f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: ap-northeast-2, us-east-1\n⏱️ 약 2-5분 소요될 수 있습니다.")
        
        # /root/service-screener-v2/adminlte/aws 디렉터리 생성
        os.makedirs('/root/service-screener-v2/adminlte/aws', exist_ok=True)
        print(f"[DEBUG] /root/service-screener-v2/adminlte/aws 디렉터리 생성 완료", flush=True)
        
        # crossAccounts.json 생성 (Reference 코드 방식)
        temp_json_path = f'/tmp/crossAccounts_{account_id}_{timestamp}.json'
        cross_accounts_config = {
            "general": {
                "IncludeThisAccount": True,
                "Regions": ['ap-northeast-2', 'us-east-1']
            }
        }
        
        with open(temp_json_path, 'w') as f:
            json.dump(cross_accounts_config, f, indent=2)
        
        print(f"[DEBUG] crossAccounts.json 생성 완료: {temp_json_path}", flush=True)
        
        # Service Screener 실행 (main.py 직접 실행 - Reference 코드 방식)
        cmd = [
            'python3',
            '/root/service-screener-v2/main.py',
            '--regions', 'ap-northeast-2,us-east-1'
        ]
        
        print(f"[DEBUG] Service Screener 직접 실행: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] 작업 디렉터리: /root/service-screener-v2", flush=True)
        
        # Service Screener 실행
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
        
        # 결과 디렉터리 확인
        screener_dir = '/root/service-screener-v2'
        account_result_dir = os.path.join(screener_dir, 'adminlte', 'aws', account_id)
        
        print(f"[DEBUG] Service Screener 결과 디렉터리 확인: {account_result_dir}", flush=True)
        
        if os.path.exists(account_result_dir):
            print(f"[DEBUG] ✅ 결과 디렉터리 발견: {account_result_dir}", flush=True)
            
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
                # 전체 디렉토리를 /tmp/reports로 복사
                tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"
                
                if os.path.exists(tmp_report_dir):
                    shutil.rmtree(tmp_report_dir)
                
                source_dir = os.path.dirname(index_html_path)
                shutil.copytree(source_dir, tmp_report_dir)
                print(f"[DEBUG] 전체 디렉터리 복사 완료: {tmp_report_dir}", flush=True)
                
                # res 디렉토리도 복사
                res_source = os.path.join(screener_dir, 'adminlte')
                res_dest = os.path.join(tmp_report_dir, 'res')
                
                if os.path.exists(res_source):
                    if os.path.exists(res_dest):
                        shutil.rmtree(res_dest)
                    shutil.copytree(res_source, res_dest)
                    print(f"[DEBUG] res 디렉터리 복사 완료: {res_dest}", flush=True)
                
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
            # 결과 디렉터리 없음 = 권한 에러
            print(f"[DEBUG] 결과 디렉터리 없음: {account_result_dir}", flush=True)
            print(f"[DEBUG] Service Screener 실행 실패 - CloudFormation 권한 부족", flush=True)
            
            return {
                "success": False,
                "summary": None,
                "report_url": None,
                "screener_result_dir": None,
                "timestamp": timestamp,
                "error": "❌ Service Screener 스캔 실패\n\n현재 IAM 역할에 CloudFormation 권한이 없어서 스캔을 완료할 수 없습니다.\n\n필요한 권한:\n- cloudformation:CreateStack\n- cloudformation:DescribeStacks\n- cloudformation:DeleteStack\n\nAWS 관리자에게 문의하여 권한을 추가해주세요."
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
        # 임시 세션 디렉터리 정리
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"[DEBUG] 임시 세션 디렉터리 삭제: {temp_dir}", flush=True)
            except Exception as e:
                print(f"[DEBUG] 임시 디렉터리 삭제 실패 (무시): {e}", flush=True)


def generate_wa_summary_async(account_id, screener_result_dir, timestamp, websocket=None, session_id=None):
    """
    Well-Architected Summary 비동기 생성 (별도 구현 예정)
    """
    try:
        print(f"[DEBUG] Well-Architected 통합 보고서 생성 시작", flush=True)
        
        if not os.path.exists(screener_result_dir):
            print(f"[DEBUG] 결과 디렉터리 없음 - WA 보고서 생성 스킵", flush=True)
            return
        
        if websocket and session_id:
            send_websocket_message(websocket, session_id, "📋 Well-Architected 통합 분석 보고서를 생성하고 있습니다...")
        
        # WA Summary 생성 로직 (Task 6에서 구현)
        print(f"[DEBUG] WA 보고서 생성 로직 (Task 6에서 구현 예정)", flush=True)
        
    except Exception as e:
        print(f"[ERROR] WA 보고서 비동기 생성 중 오류: {str(e)}", flush=True)


def send_websocket_message(websocket, session_id, message):
    """
    WebSocket으로 메시지 전송 (스레드 안전)
    """
    try:
        import json
        
        if websocket and session_id:
            ws_message = {
                "type": "message",
                "session_id": session_id,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            
            def send_async():
                try:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_closed():
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    loop.run_until_complete(websocket.send_str(json.dumps(ws_message)))
                except Exception as e:
                    print(f"[ERROR] WebSocket 전송 실패: {e}", flush=True)
            
            thread = threading.Thread(target=send_async)
            thread.daemon = True
            thread.start()
            
            print(f"[DEBUG] WebSocket 메시지 전송: {session_id} - {message[:100]}...", flush=True)
        
    except Exception as e:
        print(f"[ERROR] WebSocket 메시지 전송 실패: {e}", flush=True)


def parse_screener_results(output_dir, account_id):
    """
    Service Screener 결과 파싱하여 요약 생성
    """
    try:
        json_files = []
        if os.path.exists(output_dir):
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.json') and 'result' in file.lower():
                        json_files.append(os.path.join(root, file))
        
        if not json_files:
            return f"📊 계정 {account_id} 스캔이 완료되었습니다.\n상세 결과는 첨부된 HTML 보고서를 확인하세요."
        
        with open(json_files[0], 'r') as f:
            data = json.load(f)
        
        total_resources = 0
        total_issues = 0
        critical_issues = 0
        high_issues = 0
        
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
