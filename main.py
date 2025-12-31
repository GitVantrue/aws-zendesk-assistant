"""
AWS Zendesk Assistant - WebSocket Server + FastAPI Server
메인 진입점
"""
import asyncio
import signal
import sys
import subprocess
import time
from hybrid_server import HybridServer
from utils.logging_config import setup_logging, log_info, log_error


# 전역 변수로 서버 참조 유지
_server = None
_main_task = None
_fastapi_process = None


def signal_handler(signum, frame):
    """종료 시그널 핸들러"""
    global _fastapi_process
    log_info("종료 시그널 수신, 서버를 중지합니다...")
    
    # FastAPI 프로세스 종료
    if _fastapi_process:
        _fastapi_process.terminate()
        try:
            _fastapi_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _fastapi_process.kill()
    
    if _main_task:
        _main_task.cancel()
    sys.exit(0)


async def main():
    """메인 함수"""
    global _server, _main_task, _fastapi_process
    
    # 로깅 설정
    logger = setup_logging("DEBUG")
    
    log_info("AWS Zendesk Assistant 시작")
    
    # FastAPI 서버 시작 (포트 8000)
    log_info("FastAPI 서버 시작 중...")
    try:
        _fastapi_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "zendesk_app.server.main:app", 
             "--host", "0.0.0.0", "--port", "8000"],
            cwd="/root/aws-zendesk-assistant",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(2)  # FastAPI 서버 시작 대기
        log_info("✅ FastAPI 서버 시작됨: http://0.0.0.0:8000")
    except Exception as e:
        log_error(f"FastAPI 서버 시작 실패: {e}")
    
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