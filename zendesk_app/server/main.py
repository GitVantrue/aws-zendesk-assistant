"""
AWS Zendesk Assistant - FastAPI 서버
역할: UI 렌더링 + WebSocket 통신 + 티켓 정보 관리
"""
import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import config

# 로깅 설정
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI 앱 초기화
app = FastAPI(title="AWS Zendesk Assistant")

# 템플릿 설정
templates = Jinja2Templates(directory=config.TEMPLATE_DIR)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# 전역 상태
class AppState:
    """앱 상태 관리"""
    def __init__(self):
        self.ticket_data = None
        self.websocket_url = config.WEBSOCKET_URL

app_state = AppState()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ticket: str = None):
    """
    메인 페이지
    
    Args:
        request: FastAPI 요청
        ticket: URL 파라미터로 전달된 티켓 정보 (JSON 인코딩)
    
    Returns:
        렌더링된 HTML
    """
    try:
        # 티켓 정보 파싱
        ticket_data = None
        if ticket:
            try:
                ticket_data = json.loads(ticket)
                app_state.ticket_data = ticket_data
                logger.info(f"[DEBUG] 티켓 정보 수신: {ticket_data.get('id')}")
            except json.JSONDecodeError:
                logger.error("[ERROR] 티켓 정보 파싱 실패")
        
        # 템플릿 렌더링
        return templates.TemplateResponse("index.html", {
            "request": request,
            "ticket_data": ticket_data,
            "websocket_url": app_state.websocket_url
        })
        
    except Exception as e:
        logger.error(f"[ERROR] 페이지 렌더링 실패: {e}")
        return f"<h1>오류 발생</h1><p>{str(e)}</p>"


@app.get("/health")
async def health():
    """헬스 체크"""
    return {
        "status": "healthy",
        "service": "AWS Zendesk Assistant",
        "websocket_url": app_state.websocket_url
    }


@app.get("/api/ticket")
async def get_ticket():
    """현재 티켓 정보 조회"""
    if app_state.ticket_data:
        return app_state.ticket_data
    return {"error": "티켓 정보 없음"}


if __name__ == "__main__":
    import uvicorn
    logger.info(f"[DEBUG] FastAPI 서버 시작: {config.HOST}:{config.PORT}")
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        log_level=config.LOG_LEVEL.lower()
    )
