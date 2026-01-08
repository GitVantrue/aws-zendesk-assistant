"""
FastAPI 서버 (독립 실행)
역할: UI 렌더링 + WebSocket 프록시
"""
import logging
import os
import sys
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import websockets

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 백엔드 WebSocket 서버 설정
BACKEND_WEBSOCKET_URL = os.getenv("WEBSOCKET_BACKEND_URL", "ws://localhost:8001")
logger.info(f"[INFO] 백엔드 WebSocket URL: {BACKEND_WEBSOCKET_URL}")

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

# 캐시 방지 미들웨어
@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    # 모든 응답에 캐시 방지 헤더 추가
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def get_websocket_url(request: Request) -> str:
    """WebSocket URL 생성 (ALB 도메인 사용)"""
    # ALB 도메인 (고정)
    alb_domain = "q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com"
    
    # WebSocket URL 생성 (포트 8001, wss 사용)
    return f"wss://{alb_domain}:8001"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 페이지"""
    try:
        websocket_url = get_websocket_url(request)
        logger.info(f"[DEBUG] WebSocket URL: {websocket_url}")
        
        # 템플릿 렌더링
        try:
            response = templates.TemplateResponse("index.html", {
                "request": request,
                "websocket_url": websocket_url
            })
            # 캐시 방지 헤더 추가
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 프록시 엔드포인트
    클라이언트 ↔ FastAPI ↔ 백엔드 WebSocket 서버
    """
    await websocket.accept()
    logger.info("[DEBUG] 클라이언트 WebSocket 연결됨")
    
    backend_ws = None
    
    try:
        # 백엔드 WebSocket 서버에 연결 (경로 포함)
        backend_url = f"{BACKEND_WEBSOCKET_URL}/ws"
        logger.info(f"[DEBUG] 백엔드 연결 시도: {backend_url}")
        backend_ws = await websockets.connect(backend_url)
        logger.info("[DEBUG] 백엔드 WebSocket 연결 성공")
        
        # 클라이언트에 연결 확인 메시지 전송
        await websocket.send_json({
            "type": "connected",
            "message": "FastAPI WebSocket 프록시 연결됨"
        })
        
        # 양방향 메시지 전달
        async def forward_from_client():
            """클라이언트 → 백엔드"""
            try:
                while True:
                    data = await websocket.receive_text()
                    logger.info(f"[DEBUG] 클라이언트 메시지 수신: {data[:100]}")
                    
                    # 백엔드로 전달
                    await backend_ws.send(data)
                    logger.info("[DEBUG] 백엔드로 메시지 전달 완료")
                    
            except WebSocketDisconnect:
                logger.info("[DEBUG] 클라이언트 연결 종료")
                raise
            except Exception as e:
                logger.error(f"[ERROR] 클라이언트 메시지 처리 오류: {e}")
                raise
        
        async def forward_from_backend():
            """백엔드 → 클라이언트"""
            try:
                while True:
                    data = await backend_ws.recv()
                    logger.info(f"[DEBUG] 백엔드 메시지 수신: {data[:100]}")
                    
                    # 클라이언트로 전달
                    await websocket.send_text(data)
                    logger.info("[DEBUG] 클라이언트로 메시지 전달 완료")
                    
            except websockets.exceptions.ConnectionClosed:
                logger.info("[DEBUG] 백엔드 연결 종료")
                raise
            except Exception as e:
                logger.error(f"[ERROR] 백엔드 메시지 처리 오류: {e}")
                raise
        
        # 두 개의 태스크를 동시에 실행 (하나가 실패해도 계속 실행)
        try:
            await asyncio.gather(
                forward_from_client(),
                forward_from_backend(),
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"[ERROR] 메시지 전달 중 오류: {e}")
        
    except Exception as e:
        logger.error(f"[ERROR] WebSocket 프록시 오류: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"WebSocket 연결 오류: {str(e)}"
            })
        except:
            pass
        
    finally:
        # 정리
        if backend_ws:
            try:
                await backend_ws.close()
                logger.info("[DEBUG] 백엔드 WebSocket 연결 종료")
            except:
                pass
        
        try:
            await websocket.close()
            logger.info("[DEBUG] 클라이언트 WebSocket 연결 종료")
        except:
            pass


if __name__ == "__main__":
    logger.info("[INFO] FastAPI 서버 시작: http://0.0.0.0:8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False,
        server_header=False
    )
