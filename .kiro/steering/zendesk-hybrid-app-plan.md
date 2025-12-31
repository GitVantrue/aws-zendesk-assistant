# Zendesk 하이브리드 앱 개발 계획

**작성일**: 2025-12-31
**상태**: 진행 중
**환경**: 회사 (PowerShell)

---

## 📋 프로젝트 개요

### 목표
Zendesk 마켓플레이스 배포 가능한 하이브리드 Zendesk 앱 개발
- **프론트엔드**: JavaScript (Zendesk 요구사항)
- **백엔드**: Python (기존 WebSocket 활용)
- **통신**: WebSocket (기존 구현 재사용)

### 핵심 원칙
1. **3197496 폴더는 참고용만** - 티켓 정보 가져오는 방식만 참고
2. **기존 WebSocket 백엔드 100% 활용** - `hybrid_server.py`, `langgraph_agent.py` 그대로 사용
3. **UI 최우선** - 사용자 경험에 최대한 신경 쓰기
4. **Support Case 기능 추가 예정** - 향후 확장 가능하도록 설계

---

## 🏗️ 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│         Zendesk Support (마켓플레이스)                   │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Zendesk App (JavaScript - 최소 코드)             │  │
│  │  ├── manifest.json                                │  │
│  │  ├── assets/iframe.html (로더)                    │  │
│  │  └── assets/main.js (티켓 정보 + WebSocket 연결) │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ WebSocket
┌──────────────────────▼──────────────────────────────────┐
│  Python FastAPI 서버 (UI + 로직)                        │
│  ├── main.py (FastAPI 앱)                              │
│  ├── templates/                                         │
│  │   ├── index.html (메인 채팅 UI)                     │
│  │   ├── support_case.html (Support Case UI)           │
│  │   └── base.html (기본 템플릿)                       │
│  ├── static/                                            │
│  │   ├── styles.css (AWS 테마)                         │
│  │   ├── app.js (UI 로직)                              │
│  │   └── websocket.js (WebSocket 통신)                 │
│  └── requirements.txt                                   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  기존 WebSocket 백엔드 (hybrid_server.py)               │
│  ├── LangGraph 에이전트 (langgraph_agent.py)            │
│  ├── AWS Tools                                          │
│  │   ├── Service Screener                              │
│  │   ├── Security Report (월간 보고서)                 │
│  │   ├── CloudTrail                                    │
│  │   └── CloudWatch                                    │
│  └── Support Case 처리 (신규)                           │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 프로젝트 구조

```
aws-zendesk-assistant/
├── 3197496/                         # 참고용 (수정 금지)
│   ├── manifest.json
│   ├── assets/
│   │   ├── iframe.html
│   │   ├── main.js
│   │   └── styles.css
│   └── server/
│
├── hybrid_server.py                 # 기존 WebSocket 서버 (수정 금지)
├── langgraph_agent.py               # 기존 LangGraph 에이전트 (수정 금지)
├── main.py                          # 기존 메인 (수정 금지)
├── aws_tools/                       # 기존 AWS 도구 (수정 금지)
│
├── zendesk_app/                     # 새로운 Zendesk 앱 (신규)
│   ├── manifest.json                # Zendesk 앱 설정
│   ├── assets/
│   │   ├── iframe.html              # 로더 (최소 코드)
│   │   ├── main.js                  # 티켓 정보 + WebSocket 연결
│   │   └── logo.svg
│   │
│   └── server/                      # Python FastAPI 서버
│       ├── main.py                  # FastAPI 앱
│       ├── requirements.txt
│       ├── config.py                # 설정
│       ├── templates/
│       │   ├── base.html            # 기본 템플릿
│       │   ├── index.html           # 메인 UI
│       │   └── support_case.html    # Support Case UI
│       └── static/
│           ├── styles.css           # AWS 테마
│           ├── app.js               # UI 로직
│           └── websocket.js         # WebSocket 통신
│
└── README.md
```

---

## 🔄 통신 흐름

### 1단계: Zendesk 앱 로드
```
Zendesk Support
  ↓
assets/main.js 실행
  ├─ Zendesk 티켓 정보 수집 (3197496 참고)
  ├─ Python 서버 URL 가져오기
  └─ iframe에 Python UI 로드
```

### 2단계: Python UI 렌더링
```
FastAPI 서버 (main.py)
  ↓
templates/index.html 렌더링
  ├─ 메인 채팅 UI 표시
  ├─ WebSocket 연결 초기화
  └─ 티켓 정보 표시
```

### 3단계: WebSocket 통신
```
static/websocket.js
  ↓
기존 WebSocket 백엔드 (hybrid_server.py)
  ├─ 질문 라우팅 (langgraph_agent.py)
  ├─ AWS 작업 실행
  └─ 결과 스트리밍
```

### 4단계: UI 업데이트
```
static/app.js
  ├─ 실시간 진행 상황 표시
  ├─ 결과 렌더링
  └─ Support Case 정보 표시
```

---

## 📝 구현 단계

### Phase 1: 기본 구조 (현재)
- [ ] Zendesk 앱 (JavaScript 최소 코드) 작성
- [ ] Python FastAPI 서버 기본 설정
- [ ] WebSocket 연결 테스트

### Phase 2: UI 개발
- [ ] 메인 채팅 UI (HTML/CSS/JS)
- [ ] Support Case UI
- [ ] 실시간 진행 상황 표시
- [ ] AWS 테마 스타일링

### Phase 3: 기능 통합
- [ ] 기존 WebSocket 백엔드 연동
- [ ] Service Screener 기능
- [ ] 월간 보고서 기능
- [ ] Support Case 기능 (신규)

### Phase 4: 마켓플레이스 배포
- [ ] 앱 검증
- [ ] 패키징
- [ ] 배포

---

## 🔑 핵심 파일 역할

### 기존 파일 (수정 금지)
| 파일 | 역할 | 상태 |
|------|------|------|
| `hybrid_server.py` | WebSocket 서버 | ✅ 완성 |
| `langgraph_agent.py` | LangGraph 에이전트 | ✅ 완성 |
| `main.py` | 메인 진입점 | ✅ 완성 |
| `aws_tools/` | AWS 도구 모음 | ✅ 완성 |

### 신규 파일 (개발 중)
| 파일 | 역할 | 상태 |
|------|------|------|
| `zendesk_app/manifest.json` | Zendesk 앱 설정 | 🔄 개발 중 |
| `zendesk_app/assets/main.js` | 티켓 정보 + WebSocket | 🔄 개발 중 |
| `zendesk_app/server/main.py` | FastAPI 서버 | 🔄 개발 중 |
| `zendesk_app/server/templates/` | UI 템플릿 | 🔄 개발 중 |
| `zendesk_app/server/static/` | UI 로직 + 스타일 | 🔄 개발 중 |

---

## 🎯 개발 방향

### JavaScript (최소 코드)
```javascript
// assets/main.js
// 역할: 티켓 정보 수집 + Python 서버 연결
// 참고: 3197496/assets/main.js의 티켓 정보 수집 부분만 사용
// 나머지는 Python 서버로 위임
```

### Python (메인 개발)
```python
# server/main.py
# 역할: FastAPI 서버 + UI 렌더링 + WebSocket 통신
# 기존 hybrid_server.py와 langgraph_agent.py 그대로 활용
# 새로운 FastAPI 엔드포인트만 추가
```

---

## 💾 Git 워크플로우

### 로컬 작업 (Kiro)
```bash
# 파일 수정/생성
git add .
git commit -m "메시지"
git push origin main
```

### EC2 배포 (사용자)
```bash
cd /root/aws-zendesk-assistant
git pull origin main
sudo pkill -f main.py
nohup python3 main.py > /tmp/websocket_server.log 2>&1 &
tail -f /tmp/websocket_server.log
```

---

## ✅ 체크리스트

- [x] 프로젝트 목표 명확화
- [x] 아키텍처 설계
- [x] 파일 구조 정의
- [x] 통신 흐름 설계
- [x] 개발 단계 계획
- [ ] Phase 1 구현 시작

---

## 📌 중요 사항

1. **3197496 폴더는 참고용만** - 티켓 정보 수집 방식만 참고
2. **기존 WebSocket 백엔드 수정 금지** - `hybrid_server.py`, `langgraph_agent.py` 그대로 사용
3. **UI 최우선** - 사용자 경험에 최대한 신경 쓰기
4. **Support Case 기능 추가 예정** - 향후 확장 가능하도록 설계
5. **회사 환경** - PowerShell 명령어 사용
6. **마켓플레이스 배포** - 최종 목표

---

## 🚀 다음 단계

**Phase 1 시작**: Zendesk 앱 + Python FastAPI 기본 구조 구축

준비 완료!
