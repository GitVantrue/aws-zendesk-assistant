"""
간단한 WebSocket 테스트 (import 오류 방지)
"""
import asyncio
import json
import websockets

async def test_simple():
    """간단한 연결 테스트"""
    try:
        print("WebSocket 서버에 연결 중: ws://localhost:8765")
        
        async with websockets.connect("ws://localhost:8765") as websocket:
            print("✅ 연결 성공!")
            
            # 환영 메시지 수신
            welcome = await websocket.recv()
            print(f"서버 응답: {welcome}")
            
            # 간단한 메시지 전송
            message = {
                "message_id": "simple-test",
                "question": "간단한 테스트입니다"
            }
            
            await websocket.send(json.dumps(message))
            print("✅ 메시지 전송 완료")
            
            # 응답 수신
            for i in range(3):  # 최대 3개 응답
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(response)
                    print(f"응답 {i+1}: {data.get('type', 'unknown')} - {data.get('message', data.get('data', 'no message'))}")
                except asyncio.TimeoutError:
                    print("응답 타임아웃")
                    break
                except Exception as e:
                    print(f"응답 처리 오류: {e}")
                    break
            
            print("🎉 테스트 완료!")
            
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple())