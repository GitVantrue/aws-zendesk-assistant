"""
AWS Zendesk Assistant - WebSocket Server + FastAPI Server
메인 진입점
"""
import asyncio
import signal
import sys
import threading
import time
from hybrid_server import HybridServer
from utils.logging_config import setup_logging, log_info, log_error


# 전역 변수로 서버 참조 유지
_server = None
_main_task = None


def start_fastapi_server():
    """FastAPI 서버를 별도 스레드에서 실행"""
    try:
        import uvicorn
        log_info("FastAPI 서버 시작 중...")
        
        # uvicorn 직접 실행 (간단한 방식)
        uvicorn.run(
            "zendesk_app.server.main:app",
            host="0.0.0.0",
            port=8000,
            log_level="info",
            access_log=False,
            server_header=False
        )
    except Exception as e:
        log_error(f"FastAPI 서버 시작 실패: {e}")


def signal_handler(signum, frame):
    """종료 시그널 핸들러"""
    log_info("종료 시그널 수신, 서버를 중지합니다...")
    if _main_task:
        _main_task.cancel()
    sys.exit(0)


async def main():
    """메인 함수"""
    global _server, _main_task
    
    # 로깅 설정
    logger = setup_logging("DEBUG")
    
    log_info("AWS Zendesk Assistant 시작")
    
    # FastAPI 서버를 별도 스레드에서 시작 (non-daemon)
    fastapi_thread = threading.Thread(target=start_fastapi_server, daemon=False)
    fastapi_thread.start()
    time.sleep(2)  # FastAPI 서버 시작 대기
    log_info("✅ FastAPI 서버 시작됨: http://0.0.0.0:8000")
    
    # Hybrid 서버 생성 (HTTP + WebSocket)
    _server = HybridServer(host="0.0.0.0", port=8765)
    
    # 종료 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 서버 시작
        _main_task = asyncio.current_task()
        await _server.start()
    except asyncio.CancelledError:
        log_info("메인 태스크 취소됨")
    except Exception as e:
        log_error(f"서버 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_info("키보드 인터럽트 수신")
    except Exception as e:
        log_error(f"예상치 못한 오류: {e}")
        sys.exit(1)
    finally:
        log_info("AWS Zendesk Assistant 종료")