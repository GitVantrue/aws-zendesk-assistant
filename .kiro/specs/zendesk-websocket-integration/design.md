# AWS Zendesk WebSocket Integration - Design Document

## Overview

AWS Zendesk WebSocket Integration은 기존 Slack 봇의 모든 AWS 보안 분석 기능을 Zendesk 환경으로 이식하는 실시간 통신 시스템입니다. WebSocket 기반 양방향 통신을 통해 진행률 추적, 실시간 업데이트, 그리고 향상된 보안을 제공합니다.

핵심 설계 원칙:
- **기존 로직 재사용**: Slack 봇의 검증된 AWS 분석 로직을 100% 재사용
- **실시간 통신**: WebSocket을 통한 즉시 응답 및 진행률 추적
- **보안 강화**: Private subnet 배치로 인바운드 포트 완전 차단
- **플랫폼 독립성**: 향후 다른 플랫폼 연동을 위한 모듈화 설계

## Architecture

### High-Level Architecture

```
┌─────────────────┐    WebSocket     ┌──────────────────┐
│   Zendesk App   │ ←──────────────→ │  WebSocket       │
│   (Frontend)    │    (Real-time)   │  Server          │
└─────────────────┘                  │  (Backend)       │
                                     └──────────────────┘
                                              │
                                              ▼
                                     ┌──────────────────┐
                                     │  AWS Processor   │
                                     │  (Core Logic)    │
                                     └──────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
            │ Cross-Account│        │   Service    │        │     MCP      │
            │     Auth     │        │   Screener   │        │ Integrations │
            └──────────────┘        └──────────────┘        └──────────────┘
```

### Network Architecture

**Option 1: Public EC2 with Outbound-Only Security Group (Recommended)**
```
Internet
    │
    ▼
┌─────────────────┐
│ Public Subnet   │
│                 │
│ WebSocket       │ ← Security Group: Outbound Only
│ Server (EC2)    │   Inbound: NONE
└─────────────────┘   Outbound: 443, 80, 5000
```

**Option 2: Private Subnet with CloudFlare Tunnel (Alternative)**
```
Internet → CloudFlare Tunnel → Private Subnet → WebSocket Server
```

**Recommended Approach**: Public EC2 with restrictive security group
- **장점**: 설정 간단, 추가 서비스 불필요, 비용 절약
- **보안**: 인바운드 완전 차단으로 동일한 보안 수준 달성

## Components and Interfaces

### 1. Zendesk App (Frontend)

**Technology**: Zendesk Apps Framework v2.0, JavaScript, HTML5, CSS3
**Location**: `zendesk-app/`

**Key Components**:
- **Chat Interface**: 실시간 채팅 UI with 메시지 히스토리
- **Progress Tracker**: 시각적 진행률 표시 (progress bar, percentage)
- **Report Viewer**: 생성된 보고서 미리보기 및 다운로드
- **Authentication**: Zendesk JWT 토큰 관리

**Interfaces**:
```javascript
// WebSocket 통신 인터페이스
interface WebSocketClient {
  connect(): Promise<void>
  sendQuery(query: AWSQuery): void
  onProgress(callback: (progress: ProgressUpdate) => void): void
  onResult(callback: (result: AWSResult) => void): void
  onError(callback: (error: ErrorMessage) => void): void
}

// AWS 쿼리 인터페이스
interface AWSQuery {
  query: string
  accountId: string
  ticketId: string
  userId: string
  timestamp: string
}
```

### 2. WebSocket Server (Backend)

**Technology**: Python 3.11, Flask-SocketIO, Socket.IO
**Location**: `backend/`

**Key Components**:
- **Connection Manager**: WebSocket 연결 관리 및 인증
- **Message Router**: 메시지 타입별 라우팅 및 처리
- **Progress Broadcaster**: 실시간 진행률 브로드캐스팅
- **Error Handler**: 예외 처리 및 에러 응답

**Interfaces**:
```python
# WebSocket 이벤트 핸들러
@socketio.on('aws_query')
def handle_aws_query(data: dict) -> None

@socketio.on('connect')
def handle_connect() -> None

@socketio.on('disconnect')
def handle_disconnect() -> None

# 진행률 브로드캐스터
class ProgressBroadcaster:
    def emit_progress(self, client_id: str, progress: int, message: str) -> None
    def emit_result(self, client_id: str, result: dict) -> None
    def emit_error(self, client_id: str, error: str) -> None
```

### 3. AWS Processor (Core Logic)

**Technology**: Python 3.11, Boto3, Threading
**Location**: `backend/core/`

**Key Components**:
- **Query Analyzer**: 질문 타입 분석 (기존 analyze_question_type 로직)
- **Cross-Account Authenticator**: AWS 계정 간 인증 (기존 get_crossaccount_session 로직)
- **Service Screener**: AWS 리소스 스캔 (기존 run_service_screener 로직)
- **Report Generator**: 보안 보고서 생성 (기존 HTML 생성 로직)
- **MCP Integrator**: CloudTrail, CloudWatch, General AWS MCP 연동

**Interfaces**:
```python
class AWSProcessor:
    def __init__(self, progress_callback: Optional[Callable] = None)
    
    def process_query(self, query: str, account_id: str) -> ProcessResult
    def run_screener_scan(self, account_id: str) -> ScreenerResult
    def generate_security_report(self, account_id: str) -> ReportResult
    def query_cloudtrail(self, query: str, account_id: str) -> CloudTrailResult
    def query_cloudwatch(self, query: str, account_id: str) -> CloudWatchResult

class ProcessResult:
    status: str
    data: dict
    reports: List[ReportLink]
    summary: str
    execution_time: float
```

## Data Models

### Request Models

```python
@dataclass
class AWSQueryRequest:
    query: str
    account_id: str
    ticket_id: str
    user_id: str
    timestamp: datetime
    session_id: str

@dataclass
class ProgressUpdate:
    step: str
    message: str
    progress: int
    timestamp: datetime
    estimated_completion: Optional[datetime] = None
```

### Response Models

```python
@dataclass
class AWSQueryResult:
    status: str  # 'success', 'error', 'in_progress'
    data: dict
    reports: List[ReportLink]
    summary: str
    execution_time: float
    timestamp: datetime

@dataclass
class ReportLink:
    name: str
    url: str
    type: str  # 'screener', 'security', 'wa_summary'
    size: int
    generated_at: datetime

@dataclass
class ErrorResponse:
    error_code: str
    message: str
    details: dict
    timestamp: datetime
    retry_after: Optional[int] = None
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After reviewing all properties identified in the prework, I've identified several areas where properties can be consolidated:

- Properties 1.2, 1.3, 2.3 all relate to WebSocket communication behavior and can be combined into a comprehensive real-time communication property
- Properties 4.1, 4.2, 4.5 all relate to consistency with existing Slack bot and can be combined into an output consistency property
- Properties 2.1, 2.2, 2.4 all relate to progress tracking and can be combined into a comprehensive progress tracking property
- Properties 5.1, 5.2, 5.4, 5.5 all relate to authentication and authorization and can be combined into a security property

### Core Properties

**Property 1: Real-time WebSocket Communication**
*For any* AWS query request, when sent through the WebSocket connection, the server should establish communication, send progress updates, and deliver final results in real-time
**Validates: Requirements 1.2, 1.3, 2.3**

**Property 2: Progress Tracking Consistency**
*For any* long-running AWS operation, the system should send progress updates at regular intervals, display visual progress indicators, and provide time estimates when operations exceed expected duration
**Validates: Requirements 2.1, 2.2, 2.4**

**Property 3: Output Consistency with Slack Bot**
*For any* AWS analysis request, the WebSocket system should produce identical results, reports, and data structures as the existing Slack bot implementation
**Validates: Requirements 4.1, 4.2, 4.5**

**Property 4: Authentication and Authorization**
*For any* user access attempt, the system should verify Zendesk permissions, validate JWT tokens, enforce role-based access, and log security events for unauthorized attempts
**Validates: Requirements 5.1, 5.2, 5.4, 5.5**

**Property 5: Report Generation and Attachment**
*For any* completed analysis, the system should generate downloadable report URLs, provide attachment options, and integrate with Zendesk API for ticket updates
**Validates: Requirements 6.1, 6.2, 6.3**

**Property 6: Error Handling and Resilience**
*For any* system error or exception, the system should provide detailed error messages, implement retry logic with exponential backoff, handle timeouts gracefully, and maintain comprehensive logging
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

**Property 7: Cross-Account Authentication Consistency**
*For any* AWS account access request, the system should use identical STS assume role processes and authentication flows as the existing Slack bot
**Validates: Requirements 4.3**

**Property 8: MCP Integration Consistency**
*For any* CloudTrail, CloudWatch, or General AWS query, the system should integrate with the same MCP tools and produce consistent results
**Validates: Requirements 4.4**

**Property 9: Audit Logging**
*For any* AWS analysis request, the system should record complete audit trails with user identification and maintain logs for compliance purposes
**Validates: Requirements 5.3**

**Property 10: Health Monitoring**
*For any* health check request, the system should provide accurate health status and monitoring endpoints
**Validates: Requirements 7.5**

## Error Handling

### Error Categories

1. **Authentication Errors**
   - Invalid Zendesk JWT tokens
   - Expired authentication credentials
   - Insufficient permissions

2. **AWS Operation Errors**
   - Cross-account authentication failures
   - Service Screener execution errors
   - MCP tool integration failures

3. **Network Errors**
   - WebSocket connection failures
   - CloudFlare Tunnel connectivity issues
   - AWS API rate limiting

4. **System Errors**
   - Resource exhaustion
   - Timeout exceptions
   - Unexpected system failures

### Error Handling Strategy

```python
class ErrorHandler:
    def handle_auth_error(self, error: AuthError) -> ErrorResponse
    def handle_aws_error(self, error: AWSError) -> ErrorResponse
    def handle_network_error(self, error: NetworkError) -> ErrorResponse
    def handle_system_error(self, error: SystemError) -> ErrorResponse
    
    def should_retry(self, error: Exception) -> bool
    def get_retry_delay(self, attempt: int) -> float  # Exponential backoff
    def log_error(self, error: Exception, context: dict) -> None
```

## Testing Strategy

### Dual Testing Approach

The system will use both unit testing and property-based testing to ensure comprehensive coverage:

**Unit Testing**:
- Specific examples of WebSocket message handling
- Authentication flow edge cases
- Error condition handling
- Integration points between components

**Property-Based Testing**:
- Universal properties using Hypothesis library (Python)
- Minimum 100 iterations per property test
- Each property test tagged with format: **Feature: zendesk-websocket-integration, Property {number}: {property_text}**

**Property-Based Testing Requirements**:
- Use Hypothesis library for Python property-based testing
- Configure each test to run minimum 100 iterations
- Tag each test with corresponding design document property
- Focus on universal behaviors across all valid inputs

**Testing Framework**: pytest + Hypothesis for backend, Jest for frontend

### Test Categories

1. **WebSocket Communication Tests**
   - Connection establishment and teardown
   - Message serialization/deserialization
   - Real-time progress updates

2. **AWS Integration Tests**
   - Cross-account authentication flows
   - Service Screener execution
   - Report generation consistency

3. **Security Tests**
   - JWT token validation
   - Permission enforcement
   - Audit logging verification

4. **Performance Tests**
   - Concurrent user handling
   - Long-running operation management
   - Memory and resource usage

## Deployment Architecture

### Git 기반 배포 전략

**배포 환경**: 실제 EC2 콘솔 환경에서 Git 기반 배포
- **개발**: 로컬 워크스페이스에서 코드 작성
- **배포**: EC2에서 `git clone` 및 `git push`로 코드 동기화
- **실행**: EC2 콘솔에서 직접 애플리케이션 실행

### Container Strategy (EC2 배포용)

```yaml
# docker-compose.yml structure (EC2에서 실행)
services:
  websocket-server:
    build: ./backend
    ports:
      - "5000:5000"  # WebSocket 포트 (아웃바운드 연결용)
    environment:
      - AWS_DEFAULT_REGION=ap-northeast-2
      - WEBSOCKET_PORT=5000
    volumes:
      - ./shared:/app/shared
      - /tmp/reports:/tmp/reports
    restart: unless-stopped
```

### Git 배포 워크플로우

```bash
# 1. 로컬에서 개발 완료 후
git add .
git commit -m "WebSocket 서버 구현"
git push origin main

# 2. EC2에서 배포
git clone <repository-url>
# 또는 기존 저장소 업데이트
git pull origin main

# 3. EC2에서 실행
docker-compose up -d
# 또는 직접 실행
python3 backend/main.py
```

### Security Configuration

**Public EC2 Security Group (실제 배포 환경)**
```bash
# EC2 콘솔에서 설정할 보안 그룹 규칙
# Inbound Rules: NONE (완전 차단)
# Outbound Rules:
  - HTTPS (443) to 0.0.0.0/0     # AWS API 호출
  - HTTP (80) to 0.0.0.0/0       # 일반 웹 요청
  - Custom (5000) to 0.0.0.0/0   # WebSocket 연결 (아웃바운드)
  - DNS (53) to 0.0.0.0/0        # DNS 조회
  - SSH (22) to 관리자IP/32       # Git 배포 및 관리용 (필요시에만)
```

**핵심 보안 원칙**:
- **인바운드 포트 완전 차단**으로 외부 공격 차단
- **WebSocket 연결은 EC2에서 시작**하는 아웃바운드 연결
- Zendesk 앱이 WebSocket 서버에 연결 요청 시, **서버가 역으로 연결**
- **Git 기반 배포**를 위한 SSH 접근만 관리자 IP로 제한

### 실제 배포 환경 고려사항

**EC2 인스턴스 설정**:
- **Public IP**: WebSocket 아웃바운드 연결용
- **Elastic IP**: 고정 IP로 Zendesk 앱에서 참조
- **인스턴스 타입**: t3.medium 이상 (Q CLI + Service Screener 실행)
- **스토리지**: 최소 20GB (보고서 파일 저장용)

**환경 변수 관리** (EC2에서 설정):
```bash
# /etc/environment 또는 .env 파일
AWS_DEFAULT_REGION=ap-northeast-2
WEBSOCKET_PORT=5000
SLACK_BOT_TOKEN=<기존_토큰>  # 기존 시스템과 호환성
ZENDESK_JWT_SECRET=<새로운_시크릿>
```

### Monitoring and Logging

```python
# Structured logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'structured': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'structured'
        }
    },
    'loggers': {
        'aws_processor': {'level': 'INFO'},
        'websocket_server': {'level': 'INFO'},
        'auth_manager': {'level': 'WARNING'}
    }
}
```