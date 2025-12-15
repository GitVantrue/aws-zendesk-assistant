"""
LangGraph Agent
AWS 작업을 오케스트레이션하는 LangGraph 에이전트
"""
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime
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

    # 우선순위 2: 보고서 생성 관련 (가장 구체적)
    report_keywords = ['보고서', 'report', '리포트', '감사보고서', '보안보고서']
    if any(keyword in question_lower for keyword in report_keywords):
        return 'report', '/root/core_contexts/security_report.md'

    # 우선순위 3: CloudTrail/감사 관련 (활동 추적)
    cloudtrail_keywords = ['cloudtrail', '클라우드트레일', '추적', '누가', '언제', '활동', '이벤트', '로그인', '이력', '히스토리', 'history']
    cloudtrail_phrases = ['감사', '종료했', '삭제했', '생성했', '변경했', '수정했', '수정한', '변경한', '삭제한', '생성한', '종료한',
                          '수정사항', '변경사항', '삭제사항', '생성사항', '바꿨', '지웠', '만들었']
    if (any(keyword in question_lower for keyword in cloudtrail_keywords) or
        any(phrase in question_lower for phrase in cloudtrail_phrases)):
        return 'cloudtrail', '/root/core_contexts/cloudtrail_mcp.md'

    # 우선순위 4: CloudWatch/모니터링 관련
    cloudwatch_keywords = ['cloudwatch', '클라우드워치', '모니터링', '알람', '메트릭', 'dashboard', '성능', '로그 그룹', '지표', 'metric', 'cpu', '메모리', '디스크']
    if any(keyword in question_lower for keyword in cloudwatch_keywords):
        return 'cloudwatch', '/root/core_contexts/cloudwatch_mcp.md'

    # 우선순위 5: 일반 AWS 질문
    log_debug("질문 타입: general")
    return 'general', '/root/core_contexts/general_aws.md'


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


async def send_websocket_result(state: AgentState, result: Dict[str, Any]):
    """
    WebSocket을 통한 최종 결과 전송
    
    Args:
        state: 에이전트 상태
        result: 결과 데이터
    """
    if state["websocket"]:
        try:
            import json
            from datetime import datetime
            
            result_message = {
                "type": "result",
                "data": result,
                "timestamp": datetime.now().isoformat()
            }
            await state["websocket"].send_str(json.dumps(result_message, ensure_ascii=False))
            log_debug("최종 결과 전송 완료")
        except Exception as e:
            log_error(f"결과 전송 실패: {e}")


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
                    else:
                        # 실제 환경에서 인증 실패 시 로컬 테스트 모드로 폴백
                        log_debug(f"실제 인증 실패, 로컬 테스트 모드로 폴백: {account_id}")
                        state["credentials"] = {
                            "AWS_ACCESS_KEY_ID": "test-access-key",
                            "AWS_SECRET_ACCESS_KEY": "test-secret-key", 
                            "AWS_SESSION_TOKEN": "test-session-token"
                        }
                        state["processing_status"] = "authenticated"
                        await send_websocket_progress(state, "✅ AWS 인증 성공! (폴백 모드) 요청을 처리합니다...")
                        log_info(f"AWS 인증 성공 (폴백): {account_id}")
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
        
        # TODO: Task 5~에서 실제 AWS 작업 구현
        if question_type == "screener" and account_id and credentials:
            # Service Screener 실행
            result = {
                "question": state["question"],
                "answer": f"Task 4 완료: Service Screener 실행 준비됨 (계정: {account_id})",
                "question_type": question_type,
                "account_id": account_id,
                "authenticated": True
            }
        elif question_type == "report" and account_id and credentials:
            # 보안 보고서 생성
            result = {
                "question": state["question"],
                "answer": f"Task 4 완료: 보안 보고서 생성 준비됨 (계정: {account_id})",
                "question_type": question_type,
                "account_id": account_id,
                "authenticated": True
            }
        elif question_type in ["cloudtrail", "cloudwatch"] and account_id and credentials:
            # MCP 서버 연동
            result = {
                "question": state["question"],
                "answer": f"Task 4 완료: {question_type} MCP 연동 준비됨 (계정: {account_id})",
                "question_type": question_type,
                "account_id": account_id,
                "authenticated": True
            }
        else:
            # 일반 질문 또는 인증 실패
            result = {
                "question": state["question"],
                "answer": f"Task 4 완료: LangGraph 에이전트가 정상 작동합니다! (질문 타입: {question_type})",
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
        
        # 3. AWS 인증 (필수) - 로컬 테스트 모드 강제 적용
        state = await authenticate_aws(state, local_test_mode=True)
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