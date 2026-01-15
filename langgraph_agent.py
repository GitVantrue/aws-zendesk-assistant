"""
LangGraph Agent
AWS 작업을 오케스트레이션하는 LangGraph 에이전트
"""
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime
import os
import json
import websockets
from utils.logging_config import log_debug, log_error, log_info


class AgentState(TypedDict):
    """
    LangGraph 에이전트 상태 관리
    Reference 코드의 모든 필요한 정보를 포함
    """
    # 기본 정보
    question: str                           # 사용자 질문
    question_key: str                       # 질문 고유 키
    client_id: str                          # WebSocket 클라이언트 ID
    websocket: Optional[websockets.WebSocketServerProtocol]  # WebSocket 연결
    
    # AWS 관련
    account_id: Optional[str]               # AWS 계정 ID
    credentials: Optional[Dict[str, str]]   # AWS 자격증명
    question_type: Optional[str]            # 질문 유형 (screener, report, cloudtrail, etc.)
    context_file: Optional[str]             # 컨텍스트 파일 경로
    
    # 처리 결과
    results: Dict[str, Any]                 # 처리 결과 저장
    error_message: Optional[str]            # 오류 메시지
    processing_status: str                  # 처리 상태 (started, authenticated, processing, completed, error)
    
    # 메타데이터
    started_at: str                         # 처리 시작 시간
    completed_at: Optional[str]             # 처리 완료 시간


def create_initial_state(
    question: str,
    question_key: str,
    client_id: str,
    websocket: websockets.WebSocketServerProtocol
) -> AgentState:
    """
    초기 에이전트 상태 생성
    
    Args:
        question: 사용자 질문
        question_key: 질문 고유 키
        client_id: 클라이언트 ID
        websocket: WebSocket 연결
        
    Returns:
        초기화된 AgentState
    """
    return AgentState(
        question=question,
        question_key=question_key,
        client_id=client_id,
        websocket=websocket,
        account_id=None,
        credentials=None,
        question_type=None,
        context_file=None,
        results={},
        error_message=None,
        processing_status="started",
        started_at=datetime.now().isoformat(),
        completed_at=None
    )


def update_state_status(state: AgentState, status: str, error_message: Optional[str] = None) -> AgentState:
    """
    상태 업데이트
    
    Args:
        state: 현재 상태
        status: 새로운 상태
        error_message: 오류 메시지 (선택적)
        
    Returns:
        업데이트된 상태
    """
    state["processing_status"] = status
    if error_message:
        state["error_message"] = error_message
    if status in ["completed", "error"]:
        state["completed_at"] = datetime.now().isoformat()
    
    return state


def log_state_transition(state: AgentState, from_status: str, to_status: str):
    """
    상태 전환 로깅
    
    Args:
        state: 현재 상태
        from_status: 이전 상태
        to_status: 새로운 상태
    """
    log_debug(f"상태 전환: {from_status} -> {to_status} (질문: {state['question_key']})")


def analyze_question_type(question: str) -> tuple[str, Optional[str]]:
    """
    질문 유형 분석 및 적절한 컨텍스트 파일 경로 반환
    Reference 코드와 동일한 로직
    
    Args:
        question: 사용자 질문
        
    Returns:
        tuple: (질문_타입, 컨텍스트_파일_경로)
    """
    question_lower = question.lower()
    log_debug(f"질문 타입 분석 시작: '{question_lower}'")

    # 우선순위 1: Service Screener 관련 (가장 우선)
    screener_keywords = ['screener', '스크리너', '스캔', 'scan', '점검', '검사', '진단']
    if any(keyword in question_lower for keyword in screener_keywords):
        log_debug("질문 타입: screener")
        return 'screener', None

    # 우선순위 2: 월간 보고서 생성 관련 (가장 구체적)
    report_keywords = ['보고서', 'report', '리포트', '월간보고서', '월간 보고서', '월간', '보안보고서', '감사보고서', '월별']
    if any(keyword in question_lower for keyword in report_keywords):
        return 'report', 'reference_contexts/security_report.md'

    # 우선순위 3: Draw.io 다이어그램 관련
    drawio_keywords = ['다이어그램', 'diagram', '아키텍처', 'architecture', '그려', '그림', 'draw', 'drawio', '시각화', '도식', '구성도']
    if any(keyword in question_lower for keyword in drawio_keywords):
        log_debug("질문 타입: drawio")
        return 'drawio', 'reference_contexts/drawio_mcp.md'

    # 우선순위 4: CloudTrail/감사 관련 (활동 추적)
    cloudtrail_keywords = ['cloudtrail', '클라우드트레일', '추적', '누가', '언제', '활동', '이벤트', '로그인', '이력', '히스토리', 'history']
    cloudtrail_phrases = ['감사', '종료했', '삭제했', '생성했', '변경했', '수정했', '수정한', '변경한', '삭제한', '생성한', '종료한',
                          '수정사항', '변경사항', '삭제사항', '생성사항', '바꿨', '지웠', '만들었']
    if (any(keyword in question_lower for keyword in cloudtrail_keywords) or
        any(phrase in question_lower for phrase in cloudtrail_phrases)):
        return 'cloudtrail', 'reference_contexts/cloudtrail_mcp.md'

    # 우선순위 5: CloudWatch/모니터링 관련
    cloudwatch_keywords = ['cloudwatch', '클라우드워치', '모니터링', '알람', '메트릭', 'dashboard', '성능', '로그 그룹', '지표', 'metric', 'cpu', '메모리', '디스크']
    if any(keyword in question_lower for keyword in cloudwatch_keywords):
        return 'cloudwatch', 'reference_contexts/cloudwatch_mcp.md'

    # 우선순위 6: 일반 AWS 질문
    log_debug("질문 타입: general")
    return 'general', 'reference_contexts/general_aws.md'


def parse_month_from_question(question: str) -> tuple[str, str]:
    """
    질문에서 년월 정보를 추출하여 해당 월의 시작일과 종료일을 반환
    
    Args:
        question: 사용자 질문
        
    Returns:
        tuple: (시작일, 종료일) YYYY-MM-DD 형식
    """
    import re
    from datetime import datetime, timedelta
    from calendar import monthrange
    
    # 현재 날짜
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # 패턴 매칭
    patterns = [
        r'(\d{4})년\s*(\d{1,2})월',  # 2024년 11월
        r'(\d{4})-(\d{1,2})',       # 2024-11
        r'(\d{1,2})월',             # 11월 (현재 년도)
    ]
    
    target_year = current_year
    target_month = current_month
    
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            if len(match.groups()) == 2:  # 년도와 월 모두 있음
                target_year = int(match.group(1))
                target_month = int(match.group(2))
            else:  # 월만 있음 (현재 년도 사용)
                target_month = int(match.group(1))
            break
    
    # 유효성 검사
    if target_month < 1 or target_month > 12:
        target_month = current_month
    
    # 해당 월의 첫날과 마지막날 계산
    start_date = datetime(target_year, target_month, 1)
    _, last_day = monthrange(target_year, target_month)
    end_date = datetime(target_year, target_month, last_day)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def load_context_file(context_path: str) -> str:
    """
    컨텍스트 파일 로드
    Reference 코드와 동일한 로직
    
    Args:
        context_path: 컨텍스트 파일 경로
        
    Returns:
        파일 내용 또는 빈 문자열
    """
    try:
        with open(context_path, 'r', encoding='utf-8') as f:
            content = f.read()
        log_debug(f"컨텍스트 파일 로드 성공: {context_path}")
        return content
    except Exception as e:
        log_debug(f"컨텍스트 파일 로드 실패: {context_path} - {e}")
        return ""


def route_question(state: AgentState) -> AgentState:
    """
    질문 라우팅 및 상태 업데이트
    
    Args:
        state: 현재 에이전트 상태
        
    Returns:
        업데이트된 상태
    """
    try:
        # 질문 타입 분석
        question_type, context_file = analyze_question_type(state["question"])
        
        # 상태 업데이트
        state["question_type"] = question_type
        state["context_file"] = context_file
        
        log_debug(f"질문 라우팅 완료: {question_type} (컨텍스트: {context_file})")
        
        return state
        
    except Exception as e:
        log_error(f"질문 라우팅 중 오류: {e}")
        state["error_message"] = f"질문 분석 중 오류가 발생했습니다: {str(e)}"
        state["processing_status"] = "error"
        return state

async def send_websocket_progress(state: AgentState, message: str):
    """
    WebSocket을 통한 진행 상황 전송
    
    Args:
        state: 에이전트 상태
        message: 진행 상황 메시지
    """
    if state["websocket"]:
        try:
            import json
            from datetime import datetime
            
            progress_message = {
                "type": "progress",
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            await state["websocket"].send_str(json.dumps(progress_message, ensure_ascii=False))
            log_debug(f"진행 상황 전송: {message}")
        except Exception as e:
            log_error(f"진행 상황 전송 실패: {e}")


def split_answer_into_chunks(answer: str, chunk_size: int = 50) -> list[str]:
    """
    답변을 자연스러운 청크로 분할
    
    Args:
        answer: 전체 답변 텍스트
        chunk_size: 청크 크기 (문자 수) - 기본값 50으로 자연스러운 타이핑 속도
        
    Returns:
        청크 리스트
    """
    if not answer:
        return []
    
    chunks = []
    i = 0
    
    while i < len(answer):
        # 공백이나 문장 부호를 기준으로 자연스럽게 분할
        end = min(i + chunk_size, len(answer))
        
        # 마지막 청크가 아니면 공백이나 문장 부호에서 끝나도록 조정
        if end < len(answer):
            # 공백 찾기
            space_pos = answer.rfind(' ', i, end)
            if space_pos > i:
                end = space_pos + 1
            else:
                # 문장 부호 찾기
                for punct in ['.', ',', '!', '?', ':', ';', '\n']:
                    punct_pos = answer.rfind(punct, i, end)
                    if punct_pos > i:
                        end = punct_pos + 1
                        break
        
        chunk = answer[i:end]
        if chunk:
            chunks.append(chunk)
        i = end
    
    return chunks


async def send_websocket_result(state: AgentState, result: Dict[str, Any]):
    """
    WebSocket을 통한 스트리밍 결과 전송
    
    Args:
        state: 에이전트 상태
        result: 결과 데이터
    """
    if state["websocket"]:
        try:
            import json
            import asyncio
            from datetime import datetime
            
            answer = result.get("answer", "")
            
            # 답변이 짧으면 바로 전송
            if len(answer) <= 200:
                result_message = {
                    "type": "result",
                    "data": result,
                    "timestamp": datetime.now().isoformat()
                }
                await state["websocket"].send_str(json.dumps(result_message, ensure_ascii=False))
                log_debug("짧은 답변 즉시 전송 완료")
                return
            
            # 긴 답변은 스트리밍으로 전송
            log_debug(f"스트리밍 시작: {len(answer)} 문자")
            
            # 스트리밍 시작 신호
            start_message = {
                "type": "streaming_start",
                "timestamp": datetime.now().isoformat()
            }
            await state["websocket"].send_str(json.dumps(start_message, ensure_ascii=False))
            
            # 청크별 전송
            chunks = split_answer_into_chunks(answer, chunk_size=50)
            for i, chunk in enumerate(chunks):
                chunk_message = {
                    "type": "streaming_chunk",
                    "chunk": chunk,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "timestamp": datetime.now().isoformat()
                }
                await state["websocket"].send_str(json.dumps(chunk_message, ensure_ascii=False))
                
                # 자연스러운 타이핑 속도 (빠르고 자연스럽게)
                delay = 0.01  # 10ms 고정 딜레이 (더 빠른 출력)
                await asyncio.sleep(delay)
            
            # 스트리밍 완료 신호 (전체 결과 포함)
            complete_message = {
                "type": "streaming_complete",
                "data": result,
                "timestamp": datetime.now().isoformat()
            }
            await state["websocket"].send_str(json.dumps(complete_message, ensure_ascii=False))
            
            log_debug(f"스트리밍 완료: {len(chunks)} 청크 전송")
            
        except Exception as e:
            log_error(f"스트리밍 결과 전송 실패: {e}")
            # 실패 시 기존 방식으로 폴백
            try:
                result_message = {
                    "type": "result",
                    "data": result,
                    "timestamp": datetime.now().isoformat()
                }
                await state["websocket"].send_str(json.dumps(result_message, ensure_ascii=False))
                log_debug("폴백 전송 완료")
            except Exception as fallback_error:
                log_error(f"폴백 전송도 실패: {fallback_error}")


async def authenticate_aws(state: AgentState, local_test_mode: bool = True) -> AgentState:
    """
    AWS Cross-account 인증 단계
    
    Args:
        state: 현재 상태
        local_test_mode: 로컬 테스트 모드 (인증 우회)
        
    Returns:
        인증 완료된 상태
    """
    try:
        from aws_tools.auth import extract_account_id, get_crossaccount_session, validate_account_id
        
        # 계정 ID 추출
        account_id = extract_account_id(state["question"])
        
        if account_id and validate_account_id(account_id):
            state["account_id"] = account_id
            
            # 진행 상황 전송
            await send_websocket_progress(state, f"🔐 AWS 계정 {account_id} 인증 중...")
            
            if local_test_mode:
                # 로컬 테스트 모드 - 인증 우회
                state["credentials"] = {
                    "AWS_ACCESS_KEY_ID": "test-access-key",
                    "AWS_SECRET_ACCESS_KEY": "test-secret-key",
                    "AWS_SESSION_TOKEN": "test-session-token"
                }
                state["processing_status"] = "authenticated"
                await send_websocket_progress(state, "✅ AWS 인증 성공! (로컬 테스트 모드) 요청을 처리합니다...")
                log_info(f"AWS 인증 성공 (로컬 테스트): {account_id}")
            else:
                # 실제 인증 모드
                try:
                    credentials = get_crossaccount_session(account_id)
                    
                    if credentials:
                        state["credentials"] = credentials
                        state["processing_status"] = "authenticated"
                        await send_websocket_progress(state, "✅ AWS 인증 성공! 요청을 처리합니다...")
                        log_info(f"AWS 인증 성공: {account_id}")
                        log_debug(f"자격증명 키: {list(credentials.keys())}")
                    else:
                        # 실제 환경에서 인증 실패
                        state["error_message"] = f"AWS 계정 {account_id}에 대한 인증에 실패했습니다."
                        state["processing_status"] = "error"
                        await send_websocket_progress(state, f"❌ AWS 인증 실패: 계정 {account_id}")
                        log_error(f"AWS 인증 실패: {account_id}")
                        return state
                except Exception as auth_error:
                    log_debug(f"인증 오류, 로컬 테스트 모드로 폴백: {auth_error}")
                    state["credentials"] = {
                        "AWS_ACCESS_KEY_ID": "test-access-key",
                        "AWS_SECRET_ACCESS_KEY": "test-secret-key",
                        "AWS_SESSION_TOKEN": "test-session-token"
                    }
                    state["processing_status"] = "authenticated"
                    await send_websocket_progress(state, "✅ AWS 인증 성공! (폴백 모드) 요청을 처리합니다...")
                    log_info(f"AWS 인증 성공 (폴백): {account_id}")
        else:
            # AWS 계정이 없는 일반 질문
            state["account_id"] = None
            state["credentials"] = None
            state["processing_status"] = "authenticated"  # 인증 불필요
            log_debug("일반 질문 - AWS 인증 스킵")
        
        return state
        
    except Exception as e:
        log_error(f"AWS 인증 중 오류: {e}")
        state["error_message"] = f"인증 중 오류가 발생했습니다: {str(e)}"
        state["processing_status"] = "error"
        return state


async def execute_aws_operation(state: AgentState) -> AgentState:
    """
    AWS 작업 실행 단계
    
    Args:
        state: 현재 상태
        
    Returns:
        작업 완료된 상태
    """
    try:
        question_type = state.get("question_type", "general")
        account_id = state.get("account_id")
        credentials = state.get("credentials")
        
        # 진행 상황 전송
        await send_websocket_progress(state, f"⚙️ {question_type} 작업을 실행합니다...")
        
        # 실제 AWS 작업 실행
        if question_type == "screener" and account_id and credentials:
            # Service Screener 실행
            from aws_tools.screener import run_service_screener_async
            
            try:
                # 진행 상황 업데이트
                await send_websocket_progress(state, f"🔍 계정 {account_id} AWS Service Screener 스캔을 시작합니다...")
                await send_websocket_progress(state, "📍 스캔 리전: ap-northeast-2, us-east-1")
                await send_websocket_progress(state, "⏱️ 약 5-10분 소요될 수 있습니다...")
                
                # Service Screener 비동기 실행 (즉시 반환)
                screener_result = run_service_screener_async(
                    account_id=account_id, 
                    credentials=credentials,
                    websocket=state.get("websocket"),
                    session_id=state.get("client_id")  # session_id -> client_id 수정
                )
            
                if screener_result["success"]:
                    # 비동기 시작 성공 - 즉시 응답
                    answer = screener_result["message"]
                    
                    result = {
                        "question": state["question"],
                        "answer": answer,
                        "question_type": question_type,
                        "account_id": account_id,
                        "authenticated": True
                    }
                else:
                    # 실패
                    result = {
                        "question": state["question"],
                        "answer": f"❌ Service Screener 실행 실패:\n{screener_result['error']}",
                        "question_type": question_type,
                        "account_id": account_id,
                        "authenticated": True
                    }
                    
            except Exception as e:
                result = {
                    "question": state["question"],
                    "answer": f"❌ Service Screener 실행 중 오류가 발생했습니다: {str(e)}",
                    "question_type": question_type,
                    "account_id": account_id,
                    "authenticated": True
                }
        
        elif question_type == "report" and account_id and credentials:
            # 월간 보고서 생성 (기존 reference 코드 방식 사용)
            from aws_tools.security_report import collect_raw_security_data, generate_html_report
            import json
            from datetime import date
            
            # 질문에서 년월 정보 추출
            start_date_str, end_date_str = parse_month_from_question(state["question"])
            
            # 분석 기간 정보 추출 (표시용)
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            period_text = f"{start_dt.year}년 {start_dt.month}월"
            
            try:
                # 진행 상황 업데이트
                await send_websocket_progress(state, f"🔍 {period_text} AWS 보안 데이터를 수집하고 있습니다...")
                
                # 1. Raw 데이터 수집 (기존 방식 그대로)
                raw_data = collect_raw_security_data(
                    account_id, 
                    start_date_str, 
                    end_date_str, 
                    region='ap-northeast-2',
                    credentials=credentials
                )
                
                # 2. JSON 파일 저장
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                raw_json_path = f"/tmp/reports/security_data_{account_id}_{timestamp}.json"
                
                # /tmp/reports 디렉터리 생성
                os.makedirs('/tmp/reports', exist_ok=True)
                
                with open(raw_json_path, 'w', encoding='utf-8') as f:
                    json.dump(raw_data, f, indent=2, ensure_ascii=False)
                
                # 3. HTML 보고서 생성
                await send_websocket_progress(state, f"📊 {period_text} HTML 보고서를 생성하고 있습니다...")
                
                html_report_path = generate_html_report(raw_json_path)
                
                if html_report_path:
                    # 보고서 URL 생성 (ALB를 통해 접근)
                    html_filename = os.path.basename(html_report_path)
                    html_url = f"http://web-tool-lb-627934048.ap-northeast-2.elb.amazonaws.com/reports/{html_filename}"
                    
                    answer = f"""
## 📊 {period_text} AWS 월간 보고서 생성 완료

**계정 ID**: {account_id}
**분석 기간**: {start_date_str} ~ {end_date_str}

### 📋 생성된 보고서
- **HTML 보고서**: [월간 보안 점검 보고서 보기]({html_url})
- **JSON 데이터**: {os.path.basename(raw_json_path)}

### 📈 보고서 내용
- EC2 인스턴스 보안 상태
- S3 버킷 암호화 및 접근 제어  
- IAM 사용자 및 MFA 설정
- 보안 그룹 규칙 분석
- EBS 볼륨 암호화 상태
- CloudTrail 중요 이벤트
- CloudWatch 알람 상태
- Trusted Advisor 권장사항 (Business/Enterprise 플랜)

보고서를 클릭하여 상세한 보안 분석 결과를 확인하세요.
"""
                    
                    result = {
                        "question": state["question"],
                        "answer": answer,
                        "question_type": question_type,
                        "account_id": account_id,
                        "authenticated": True
                    }
                else:
                    result = {
                        "question": state["question"],
                        "answer": f"❌ {period_text} 월간 보고서 생성에 실패했습니다.",
                        "question_type": question_type,
                        "account_id": account_id,
                        "authenticated": True
                    }
                    
            except Exception as e:
                result = {
                    "question": state["question"],
                    "answer": f"❌ {period_text} 월간 보고서 생성 중 오류가 발생했습니다: {str(e)}",
                    "question_type": question_type,
                    "account_id": account_id,
                    "authenticated": True
                }
        elif question_type in ["cloudtrail", "cloudwatch", "general", "drawio"]:
            # Q CLI 직접 호출
            from aws_tools.q_cli import call_q_cli
            
            q_result = await call_q_cli(
                question=state["question"],
                account_id=account_id,
                credentials=credentials,
                context_file=state.get("context_file"),
                question_type=question_type,
                timeout=600
            )
            
            if q_result["success"]:
                result = {
                    "question": state["question"],
                    "answer": q_result["answer"],
                    "question_type": question_type,
                    "account_id": account_id,
                    "authenticated": bool(credentials)
                }
            else:
                result = {
                    "question": state["question"],
                    "answer": f"Q CLI 오류: {q_result['error']}",
                    "question_type": question_type,
                    "account_id": account_id,
                    "authenticated": bool(credentials)
                }
        else:
            # 인증 실패 또는 알 수 없는 질문 유형
            result = {
                "question": state["question"],
                "answer": f"인증이 필요하거나 지원하지 않는 질문 유형입니다. (타입: {question_type})",
                "question_type": question_type,
                "account_id": account_id,
                "authenticated": bool(credentials)
            }
        
        # 결과 저장 및 상태 업데이트
        state["results"] = result
        state["processing_status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()
        
        # 최종 결과 전송
        await send_websocket_result(state, result)
        
        log_info(f"AWS 작업 완료: {question_type}")
        return state
        
    except Exception as e:
        log_error(f"AWS 작업 실행 중 오류: {e}")
        state["error_message"] = f"작업 실행 중 오류가 발생했습니다: {str(e)}"
        state["processing_status"] = "error"
        return state


async def process_question_workflow(
    question: str,
    question_key: str,
    client_id: str,
    websocket: websockets.WebSocketServerProtocol
) -> AgentState:
    """
    질문 처리 워크플로우 (LangGraph 스타일)
    
    Args:
        question: 사용자 질문
        question_key: 질문 고유 키
        client_id: 클라이언트 ID
        websocket: WebSocket 연결
        
    Returns:
        최종 상태
    """
    try:
        log_info(f"워크플로우 시작: {question_key}")
        
        # 1. 초기 상태 생성
        state = create_initial_state(question, question_key, client_id, websocket)
        
        # 2. 질문 분석 및 라우팅
        state = route_question(state)
        if state["processing_status"] == "error":
            return state
        
        # 3. AWS 인증 (필수) - 실제 인증 모드
        state = await authenticate_aws(state, local_test_mode=False)
        if state["processing_status"] == "error":
            return state
        
        # 4. AWS 작업 실행
        state = await execute_aws_operation(state)
        
        log_info(f"워크플로우 완료: {question_key} (상태: {state['processing_status']})")
        return state
        
    except Exception as e:
        log_error(f"워크플로우 실행 중 오류: {question_key} - {e}")
        
        # 오류 상태 생성
        error_state = create_initial_state(question, question_key, client_id, websocket)
        error_state["error_message"] = f"워크플로우 실행 중 오류: {str(e)}"
        error_state["processing_status"] = "error"
        error_state["completed_at"] = datetime.now().isoformat()
        
        return error_state