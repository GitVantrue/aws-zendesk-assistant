# FastAPI WebSocket 통합 가이드

**작성일**: 2025-01-08
**상태**: 구현 필요
**환경**: EC2 (모든 서비스 실행 중)

---

## 📋 현재 상황 분석

### ✅ 완료된 부분
1. **백엔드 기능**: 모두 구현 완료
   - `hybrid_server.py` (포트 8001): WebSocket 서버 + HTTP 헬스체크
   - `langgraph_agent.py`: 질문 라우팅 및 AWS 작업 처리
   - `aws_tools/`: Service Screener, 월간보고서, CloudTrail, CloudWatch 등

2. **프론트엔드 UI**: 완성됨
   - `zendesk_app/server/templates/index.html`: 대시보드 UI
   - `zendesk_app/server/static/app.js`: 대시보드 로직
   - `zendesk_app/server/static/websocket.js`: WebSocket 클라이언트 로직
   - `zendesk_app/server/static/styles.css`: AWS 테마 스타일

3. **FastAPI 서버**: 기본 구조만 있음
   - `fastapi_server.py`: 정적 파일 제공만 가능
   - 포트 8000에서 실행 중

### ❌ 문제점
**LB DNS 접속 시 UI는 나오지만 버튼 클릭 시 기능이 동작하지 않음**

원인:
- FastAPI 서버가 **WebSocket 엔드포인트를 제공하지 않음**
- 클라이언트 JS에서 `sendQuestion()` 호출 → WebSocket 메시지 전송 시도
- 하지만 FastAPI에 WebSocket 핸들러가 없어서 연결 실패
- 백엔드 `hybrid_server.py`의 WebSocket 서버(포트 8001)와 통신 불가

### 🔄 통신 흐름 (현재 - 작동 안 함)
```
브라우저 (LB DNS)
  ↓
FastAPI 서버 (포트 8000)
  ├─ HTML/CSS/JS 제공 ✅
  └─ WebSocket 엔드포인트 ❌ (없음)
  
백엔드 WebSocket 서버 (포트 8001)
  ├─ LangGraph 에이전트
  ├─ AWS 작업 처리
  └─ 결과 반환
```

---

## 🔧 해결 방법

### 필요한 작업
FastAPI 서버에 **WebSocket 프록시 엔드포인트** 추가

### 구현 방식
1. FastAPI에 `/ws` 엔드포인트 추가
2. 클라이언트 WebSocket 연결 수락
3. 백엔드 `hybrid_server.py`의 WebSocket 서버로 메시지 전달
4. 백엔드 응답을 클라이언트로 반환

### 수정할 파일
- `fastapi_server.py`: WebSocket 프록시 로직 추가

### 예상 통신 흐름 (수정 후)
```
브라우저 (LB DNS)
  ↓
FastAPI 서버 (포트 8000)
  ├─ HTML/CSS/JS 제공 ✅
  └─ WebSocket 프록시 (/ws) ← 추가 필요
       ↓
백엔드 WebSocket 서버 (포트 8001)
  ├─ LangGraph 에이전트
  ├─ AWS 작업 처리
  └─ 결과 반환
```

---

## 📝 구현 체크리스트

- [ ] FastAPI에 WebSocket 프록시 엔드포인트 추가
- [ ] 클라이언트 WebSocket URL 수정 (필요시)
- [ ] EC2에서 테스트
- [ ] 버튼 클릭 시 기능 동작 확인

---

## 🚀 배포 명령어 (EC2)

```bash
cd /root/aws-zendesk-assistant
git pull origin main
sudo pkill -f fastapi_server.py
sudo pkill -f main.py
nohup python3 fastapi_server.py > /tmp/fastapi_server.log 2>&1 &
nohup python3 main.py > /tmp/websocket_server.log 2>&1 &
tail -f /tmp/fastapi_server.log
```

---

## 📌 중요 사항

1. **포트 구성**
   - FastAPI: 8000 (ALB를 통해 외부 접근)
   - WebSocket 백엔드: 8001 (내부 통신)

2. **ALB 설정**
   - 포트 80/443 → FastAPI 8000으로 라우팅
   - WebSocket 업그레이드 지원 필요

3. **환경 변수**
   - `WEBSOCKET_BACKEND_URL`: `ws://localhost:8001` (내부 통신)
   - `WEBSOCKET_CLIENT_URL`: `wss://[ALB_DOMAIN]:8001` (클라이언트용)

---

## 🔗 관련 파일

- `fastapi_server.py`: FastAPI 메인 서버
- `hybrid_server.py`: 백엔드 WebSocket 서버
- `zendesk_app/server/static/websocket.js`: 클라이언트 WebSocket 로직
- `zendesk_app/server/templates/index.html`: UI 템플릿
