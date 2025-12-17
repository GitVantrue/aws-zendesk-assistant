# AWS Zendesk WebSocket Agent - 프로젝트 가이드라인

## 프로젝트 목표

**WebSocket 기반 Zendesk ↔ EC2(Q CLI) 챗봇 구현**

기존 `reference_slack_bot.py`의 모든 기능을 유지하되, Slack API 대신 WebSocket을 통해 Zendesk와 연동하는 시스템을 구축합니다.

## 핵심 아키텍처

```
Zendesk App ←→ WebSocket ←→ LangGraph Agent ←→ AWS Tools (Q CLI)
```

- **통신**: WebSocket 기반 실시간 세션
- **오케스트레이션**: LangGraph Agent 
- **기능**: reference_slack_bot.py의 모든 AWS 분석 기능
- **환경**: 새 EC2, /root/ 하위 구조 (기존 코드와 동일)

## 개발 우선순위

1. **1순위**: 로컬 WebSocket 서버 구현 및 테스트
2. **2순위**: 모든 AWS 기능 구현 완료
3. **3순위**: Zendesk 앱 개발 (가장 후순위)

## 작업 태도 가이드라인

### ⚠️ 필수 준수사항

1. **작업 시작 시 환경 확인 (최우선)**
   - 프로젝트 시작할 때 **반드시** 먼저 질문: "집에서 작업하시나요, 회사에서 작업하시나요?"
   - 집에서 작업한다고 답하면: WSL 명령어 사용 (wsl bash -c "...")
   - 회사에서 작업한다고 답하면: 일반 PowerShell 명령어 사용
   - **이 질문을 빠뜨리지 말 것 - 매우 중요함**

2. **사용자 요청 전에 파일 수정/생성/삭제 금지**
   - 반드시 사용자 확인 후 진행
   - "~해도 될까요?" 형태로 먼저 질문

3. **명확한 확인 후 진행**
   - 모호한 상황에서는 반드시 사용자에게 확인
   - 추측하지 말고 정확한 요구사항 파악

4. **간결하고 직접적인 커뮤니케이션**
   - 불필요한 설명 최소화
   - 핵심만 간단명료하게 전달

## 기술 구현 방향

### Reference 코드 활용

**기존 기능 100% 재사용:**
- `reference_slack_bot.py`의 모든 AWS 분석 로직
- Cross-account 인증 방식
- Service Screener 실행 로직
- 보안 보고서 생성 로직
- CloudTrail/CloudWatch/General AWS MCP 연동

**변경 부분:**
- Slack API → WebSocket 통신
- Flask 라우팅 → LangGraph 워크플로우

### 환경 설정

**새 EC2 환경:**
- Q CLI 설치: `/root/` 하위
- Service Screener: `/root/service-screener-v2/`
- 기존 reference 코드와 동일한 경로 구조

**로컬 개발:**
- WebSocket 서버 로컬 테스트
- 모든 기능 검증 후 EC2 배포

## 배포 워크플로우

### 작업 환경 분리 (매우 중요)

**로컬: Kiro IDE (코드 수정만)**
- 파일 수정, 생성, 삭제
- Git add/commit/push 실행
- 코드 리뷰 및 테스트 계획

**EC2: 실제 실행 환경 (별도)**
- Git pull로 코드 받기
- 실제 테스트 실행
- 서비스 재시작
- 로그 확인

### Git 작업 범위 (Kiro가 실행)
```bash
# 회사에서 작업 시 (일반 PowerShell)
git add .
git commit -m "메시지"
git push origin main
```

### EC2 배포 명령어 (사용자가 실행)
**Git push 완료 후 반드시 다음 명령어를 사용자에게 제공:**
```bash
cd /root/aws-zendesk-assistant
git pull origin main
sudo pkill -f main.py
nohup python3 main.py > /tmp/websocket_server.log 2>&1 &
tail -f /tmp/websocket_server.log
```

**중요**: 
- **Kiro는 git push까지만 실행** (로컬에서)
- **EC2 명령어는 사용자가 직접 실행** (EC2에서)
- 로컬에서 EC2 명령어를 실행하면 안 됨
- **매번 git push 후 위 EC2 명령어를 반드시 사용자에게 제공할 것**

## 현재 상태

### ✅ 완료된 작업
- **프로젝트 구조**: 기존 코드 정리, Reference 파일 보존 완료
- **스펙 문서**: Requirements → Design → Tasks 문서 작성 완료
- **WebSocket 서버**: Hybrid HTTP/WebSocket 서버 구현 완료 (ALB 호환)
- **하트비트**: 20초 간격 ping/pong으로 연결 지속성 확보
- **AWS 인증**: Cross-account 인증 시스템 구현 완료
- **LangGraph 에이전트**: 질문 라우팅 및 워크플로우 구현 완료
- **Q CLI 통합**: general/cloudtrail/cloudwatch 질문 처리 완료
- **MCP 서버**: 3개 MCP 서버 모두 실행 중 (aws-knowledge, cloudtrail, cloudwatch)
- **출력 정리**: Q CLI 응답에서 불필요한 로그 제거 완료
- **HTML 테스트**: 마크다운 렌더링 지원하는 테스트 환경 완료

### 🔧 기술 상세
- **WebSocket**: aiohttp 기반 hybrid 서버 (HTTP 헬스체크 + WebSocket)
- **인증**: Parameter Store → STS assume role → 임시 자격증명
- **Q CLI**: MCP 서버 활용으로 고품질 AWS 분석 및 한국어 답변
- **컨텍스트**: 질문 유형별 전용 컨텍스트 파일 자동 로드
- **환경변수**: Reference 코드와 동일한 AWS 설정 (EC2 메타데이터 비활성화 등)

### 🎯 다음 단계 (우선순위)
1. **Service Screener 구현** (Task 5) - Python 스크립트 + Q CLI 분석
2. **보안 보고서 구현** (Task 6) - boto3 수집 + Q CLI 분석 + HTML 생성
3. **Zendesk 앱 개발** (최종 단계)

## 핵심 원칙

- **기능 우선**: 모든 AWS 기능이 완벽히 작동해야 함
- **Reference 활용**: 검증된 로직을 최대한 재사용
- **단계적 접근**: 로컬 → EC2 → Zendesk 순서
- **사용자 중심**: 모든 결정은 사용자 확인 후 진행