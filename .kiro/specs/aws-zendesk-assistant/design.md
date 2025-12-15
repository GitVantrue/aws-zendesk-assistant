# AWS Zendesk Assistant - Design Document

## Overview

WebSocket 기반 실시간 통신을 통해 Zendesk 환경에서 AWS 보안 분석을 제공하는 시스템입니다. 기존 reference_slack_bot.py의 모든 AWS 분석 기능을 100% 재사용하되, Slack API를 WebSocket 통신으로, Flask 라우팅을 LangGraph Agent 오케스트레이션으로 전환합니다.

## Architecture

```
Zendesk App ←→ WebSocket Server ←→ LangGraph Agent ←→ AWS Tools
                     ↓
              Real-time Progress Updates
                     ↓
         Q CLI (LLM Engine) ←→ MCP Servers (CloudTrail, CloudWatch, General AWS)
                     ↓
              Service Screener (Python Script)
                     ↓
         Raw Data Collection (boto3) → HTML Report Generation
```

### Core Components

1. **WebSocket Server**: 실시간 양방향 통신 (Slack API 대체)
2. **LangGraph Agent**: 상태 머신 기반 워크플로우 오케스트레이션 (Flask 라우팅 대체)
3. **Q CLI Integration**: 모든 AWS 분석의 핵심 LLM 엔진
4. **Reference Logic Reuse**: 기존 검증된 함수들 100% 재사용

## Components and Interfaces

### 1. WebSocket Server
```python
class WebSocketServer:
    def __init__(self):
        self.processing_questions = set()  # 중복 방지
        
    async def handle_connection(self, websocket, path):
        # 연결 관리 및 메시지 라우팅
        
    async def send_progress_update(self, websocket, message):
        # 실시간 진행 상황 업데이트
        
    async def send_result(self, websocket, result):
        # 최종 결과 전송
```

### 2. LangGraph Agent
```python
from langgraph import StateGraph, END

class AWSAnalysisAgent:
    def __init__(self):
        self.graph = self._build_graph()
        
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        # 노드 정의
        workflow.add_node("analyze_question", self.analyze_question_node)
        workflow.add_node("cross_account_auth", self.cross_account_auth_node)
        workflow.add_node("service_screener", self.service_screener_node)
        workflow.add_node("security_report", self.security_report_node)
        workflow.add_node("cloudtrail_query", self.cloudtrail_query_node)
        workflow.add_node("cloudwatch_query", self.cloudwatch_query_node)
        workflow.add_node("general_aws_query", self.general_aws_query_node)
        
        # 모든 AWS 작업은 반드시 cross_account_auth를 거쳐야 함
        workflow.add_conditional_edges(
            "analyze_question",
            self.route_question,
            {
                "screener": "cross_account_auth",
                "report": "cross_account_auth", 
                "cloudtrail": "cross_account_auth",
                "cloudwatch": "cross_account_auth",
                "general": "cross_account_auth"
            }
        )
        
        # 인증 완료 후 실제 작업으로 라우팅
        workflow.add_conditional_edges(
            "cross_account_auth",
            self.route_authenticated_request,
            {
                "screener": "service_screener",
                "report": "security_report", 
                "cloudtrail": "cloudtrail_query",
                "cloudwatch": "cloudwatch_query",
                "general": "general_aws_query"
            }
        )
        
        return workflow.compile()
```

### 3. Reference Function Integration
```python
# reference_slack_bot.py 함수들을 LangGraph Tool로 래핑
from reference_slack_bot import (
    get_crossaccount_session,
    collect_raw_security_data,
    generate_html_report,
    run_service_screener,
    analyze_question_type,
    cleanup_old_screener_results
)

class AWSTools:
    @staticmethod
    def get_cross_account_credentials(account_id: str) -> dict:
        """
        Cross-account 인증 (reference 로직 재사용)
        모든 AWS 작업은 반드시 이 함수를 통해 임시 자격증명을 받아야 함
        """
        return get_crossaccount_session(account_id)
    
    @staticmethod
    def collect_security_data(account_id: str, start_date: str, end_date: str, credentials: dict) -> dict:
        """
        보안 데이터 수집 (reference 로직 재사용)
        credentials는 반드시 get_cross_account_credentials()에서 받은 임시 자격증명
        """
        return collect_raw_security_data(account_id, start_date, end_date, credentials=credentials)
    
    @staticmethod
    def generate_report(json_file_path: str) -> str:
        """HTML 보고서 생성 (reference 로직 재사용)"""
        return generate_html_report(json_file_path)

### 4. Mandatory Cross-Account Authentication Flow
```python
class CrossAccountAuthNode:
    """모든 AWS 작업 전에 반드시 실행되는 인증 노드"""
    
    def __init__(self):
        self.auth_required = True  # 모든 AWS 작업에 필수
        
    def execute(self, state: AgentState) -> AgentState:
        """
        1. 질문에서 계정 ID 추출 (extract_account_id)
        2. Parameter Store에서 cross-account 자격증명 로드
        3. 2단계 STS assume role 실행 (User 방식 → Role 방식 폴백)
        4. 임시 자격증명을 state에 저장
        """
        account_id = state.get("account_id")
        if not account_id:
            raise AuthenticationError("계정 ID가 필요합니다")
            
        # reference 로직 100% 재사용
        credentials = get_crossaccount_session(account_id)
        if not credentials:
            raise AuthenticationError(f"계정 {account_id} 인증 실패")
            
        state["credentials"] = credentials
        return state
```

## Data Models

### Agent State
```python
from typing import TypedDict, Optional, List, Dict, Any

class AgentState(TypedDict):
    # 입력 정보
    question: str
    websocket: Any
    question_key: str
    
    # 분석 결과
    question_type: str  # screener, report, cloudtrail, cloudwatch, general
    account_id: Optional[str]
    
    # 인증 정보
    credentials: Optional[Dict[str, str]]
    
    # 처리 결과
    raw_data: Optional[Dict[str, Any]]
    analysis_result: Optional[str]
    report_url: Optional[str]
    
    # 진행 상황
    progress_messages: List[str]
    error_message: Optional[str]
```

### WebSocket Message Format
```python
# 클라이언트 → 서버
{
    "type": "aws_query",
    "message": "계정 123456789012에 대해 Service Screener 실행해줘",
    "session_id": "unique_session_id"
}

# 서버 → 클라이언트 (진행 상황)
{
    "type": "progress",
    "message": "🔄 계정 123456789012 cross-account 인증 중...",
    "session_id": "unique_session_id"
}

# 서버 → 클라이언트 (최종 결과)
{
    "type": "result",
    "message": "✅ Service Screener 완료!",
    "report_url": "http://server/reports/screener_123456789012_20241215.html",
    "session_id": "unique_session_id"
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

모든 acceptance criteria가 testable properties로 분류되었으며, 다음과 같은 중복성 검토를 수행했습니다:

**중복 제거된 항목들:**
- Context loading properties (4.1, 5.1): MCP context loading은 하나의 통합 property로 처리
- Progress update properties (1.2, 2.3): 실시간 업데이트는 하나의 일반적인 property로 통합
- Authentication properties (1.4, 2.1, 6.2): Cross-account 인증은 하나의 포괄적인 property로 통합
- Logging properties (8.1, 8.4): 로깅 형식은 하나의 통합 property로 처리

### Core Properties

**Property 1: Question routing consistency**
*For any* AWS query containing specific keywords, the system should route to the same handler as the reference implementation's analyze_question_type() function
**Validates: Requirements 1.1, 6.4**

**Property 2: Real-time progress updates**
*For any* long-running operation (Service Screener, security reports, WA analysis), the system should send progress messages at regular intervals
**Validates: Requirements 1.2, 2.3**

**Property 3: Mandatory cross-account authentication**
*For any* AWS operation request, the system should ALWAYS execute cross-account authentication first and use the resulting temporary credentials for all subsequent AWS API calls
**Validates: Requirements 1.4, 2.1, 6.2**

**Property 4: Reference function reuse**
*For any* AWS operation, the system should call the exact same functions (get_crossaccount_session, collect_raw_security_data, generate_html_report) with identical parameters as the reference implementation
**Validates: Requirements 6.1, 6.3, 6.5**

**Property 5: Service Screener execution path**
*For any* Service Screener request, the system should execute /root/service-screener-v2/Screener.py with crossAccounts.json and copy results to /tmp/reports
**Validates: Requirements 2.2, 2.4**

**Property 6: Security data collection completeness**
*For any* security report request, the system should collect data from all specified services (EC2, S3, RDS, Lambda, IAM, Security Groups, CloudTrail, CloudWatch, Trusted Advisor)
**Validates: Requirements 3.2**

**Property 7: HTML report generation consistency**
*For any* analysis result, the system should generate HTML reports using templates/json_report_template.html with identical structure to reference implementation
**Validates: Requirements 3.4, 6.3**

**Property 8: MCP integration with context**
*For any* CloudTrail or CloudWatch query, the system should load the appropriate context file and use MCP integration with Q_CLI
**Validates: Requirements 4.1, 4.2, 5.1, 5.3**

**Property 9: Critical event filtering**
*For any* CloudTrail analysis, the system should focus on the predefined critical events (DeleteBucket, TerminateInstances, DeleteUser, CreateAccessKey, etc.)
**Validates: Requirements 4.3**

**Property 10: Timezone handling accuracy**
*For any* time-based query, the system should correctly convert between UTC+9 (Korean time) and UTC for AWS API calls
**Validates: Requirements 4.4**

**Property 11: Concurrent processing with threading**
*For any* multiple simultaneous requests, the system should handle them using threading.Thread with daemon=True without blocking
**Validates: Requirements 7.2**

**Property 12: Timeout enforcement**
*For any* long-running operation, the system should enforce appropriate timeouts (600s for Service Screener, 900s for WA Summarizer)
**Validates: Requirements 7.3**

**Property 13: Error handling and cleanup**
*For any* exception or error, the system should log with proper prefixes, send error messages to WebSocket clients, and clean up tracking data
**Validates: Requirements 8.1, 8.3, 8.5**

**Property 14: System initialization consistency**
*For any* server startup, the system should initialize /tmp/reports directory, processing_questions tracking, and /health endpoint
**Validates: Requirements 7.1, 7.5**

**Property 15: File cleanup maintenance**
*For any* cleanup operation, the system should remove files older than 3 days using cleanup_old_screener_results() logic
**Validates: Requirements 7.4**

## Error Handling

### Exception Hierarchy
```python
class AWSZendeskError(Exception):
    """Base exception for AWS Zendesk Assistant"""
    pass

class AuthenticationError(AWSZendeskError):
    """Cross-account authentication failures"""
    pass

class ServiceScreenerError(AWSZendeskError):
    """Service Screener execution failures"""
    pass

class ReportGenerationError(AWSZendeskError):
    """HTML report generation failures"""
    pass

class WebSocketError(AWSZendeskError):
    """WebSocket communication failures"""
    pass
```

### Error Recovery Strategies
1. **Authentication Failures**: Fallback from User method to Role method
2. **Service Timeouts**: Graceful termination with partial results
3. **WebSocket Disconnections**: Automatic reconnection with exponential backoff
4. **File System Errors**: Continue processing with error logging
5. **AWS API Throttling**: Retry with exponential backoff

## Testing Strategy

### Dual Testing Approach

**Unit Testing Requirements:**
- Test specific examples and edge cases for each LangGraph node
- Verify WebSocket message handling and routing logic
- Test error conditions and recovery mechanisms
- Validate reference function integration points

**Property-Based Testing Requirements:**
- Use **Hypothesis** for Python property-based testing
- Configure each property test to run minimum **100 iterations**
- Tag each property test with format: **Feature: aws-zendesk-assistant, Property {number}: {property_text}**
- Each correctness property must be implemented by a SINGLE property-based test

**Testing Framework Setup:**
```python
import pytest
from hypothesis import given, strategies as st

# Property test example
@given(st.text(min_size=1))
def test_question_routing_consistency(query):
    """
    **Feature: aws-zendesk-assistant, Property 1: Question routing consistency**
    For any AWS query containing specific keywords, the system should route 
    to the same handler as the reference implementation
    """
    # Test implementation
    pass
```

**Integration Testing:**
- End-to-end WebSocket communication tests
- Cross-account authentication flow validation
- Service Screener execution with real AWS accounts
- HTML report generation and serving verification

**Performance Testing:**
- Concurrent WebSocket connection handling
- Long-running operation timeout validation
- Memory usage during large report generation
- File cleanup efficiency testing