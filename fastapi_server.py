"""
FastAPI 서버 (독립 실행)
역할: UI 렌더링 + 티켓 정보 관리
"""
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI 앱 초기화
app = FastAPI(title="AWS Zendesk Assistant")

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# 경로 설정
BASE_DIR = Path(__file__).parent
TEMPLATE_DIR = BASE_DIR / "zendesk_app" / "server" / "templates"
STATIC_DIR = BASE_DIR / "zendesk_app" / "server" / "static"

# 템플릿 설정
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# 정적 파일 마운트
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def get_websocket_url(request: Request) -> str:
    """WebSocket URL 생성 (ALB 도메인 사용)"""
    # ALB 도메인 (고정)
    alb_domain = "q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com"
    
    # WebSocket URL 생성 (포트 8000, wss 사용)
    return f"wss://{alb_domain}:8000"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 페이지"""
    try:
        websocket_url = get_websocket_url(request)
        logger.info(f"[DEBUG] WebSocket URL: {websocket_url}")
        
        # 템플릿 렌더링
        try:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "websocket_url": websocket_url
            })
        except Exception as template_error:
            logger.error(f"[ERROR] 템플릿 렌더링 실패: {template_error}")
            # 템플릿 파일이 없으면 간단한 HTML 반환
            return f"""
            <!DOCTYPE html>
            <html>
            <head><title>AWS Zendesk Assistant</title></head>
            <body>
                <h1>AWS Zendesk Assistant</h1>
                <p>WebSocket URL: {websocket_url}</p>
            </body>
            </html>
            """
        
    except Exception as e:
        logger.error(f"[ERROR] 페이지 렌더링 실패: {e}")
        return f"<h1>오류 발생</h1><p>{str(e)}</p>"


@app.get("/health")
async def health(request: Request):
    """헬스 체크"""
    return {
        "status": "healthy",
        "service": "AWS Zendesk Assistant FastAPI",
        "websocket_url": get_websocket_url(request)
    }


if __name__ == "__main__":
    logger.info("[INFO] FastAPI 서버 시작: http://0.0.0.0:8001")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
        access_log=False,
        server_header=False
    )
