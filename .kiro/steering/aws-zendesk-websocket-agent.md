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

### Git 작업 범위
```bash
# 집에서 작업 시 (WSL 사용)
wsl bash -c "cd /mnt/c/Users/kimhs/Desktop/Work/Kiro/aws-zendesk-assistant && git add . && git commit -m '메시지' && git push origin main"

# 회사에서 작업 시 (일반 PowerShell)
git add .
git commit -m "메시지"
git push origin main
```

### EC2 배포 명령어 (항상 제공)
**Git push 완료 후 반드시 다음 명령어를 사용자에게 제공:**
```bash
cd /root/aws-zendesk-assistant
git pull origin main
sudo pkill -f main.py
nohup python3 main.py > /tmp/websocket_server.log 2>&1 &
tail -f /tmp/websocket_server.log
```

**중요**: 
- Kiro는 git push까지만 실행
- EC2 명령어는 사용자에게 제공만 함
- **매번 git push 후 위 EC2 명령어를 반드시 제공할 것**

## 현재 상태

### ✅ 완료된 작업
- 기존 코드 정리 완료
- Reference 파일 보존 (`reference_slack_bot.py`, `reference_contexts/`, `reference_templates/`)
- 깨끗한 프로젝트 구조 준비

### 🎯 다음 단계
1. 새로운 스펙 문서 작성 (Requirements → Design → Tasks)
2. LangGraph 기반 WebSocket 서버 구현
3. Reference 로직을 LangGraph Tool로 변환
4. 로컬 테스트 및 검증
5. EC2 배포 및 통합 테스트
6. Zendesk 앱 개발

## 핵심 원칙

- **기능 우선**: 모든 AWS 기능이 완벽히 작동해야 함
- **Reference 활용**: 검증된 로직을 최대한 재사용
- **단계적 접근**: 로컬 → EC2 → Zendesk 순서
- **사용자 중심**: 모든 결정은 사용자 확인 후 진행