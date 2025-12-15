"""
WebSocket 테스트 클라이언트
로컬에서 WebSocket 서버를 테스트하기 위한 간단한 클라이언트
"""
import asyncio
import json
import websockets
import uuid
from datetime import datetime


async def test_client():
    """테스트 클라이언트 실행"""
    uri = "ws://localhost:8765"
    
    try:
        print(f"WebSocket 서버에 연결 중: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("서버에 연결되었습니다!")
            
            # 연결 확인 메시지 수신
            welcome_message = await websocket.recv()
            print(f"서버 응답: {welcome_message}")
            
            # 테스트 질문들
            test_questions = [
                "안녕하세요! 테스트 질문입니다.",
                "AWS 계정 123456789012 Service Screener 스캔해주세요",
                "보안 보고서 생성해주세요"
            ]
            
            for i, question in enumerate(test_questions):
                message_id = str(uuid.uuid4())
                
                # 질문 전송
                message = {
                    "message_id": message_id,
                    "question": question,
                    "timestamp": datetime.now().isoformat()
                }
                
                print(f"\n[질문 {i+1}] 전송: {question}")
                await websocket.send(json.dumps(message, ensure_ascii=False))
                
                # 응답 수신 (진행 상황 + 최종 결과)
                response_count = 0
                while response_count < 2:  # progress + result
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        response_data = json.loads(response)
                        
                        if response_data["type"] == "progress":
                            print(f"  진행 상황: {response_data['message']}")
                        elif response_data["type"] == "result":
                            print(f"  최종 결과: {response_data['data']['answer']}")
                        elif response_data["type"] == "error":
                            print(f"  오류: {response_data['message']}")
                        
                        response_count += 1
                        
                    except asyncio.TimeoutError:
                        print("  응답 타임아웃")
                        break
                
                # 잠시 대기
                await asyncio.sleep(1)
            
            print("\n모든 테스트 완료!")
            
    except Exception as e:
        print(f"연결 오류: {e}")


if __name__ == "__main__":
    asyncio.run(test_client())