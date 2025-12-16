"""
AWS Service Screener 실행 모듈
Reference 코드의 Service Screener 로직을 WebSocket 환경에 맞게 적용
"""

import os
import json
import subprocess
import shutil
from datetime import datetime
import traceback

def run_service_screener(account_id, credentials=None):
    """
    AWS Service Screener 실행
    Reference 코드의 완전한 Service Screener 실행 로직
    
    Args:
        account_id (str): AWS 계정 ID
        credentials (dict): AWS 자격증명 (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    
    Returns:
        dict: {
            "success": bool,
            "summary": str,
            "report_url": str,
            "wa_report_url": str,
            "error": str
        }
    """
    print(f"[DEBUG] ✅ Service Screener 실행 시작: 계정 {account_id}", flush=True)
    
    try:
        # 환경 변수 설정
        env_vars = os.environ.copy()
        
        # 자격증명 설정 (파라미터 우선, 없으면 환경 변수)
        if credentials:
            env_vars['AWS_ACCESS_KEY_ID'] = credentials.get('AWS_ACCESS_KEY_ID', '')
            env_vars['AWS_SECRET_ACCESS_KEY'] = credentials.get('AWS_SECRET_ACCESS_KEY', '')
            env_vars['AWS_SESSION_TOKEN'] = credentials.get('AWS_SESSION_TOKEN', '')
        
        # EC2 메타데이터 비활성화 (Reference 코드와 동일)
        env_vars['AWS_EC2_METADATA_DISABLED'] = 'true'
        
        print(f"[DEBUG] 자격증명 확인: ACCESS_KEY={env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}..., SESSION_TOKEN={'있음' if env_vars.get('AWS_SESSION_TOKEN') else '없음'}", flush=True)
        
        # 기존 Service Screener 결과 삭제 (Reference 코드와 동일)
        old_result_dir = f'/root/service-screener-v2/adminlte/aws/{account_id}'
        if os.path.exists(old_result_dir):
            print(f"[DEBUG] 기존 결과 삭제: {old_result_dir}", flush=True)
            shutil.rmtree(old_result_dir)
        
        # 단일 계정 스캔 방식 (공식 문서 기준)
        # 기본 리전: 서울(ap-northeast-2), 버지니아(us-east-1)
        scan_regions = ['ap-northeast-2', 'us-east-1']
        regions_str = ','.join(scan_regions)
        
        print(f"[DEBUG] 단일 계정 스캔 모드 - 스캔 대상 리전: {regions_str}", flush=True)

        # Service Screener 실행 - 공식 문서 방식: screener --regions {YourRegion}
        screener_path = '/root/service-screener-v2/Screener.py'
        
        # 파일 존재 확인
        print(f"[DEBUG] Screener.py 파일 존재 확인: {os.path.exists(screener_path)}", flush=True)
        if not os.path.exists(screener_path):
            print(f"[ERROR] Screener.py 파일이 존재하지 않음: {screener_path}", flush=True)
            # 대체 경로 확인
            alt_paths = [
                '/root/service-screener-v2/main.py',
                '/root/service-screener-v2/screener.py',
                '/root/service-screener-v2/ServiceScreener.py'
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    print(f"[DEBUG] 대체 파일 발견: {alt_path}", flush=True)
                    screener_path = alt_path
                    break
        
        # 공식 문서 방식: screener --regions {YourRegion}
        cmd = [
            'python3',
            screener_path,
            '--regions', regions_str
        ]
        print(f"[DEBUG] 단일 계정 Service Screener 실행: {' '.join(cmd)}", flush=True)
        print(f"[DEBUG] 작업 디렉터리: /root/service-screener-v2", flush=True)
        print(f"[DEBUG] 환경변수 AWS_ACCESS_KEY_ID: {env_vars.get('AWS_ACCESS_KEY_ID', 'None')[:20]}...", flush=True)
        
        # Service Screener 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=600,  # 10분 타임아웃
            cwd='/root/service-screener-v2'
        )
        
        print(f"[DEBUG] Service Screener 실행 완료. 반환코드: {result.returncode}", flush=True)
        print(f"[DEBUG] stdout 길이: {len(result.stdout)}, stderr 길이: {len(result.stderr)}", flush=True)
        if result.stdout:
            print(f"[DEBUG] stdout (전체):\n{result.stdout}", flush=True)
        if result.stderr:
            print(f"[DEBUG] stderr (전체):\n{result.stderr}", flush=True)
        
        # 작업 디렉터리 내용 확인
        try:
            cwd_contents = os.listdir('/root/service-screener-v2')
            print(f"[DEBUG] 작업 디렉터리 내용: {cwd_contents}", flush=True)
        except Exception as e:
            print(f"[ERROR] 작업 디렉터리 확인 실패: {e}", flush=True)
        
        # Reference 코드와 동일: 반환코드 무시하고 결과 디렉터리 확인
        # (CloudFormation 오류가 있어도 결과가 생성될 수 있음)
        screener_dir = '/root/service-screener-v2'
        account_result_dir = os.path.join(screener_dir, 'adminlte', 'aws', account_id)
        
        print(f"[DEBUG] Service Screener 결과 디렉터리 확인: {account_result_dir}", flush=True)
        
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
                
                # Service Screener 보고서 URL 생성
                report_url = f"http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/screener_{account_id}_{timestamp}/index.html"
                print(f"[DEBUG] Service Screener 보고서 URL 생성: {report_url}", flush=True)
                
                # Well-Architected 통합 보고서 생성
                print(f"[DEBUG] Well-Architected 통합 보고서 생성 시작", flush=True)
                wa_report_url = generate_wa_summary_report(account_id, account_result_dir, timestamp)
                
                # 단일 계정 스캔에서는 임시 파일이 없음
                
                return {
                    "success": True,
                    "summary": summary,
                    "report_url": report_url,
                    "wa_report_url": wa_report_url,
                    "error": None
                }
            else:
                print(f"[DEBUG] index.html을 찾을 수 없음", flush=True)
                return {
                    "success": True,
                    "summary": f"📊 계정 {account_id} 스캔이 완료되었으나 index.html을 찾을 수 없습니다.",
                    "report_url": None,
                    "wa_report_url": None,
                    "error": None
                }
        else:
            print(f"[DEBUG] 계정 디렉터리 없음: {account_result_dir}", flush=True)
            return {
                "success": True,
                "summary": f"📊 계정 {account_id} 스캔이 완료되었습니다.\n⚠️ 출력 디렉터리를 찾을 수 없습니다.",
                "report_url": None,
                "wa_report_url": None,
                "error": None
            }
    
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Service Screener 타임아웃", flush=True)
        return {
            "success": False,
            "summary": None,
            "report_url": None,
            "wa_report_url": None,
            "error": "스캔 시간이 초과되었습니다. (10분)"
        }
    except Exception as e:
        print(f"[ERROR] Service Screener 실행 중 오류: {str(e)}", flush=True)
        traceback.print_exc()
        return {
            "success": False,
            "summary": None,
            "report_url": None,
            "wa_report_url": None,
            "error": f"스캔 실행 중 오류: {str(e)}"
        }

def parse_screener_results(output_dir, account_id):
    """
    Service Screener 결과 파싱하여 요약 생성
    Reference 코드의 완전한 parse_screener_results 함수
    
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

def generate_wa_summary_report(account_id, screener_result_dir, timestamp):
    """
    Well-Architected 통합 분석 보고서 생성
    Reference 코드의 완전한 generate_wa_summary_report 함수
    
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