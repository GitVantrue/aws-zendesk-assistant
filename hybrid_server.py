"""
Hybrid HTTP/WebSocket Server for AWS Zendesk Assistant
ALB 호환성을 위한 HTTP + WebSocket 서버
"""

import os
import json
import asyncio
import threading
from aiohttp import web, WSMsgType
from datetime import datetime
from langgraph_agent import process_question_with_agent


class HybridServer:
    """HTTP와 WebSocket을 모두 지원하는 하이브리드 서버"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.connected_clients = {}
        self.processing_questions = set()
        
        # 라우트 설정
        self.setup_routes()
        
        print(f"[DEBUG] Hybrid 서버 초기화: {host}:{port}", flush=True)
    
    def setup_routes(self):
        """HTTP 라우트 설정"""
        self.app.router.add_get('/', self.health_check)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/ws', self.websocket_handler)
        
        # Static 파일 서빙 (보고서 파일들)
        self.app.router.add_static('/reports', '/tmp/reports', name='reports')
    
    async def health_check(self, request):
        """ALB 헬스체크 엔드포인트"""
        return web.json_response({
            "status": "healthy",
            "service": "AWS Zendesk Assistant",
            "timestamp": datetime.now().isoformat(),
            "connected_clients": len(self.connected_clients)
        })
    
    async def websocket_handler(self, request):
        """WebSocket 연결 처리"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        # 클라이언트 등록
        client_id = f"{request.remote}:{datetime.now().timestamp()}"
        self.connected_clients[client_id] = ws
        
        print(f"[DEBUG] WebSocket 클라이언트 연결됨: {client_id}", flush=True)
        
        # 연결 확인 메시지 전송
        welcome_message = {
            "type": "connected",
            "message": "AWS Zendesk Assistant에 연결되었습니다",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }
        await ws.send_str(json.dumps(welcome_message, ensure_ascii=False))
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "ping":
                            # 클라이언트 ping에 대한 Pong 응답
                            await ws.send_str(json.dumps({
                                "type": "pong",
                                "timestamp": datetime.now().isoformat()
                            }))
                        elif data.get("type") == "pong":
                            # 서버 ping에 대한 클라이언트 pong 응답 - 무시
                            print(f"[DEBUG] Pong 수신: {client_id}", flush=True)
                        else:
                            # 일반 질문 메시지 처리
                            await self.handle_websocket_message(client_id, ws, msg.data)
                    except json.JSONDecodeError:
                        # JSON이 아닌 메시지는 일반 메시지로 처리
                        await self.handle_websocket_message(client_id, ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    print(f"[ERROR] WebSocket 오류: {ws.exception()}", flush=True)
                    break
        except Exception as e:
            print(f"[ERROR] WebSocket 처리 중 오류: {client_id} - {e}", flush=True)
        finally:
            # 클라이언트 제거
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
            print(f"[DEBUG] WebSocket 클라이언트 연결 해제: {client_id}", flush=True)
        
        return ws
    
    async def handle_websocket_message(self, client_id: str, ws, message: str):
        """WebSocket 메시지 처리"""
        try:
            print(f"[DEBUG] WebSocket 메시지 수신: {client_id} - {message[:100]}", flush=True)
            
            # 메시지 파싱
            try:
                data = json.loads(message)
                question = data.get("message", message)
                session_id = data.get("session_id", client_id)
            except json.JSONDecodeError:
                question = message
                session_id = client_id
            
            # 중복 방지
            question_key = f"{client_id}:{question}"
            if question_key in self.processing_questions:
                print(f"[DEBUG] 중복 질문 무시: {question_key}", flush=True)
                await ws.send_str(json.dumps({
                    "type": "error",
                    "message": "이미 처리 중인 질문입니다",
                    "session_id": session_id
                }, ensure_ascii=False))
                return
            
            self.processing_questions.add(question_key)
            
            # 처리 중 메시지 전송
            await ws.send_str(json.dumps({
                "type": "processing",
                "message": "요청을 처리하고 있습니다...",
                "session_id": session_id
            }, ensure_ascii=False))
            
            # 비동기로 질문 처리 (LangGraph 에이전트 사용)
            thread = threading.Thread(
                target=self._process_question_thread,
                args=(question, session_id, client_id, ws, question_key)
            )
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            print(f"[ERROR] 메시지 처리 중 오류: {e}", flush=True)
            await ws.send_str(json.dumps({
                "type": "error",
                "message": f"오류 발생: {str(e)}"
            }, ensure_ascii=False))
    
    def _process_question_thread(self, question: str, session_id: str, client_id: str, ws, question_key: str):
        """질문 처리 스레드"""
        try:
            print(f"[DEBUG] 질문 처리 시작: {session_id} - {question}", flush=True)
            
            # LangGraph 에이전트로 질문 처리
            result = process_question_with_agent(question, session_id, ws)
            
            print(f"[DEBUG] 질문 처리 완료: {session_id}", flush=True)
            
        except Exception as e:
            print(f"[ERROR] 질문 처리 중 오류: {e}", flush=True)
            try:
                # 에러 메시지 전송
                asyncio.run(ws.send_str(json.dumps({
                    "type": "error",
                    "message": f"처리 중 오류 발생: {str(e)}",
                    "session_id": session_id
                }, ensure_ascii=False)))
            except:
                pass
        finally:
            self.processing_questions.discard(question_key)
    
    async def send_heartbeat(self):
        """주기적으로 클라이언트에 ping 전송"""
        while True:
            try:
                await asyncio.sleep(20)  # 20초마다
                
                # 모든 연결된 클라이언트에 ping 전송
                disconnected = []
                for client_id, ws in list(self.connected_clients.items()):
                    try:
                        await ws.send_str(json.dumps({
                            "type": "ping",
                            "timestamp": datetime.now().isoformat()
                        }))
                    except Exception as e:
                        print(f"[DEBUG] Ping 전송 실패: {client_id} - {e}", flush=True)
                        disconnected.append(client_id)
                
                # 연결 끊긴 클라이언트 제거
                for client_id in disconnected:
                    if client_id in self.connected_clients:
                        del self.connected_clients[client_id]
                        
            except Exception as e:
                print(f"[ERROR] Heartbeat 오류: {e}", flush=True)
    
    async def start(self):
        """서버 시작"""
        print(f"[DEBUG] Hybrid 서버 시작: {self.host}:{self.port}", flush=True)
        
        # Heartbeat 태스크 시작
        asyncio.create_task(self.send_heartbeat())
        
        # HTTP 서버 시작
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        print(f"[DEBUG] ✅ Hybrid 서버 실행 중: http://{self.host}:{self.port}", flush=True)
        
        # 무한 대기
        await asyncio.Event().wait()


async def main():
    """메인 함수"""
    # /tmp/reports 디렉터리 생성
    os.makedirs('/tmp/reports', exist_ok=True)
    
    # 서버 생성 및 시작
    server = HybridServer(host="0.0.0.0", port=8765)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
