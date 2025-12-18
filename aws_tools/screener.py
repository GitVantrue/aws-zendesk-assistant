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
                    
                    # WA Summary를 별도 스레드에서 실행 (Reference 코드와 동일)
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
    AWS Service Screener 동기 실행 (Reference 코드 방식 - Q CLI 오케스트레이션)
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
        
        # 리전 설정 (Slack 봇과 동일)
        env_vars['AWS_DEFAULT_REGION'] = 'ap-northeast-2'
        
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
        
        # 기존 Service Screener 결과 삭제 (실제 경로 기준)
        old_result_dir = f'/root/service-screener-v2/aws/{account_id}'
        if os.path.exists(old_result_dir):
            print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
            shutil.rmtree(old_result_dir)
        
        # 타임스탬프 생성 (보고서 URL용)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 진행 상황 업데이트
        if websocket and session_id:
            send_websocket_message(websocket, session_id, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...\n📍 스캔 리전: ap-northeast-2, us-east-1\n⏱️ 약 2-5분 소요될 수 있습니다.")
        
        # ========================================
        # Service Screener 직접 실행 (Reference 코드와 동일: Screener.py --crossAccounts 방식)
        # ========================================
        
        print(f"[DEBUG] Service Screener 직접 실행 시작", flush=True)
        print(f"[DEBUG] 환경변수 전달 확인: AWS_ACCESS_KEY_ID={env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}...", flush=True)
        print(f"[DEBUG] 환경변수 전달 확인: AWS_EC2_METADATA_DISABLED={env_vars.get('AWS_EC2_METADATA_DISABLED', 'None')}", flush=True)
        
        # Service Screener main.py 실행 (Slack 봇과 동일: --regions 옵션 사용)
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
                
        # 전역 res 디렉터리도 /tmp/reports/ 최상위에 복사 (../res/ 경로 참조 대응)
                tmp_res_dir = '/tmp/reports/res'
                screener_res_dir = '/root/service-screener-v2/adminlte/aws/res'
                
                print(f"[DEBUG] 전역 res 소스 경로 확인: {screener_res_dir}, 존재={os.path.exists(screener_res_dir)}", flush=True)
                
                if os.path.exists(screener_res_dir):
                    # 기존 res 폴더가 있으면 삭제하고 새로 복사
                    if os.path.exists(tmp_res_dir):
                        print(f"[DEBUG] 기존 전역 res 디렉터리 삭제: {tmp_res_dir}", flush=True)
                        shutil.rmtree(tmp_res_dir)
                    shutil.copytree(screener_res_dir, tmp_res_dir)
                    print(f"[DEBUG] 전역 res 디렉터리 복사 완료: {tmp_res_dir}", flush=True)
                else:
                    print(f"[ERROR] 전역 res 소스 디렉터리를 찾을 수 없음: {screener_res_dir}", flush=True)
                
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
                print(f"[DEBUG] index.html을 찾을 수 없음 - JSON 파일들로 HTML 보고서 생성", flush=True)
                
                # JSON 파일들로부터 간단한 HTML 보고서 생성
                html_report = generate_html_from_json(account_result_dir, account_id, timestamp)
                
                if html_report:
                    # HTML 파일 저장
                    tmp_report_dir = f"/tmp/reports/screener_{account_id}_{timestamp}"
                    os.makedirs(tmp_report_dir, exist_ok=True)
                    
                    index_html_path = os.path.join(tmp_report_dir, 'index.html')
                    with open(index_html_path, 'w', encoding='utf-8') as f:
                        f.write(html_report)
                    
                    print(f"[DEBUG] HTML 보고서 생성 완료: {index_html_path}", flush=True)
                    
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
                    return {
                        "success": True,
                        "summary": f"📊 계정 {account_id} 스캔이 완료되었으나 HTML 보고서를 생성할 수 없습니다.",
                        "report_url": None,
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

def generate_html_from_json(json_dir, account_id, timestamp):
    """
    JSON 파일들로부터 HTML 보고서 생성
    """
    try:
        print(f"[DEBUG] JSON 파일들로부터 HTML 보고서 생성 시작", flush=True)
        
        # JSON 파일 목록 수집
        service_data = {}
        total_findings = 0
        
        if os.path.exists(json_dir):
            for file in os.listdir(json_dir):
                if file.endswith('.json') and not file.endswith('.stat.json') and not file.endswith('.charts.json') and not file.startswith('CustomPage'):
                    service_name = file.replace('.json', '').upper()
                    file_path = os.path.join(json_dir, file)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 이슈 개수 계산
                        if isinstance(data, dict):
                            for key, value in data.items():
                                if isinstance(value, (list, dict)):
                                    total_findings += len(value) if isinstance(value, list) else 1
                        
                        service_data[service_name] = {
                            'file': file,
                            'path': file_path,
                            'data': data
                        }
                    except Exception as e:
                        print(f"[DEBUG] JSON 파일 파싱 실패: {file} - {e}", flush=True)
        
        # HTML 보고서 생성
        services_list = ', '.join(sorted(service_data.keys()))
        
        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Service Screener Report - Account {account_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .content {{
            padding: 40px;
        }}
        .summary {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 5px solid #ff9900;
        }}
        .summary h2 {{
            color: #232f3e;
            margin-bottom: 15px;
        }}
        .summary-item {{
            display: inline-block;
            margin-right: 30px;
            margin-bottom: 10px;
        }}
        .summary-item strong {{
            color: #232f3e;
        }}
        .summary-item span {{
            color: #ff9900;
            font-size: 1.3em;
            font-weight: bold;
        }}
        .services {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .service-card {{
            background: white;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
        }}
        .service-card:hover {{
            border-color: #ff9900;
            box-shadow: 0 5px 15px rgba(255, 153, 0, 0.2);
        }}
        .service-card h3 {{
            color: #232f3e;
            margin-bottom: 10px;
            font-size: 1.2em;
        }}
        .service-card p {{
            color: #666;
            font-size: 0.95em;
            line-height: 1.6;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }}
        .badge {{
            display: inline-block;
            background: #ff9900;
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.85em;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 AWS Service Screener Report</h1>
            <p>Account: {account_id} | Generated: {timestamp}</p>
        </div>
        
        <div class="content">
            <div class="summary">
                <h2>📊 Scan Summary</h2>
                <div class="summary-item">
                    <strong>Total Findings:</strong> <span>{total_findings}</span>
                </div>
                <div class="summary-item">
                    <strong>Services Scanned:</strong> <span>{len(service_data)}</span>
                </div>
                <div class="summary-item">
                    <strong>Scan Date:</strong> <span>{timestamp}</span>
                </div>
            </div>
            
            <h2 style="color: #232f3e; margin-bottom: 20px;">📋 Scanned Services</h2>
            <div class="services">
"""
        
        for service_name in sorted(service_data.keys()):
            html_content += f"""                <div class="service-card">
                    <h3>{service_name}</h3>
                    <p>Service security and compliance assessment completed.</p>
                    <span class="badge">✓ Scanned</span>
                </div>
"""
        
        html_content += """            </div>
        </div>
        
        <div class="footer">
            <p>AWS Service Screener Report | Powered by Q CLI</p>
            <p style="font-size: 0.9em; margin-top: 10px;">For detailed findings, please review the individual service reports.</p>
        </div>
    </div>
</body>
</html>
"""
        
        print(f"[DEBUG] HTML 보고서 생성 완료: {len(html_content)} bytes", flush=True)
        return html_content
        
    except Exception as e:
        print(f"[ERROR] HTML 보고서 생성 실패: {e}", flush=True)
        traceback.print_exc()
        return None

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

def generate_enhanced_wa_summary(account_id, screener_result_dir, timestamp):
    """
    향상된 WA Summary 구현
    Service Screener 결과를 Q CLI로 분석하여 Well-Architected 관점의 보고서 생성
    """
    try:
        print(f"[DEBUG] 향상된 WA Summary 생성 시작: {account_id}", flush=True)
        
        # Service Screener 결과 파일들 수집
        result_files = []
        service_data = {}
        
        if os.path.exists(screener_result_dir):
            for file in os.listdir(screener_result_dir):
                if file.endswith('.html') and file != 'index.html':
                    service_name = file.replace('.html', '')
                    file_path = os.path.join(screener_result_dir, file)
                    result_files.append((service_name, file_path))
                    service_data[service_name] = file_path
        
        # Q CLI를 사용하여 Well-Architected 분석 수행
        wa_context = """
AWS Well-Architected Framework의 5가지 기둥을 기준으로 분석해주세요:

1. **Operational Excellence (운영 우수성)**
   - 시스템 운영 및 모니터링
   - 지속적인 개선 프로세스

2. **Security (보안)**
   - 데이터 보호 및 시스템 보안
   - 접근 제어 및 권한 관리

3. **Reliability (안정성)**
   - 장애 복구 능력
   - 확장성 및 가용성

4. **Performance Efficiency (성능 효율성)**
   - 리소스 최적화
   - 성능 모니터링

5. **Cost Optimization (비용 최적화)**
   - 비용 효율적인 리소스 사용
   - 불필요한 비용 제거

각 기둥별로 현재 상태를 평가하고 개선 권장사항을 제시해주세요.
"""
        
        # Service Screener 결과 요약 생성
        services_summary = f"스캔된 서비스: {', '.join(service_data.keys())}"
        
        # Q CLI 프롬프트 구성
        wa_prompt = f"""다음 AWS 계정의 Service Screener 결과를 Well-Architected Framework 관점에서 분석해주세요:

{wa_context}

=== 계정 정보 ===
계정 ID: {account_id}
스캔 시간: {timestamp}
{services_summary}

=== 분석 요청 ===
위 계정의 Service Screener 결과를 바탕으로 Well-Architected Framework의 5가지 기둥별로 현재 상태를 평가하고, 각 기둥별 개선 권장사항을 한국어로 상세히 작성해주세요.

특히 다음 사항들을 포함해주세요:
- 각 기둥별 현재 상태 점수 (1-5점)
- 주요 발견사항 및 위험요소
- 구체적인 개선 권장사항
- 우선순위별 액션 아이템

HTML 형식으로 보기 좋게 정리해서 응답해주세요."""

        print(f"[DEBUG] Q CLI로 WA 분석 시작", flush=True)
        
        # Q CLI 실행
        cmd = ['/root/.local/bin/q', 'chat', '--no-interactive', '--trust-all-tools', wa_prompt]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )
        
        if result.returncode == 0 and result.stdout:
            # Q CLI 응답을 HTML로 변환
            wa_analysis = result.stdout.strip()
            
            # HTML 보고서 생성
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Well-Architected Analysis - Account {account_id}</title>
    <meta charset="utf-8">
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 0;
            background-color: #f5f5f5;
        }}
        .header {{ 
            background: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);
            color: white; 
            padding: 30px;
            text-align: center;
        }}
        .content {{ 
            max-width: 1200px;
            margin: 0 auto;
            padding: 30px;
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .pillar {{
            margin: 20px 0;
            padding: 20px;
            border-left: 5px solid #ff9900;
            background: #f9f9f9;
        }}
        .pillar h3 {{
            color: #232f3e;
            margin-top: 0;
        }}
        .score {{
            display: inline-block;
            padding: 5px 15px;
            background: #ff9900;
            color: white;
            border-radius: 20px;
            font-weight: bold;
        }}
        .recommendation {{
            background: #e8f4f8;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Well-Architected Framework Analysis</h1>
        <p>Account: {account_id} | Generated: {timestamp}</p>
    </div>
    <div class="content">
        <div style="margin-bottom: 30px;">
            <h2>📊 Analysis Summary</h2>
            <p><strong>Scanned Services:</strong> {len(service_data)} services</p>
            <p><strong>Services:</strong> {', '.join(service_data.keys())}</p>
        </div>
        
        <div>
            <h2>🔍 Well-Architected Analysis</h2>
            {wa_analysis}
        </div>
    </div>
    <div class="footer">
        <p>Generated by AWS Well-Architected Analysis Tool | Based on Service Screener Results</p>
    </div>
</body>
</html>
"""
            
            # HTML 파일 저장
            dest_filename = f"wa_analysis_{account_id}_{timestamp}.html"
            dest_path = f"/tmp/reports/{dest_filename}"
            
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"[DEBUG] 향상된 WA Summary 저장 완료: {dest_path}", flush=True)
            
            # URL 생성
            wa_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{dest_filename}"
            return wa_url
        else:
            print(f"[ERROR] Q CLI WA 분석 실패: {result.stderr}", flush=True)
            # 기본 WA Summary로 폴백
            return generate_simple_wa_summary(account_id, screener_result_dir, timestamp)
        
    except Exception as e:
        print(f"[ERROR] 향상된 WA Summary 생성 실패: {e}", flush=True)
        # 기본 WA Summary로 폴백
        return generate_simple_wa_summary(account_id, screener_result_dir, timestamp)

def generate_simple_wa_summary(account_id, screener_result_dir, timestamp):
    """
    간단한 WA Summary 대체 구현
    Service Screener 결과를 기반으로 기본적인 WA 분석 제공
    """
    try:
        print(f"[DEBUG] 간단한 WA Summary 생성 시작: {account_id}", flush=True)
        
        # Service Screener 결과에서 주요 정보 추출
        summary_data = {
            "account_id": account_id,
            "timestamp": timestamp,
            "services_scanned": [],
            "total_findings": 0,
            "critical_findings": 0,
            "high_findings": 0
        }
        
        # HTML 파일들에서 서비스 목록 추출
        if os.path.exists(screener_result_dir):
            for file in os.listdir(screener_result_dir):
                if file.endswith('.html') and file != 'index.html':
                    service_name = file.replace('.html', '').upper()
                    summary_data["services_scanned"].append(service_name)
        
        # 서비스 목록 정렬
        summary_data["services_scanned"].sort()
        
        # 간단한 HTML 보고서 생성
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Well-Architected Summary - Account {account_id}</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #232f3e; color: white; padding: 20px; }}
        .content {{ padding: 20px; }}
        .service {{ margin: 10px 0; padding: 10px; border-left: 4px solid #ff9900; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Well-Architected Summary Report</h1>
        <p>Account: {account_id} | Generated: {timestamp}</p>
    </div>
    <div class="content">
        <h2>Scanned Services</h2>
        <p>Total Services: {len(summary_data["services_scanned"])}</p>
        {"".join([f'<div class="service">{service}</div>' for service in summary_data["services_scanned"]])}
        
        <h2>Recommendations</h2>
        <p>Please refer to the detailed Service Screener report for specific findings and recommendations.</p>
        <p>This is a simplified Well-Architected summary. For comprehensive analysis, please use the full Service Screener results.</p>
    </div>
</body>
</html>
"""
        
        # HTML 파일 저장
        dest_filename = f"simple_wa_summary_{account_id}_{timestamp}.html"
        dest_path = f"/tmp/reports/{dest_filename}"
        
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[DEBUG] 간단한 WA Summary 저장 완료: {dest_path}", flush=True)
        
        # URL 생성
        wa_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/{dest_filename}"
        return wa_url
        
    except Exception as e:
        print(f"[ERROR] 간단한 WA Summary 생성 실패: {e}", flush=True)
        return None

def generate_wa_summary_report(account_id, screener_result_dir, timestamp):
    """
    Well-Architected 통합 분석 보고서 생성 (Reference 코드와 동일한 동작)
    
    Args:
        account_id (str): AWS 계정 ID
        screener_result_dir (str): Service Screener 결과 디렉터리
        timestamp (str): 타임스탬프
    
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
        temp_account_dir = os.path.join(temp_wa_input_dir, account_id)
        shutil.copytree(screener_result_dir, temp_account_dir)
        print(f"[DEBUG] 계정 폴더 복사: {screener_result_dir} -> {temp_account_dir}", flush=True)

        # res 폴더 복사 (CSS/JS 등 공통 리소스) - Reference 코드와 동일한 경로 사용
        res_source = '/root/service-screener-v2/aws/res'
        res_dest = os.path.join(temp_wa_input_dir, 'res')
        if os.path.exists(res_source):
            shutil.copytree(res_source, res_dest)
            print(f"[DEBUG] res 폴더 복사: {res_source} -> {res_dest}", flush=True)
        else:
            # 대체 경로 시도 (adminlte 구조)
            alt_res_source = '/root/service-screener-v2/adminlte/aws/res'
            if os.path.exists(alt_res_source):
                shutil.copytree(alt_res_source, res_dest)
                print(f"[DEBUG] 대체 res 폴더 복사: {alt_res_source} -> {res_dest}", flush=True)
            else:
                print(f"[DEBUG] res 폴더를 찾을 수 없음: {res_source}, {alt_res_source}", flush=True)

        # 출력 디렉터리는 wa-ss-summarizer의 기본 output 디렉터리 사용
        wa_output_dir = os.path.join(wa_summarizer_dir, 'output')
        os.makedirs(wa_output_dir, exist_ok=True)

        print(f"[DEBUG] WA Summarizer 실행: {wa_script} -d {temp_wa_input_dir}", flush=True)

        # wa-ss-summarizer 실행 (Q CLI PATH 추가 + 한국어 출력 설정) - Reference 코드와 동일
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
        print(f"[ERROR] WA 보고서 생성 중 오류: {str(e)}", flush=True)
        traceback.print_exc()
        return None
