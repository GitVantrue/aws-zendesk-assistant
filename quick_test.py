"""
빠른 WebSocket 서버 테스트
서버 시작 후 자동으로 종료되는 테스트
"""
import asyncio
import json
import websockets
from websocket_server import WebSocketServer
from utils.logging_config import setup_logging, log_info

async def test_server():
    """서버 테스트"""
    setup_logging("DEBUG")
    
    # 서버 생성
    server = WebSocketServer(host="localhost", port=8765)
    
    # 서버 시작 (백그라운드)
    server_task = asyncio.create_task(server.start_server())
    
    # 잠시 대기 (서버 시작 시간)
    await asyncio.sleep(1)
    
    try:
        # 클라이언트 연결 테스트
        uri = "ws://localhost:8765"
        async with websockets.connect(uri) as websocket:
            log_info("✅ 클라이언트 연결 성공!")
            
            # 환영 메시지 수신
            welcome = await websocket.recv()
            log_info(f"서버 응답: {json.loads(welcome)['message']}")
            
            # 테스트 메시지 전송
            test_message = {
                "message_id": "test-001",
                "question": "테스트 질문입니다"
            }
            await websocket.send(json.dumps(test_message))
            log_info("✅ 메시지 전송 성공!")
            
            # 진행 상황 메시지 수신
            progress = await websocket.recv()
            progress_data = json.loads(progress)
            log_info(f"진행 상황: {progress_data['message']}")
            
            # 결과 메시지 수신
            result = await websocket.recv()
            result_data = json.loads(result)
            log_info(f"✅ 결과 수신: {result_data['data']['answer']}")
            
    except Exception as e:
        log_info(f"❌ 테스트 실패: {e}")
    
    # 서버 종료
    await server.stop_server()
    server_task.cancel()
    
    log_info("🎉 WebSocket 서버 테스트 완료!")

if __name__ == "__main__":
    asyncio.run(test_server())