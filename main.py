"""
AWS Zendesk Assistant - WebSocket Server
메인 진입점
"""
import asyncio
import signal
import sys
from websocket_server import WebSocketServer
from utils.logging_config import setup_logging, log_info, log_error


async def main():
    """메인 함수"""
    # 로깅 설정
    logger = setup_logging("DEBUG")
    
    log_info("AWS Zendesk Assistant 시작")
    
    # WebSocket 서버 생성
    server = WebSocketServer(host="localhost", port=8765)
    
    # 종료 시그널 핸들러
    def signal_handler(signum, frame):
        log_info("종료 시그널 수신, 서버를 중지합니다...")
        asyncio.create_task(server.stop_server())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 서버 시작
        await server.start_server()
    except Exception as e:
        log_error(f"서버 실행 중 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())