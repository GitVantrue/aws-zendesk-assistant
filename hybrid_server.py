"""
Hybrid HTTP/WebSocket Server
ALB 호환성을 위한 HTTP + WebSocket 서버
"""
import asyncio
import json
import websockets
from aiohttp import web, WSMsgType
from typing import Dict, Set, Optional, Any
from datetime import datetime
from utils.logging_config import log_debug, log_error, log_info


class HybridServer:
    """
    HTTP와 WebSocket을 모두 지원하는 하이브리드 서버
    ALB 헬스체크와 WebSocket 연결을 동시에 처리
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        
        # Reference 코드와 동일한 처리 중인 질문 추적
        self.processing_questions: Set[str] = set()
        
        # 연결된 클라이언트 관리
        self.connected_clients: Dict[str, Any] = {}
        
        # Heartbeat 관리
        self.heartbeat_interval = 20  # 20초마다 ping (더 자주)
        self.heartbeat_task = None
        
        # HTTP 앱
        self.app = web.Application()
        self.setup_routes()
        
        log_debug(f"Hybrid 서버 초기화: {host}:{port}")
    
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
        
        log_debug(f"WebSocket 클라이언트 연결됨: {client_id}")
        
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
                            await ws.send_str(json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}))
                        elif data.get("type") == "pong":
                            # 서버 ping에 대한 클라이언트 pong 응답 - 무시
                            log_debug(f"Pong 수신: {client_id}")
                        else:
                            # 일반 질문 메시지 처리
                            await self.handle_websocket_message(client_id, msg.data)
                    except json.JSONDecodeError:
                        # JSON이 아닌 메시지는 일반 메시지로 처리
                        await self.handle_websocket_message(client_id, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    log_error(f'WebSocket 오류: {ws.exception()}')
                    break
        except Exception as e:
            log_error(f"WebSocket 처리 중 오류: {client_id} - {e}")
        finally:
            # 클라이언트 연결 해제
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
                log_debug(f"WebSocket 클라이언트 연결 해제됨: {client_id}")
        
        return ws
    
    async def handle_websocket_message(self, client_id: str, raw_message: str):
        """WebSocket 메시지 처리"""
        try:
            # JSON 파싱
            message_data = json.loads(raw_message)
            
            # 필수 필드 확인
            if "message_id" not in message_data or "question" not in message_data:
                await self.send_error(client_id, "message_id와 question 필드가 필요합니다")
                return
            
            message_id = message_data["message_id"]
            question = message_data["question"].strip()
            
            if not question:
                await self.send_error(client_id, "질문이 비어있습니다")
                return
            
            # Reference 코드와 동일한 중복 방지 로직
            question_key = f"{client_id}:{message_id}"
            
            if question_key in self.processing_questions:
                log_debug(f"중복 질문 무시: {question_key}")
                return
            
            log_debug(f"새 질문 처리: {question_key}")
            log_debug(f"질문 내용: {question}")
            
            # 처리 중 목록에 추가
            self.processing_questions.add(question_key)
            
            # 즉시 처리 중 메시지 전송
            await self.send_progress_update(client_id, "🔄 요청을 처리하고 있습니다. 잠시만 기다려주세요...")
            
            # 비동기 처리 시작
            asyncio.create_task(self.process_question_async(client_id, question, question_key))
            
        except json.JSONDecodeError:
            await self.send_error(client_id, "잘못된 JSON 형식입니다")
        except Exception as e:
            log_error(f"메시지 처리 중 오류: {e}")
            await self.send_error(client_id, f"메시지 처리 중 오류가 발생했습니다: {str(e)}")
    
    async def send_message(self, client_id: str, message: Dict[str, Any]) -> bool:
        """클라이언트에게 메시지 전송"""
        if client_id not in self.connected_clients:
            log_error(f"클라이언트를 찾을 수 없음: {client_id}")
            return False
        
        try:
            ws = self.connected_clients[client_id]
            await ws.send_str(json.dumps(message, ensure_ascii=False))
            log_debug(f"메시지 전송 완료: {client_id}")
            return True
        except Exception as e:
            log_error(f"메시지 전송 실패: {client_id} - {e}")
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
            return False
    
    async def send_progress_update(self, client_id: str, message: str):
        """진행 상황 업데이트 전송"""
        progress_message = {
            "type": "progress",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, progress_message)
    
    async def send_result(self, client_id: str, result: Dict[str, Any]):
        """최종 결과 전송"""
        result_message = {
            "type": "result",
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, result_message)
    
    async def send_error(self, client_id: str, error_message: str):
        """에러 메시지 전송"""
        error_msg = {
            "type": "error",
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, error_msg)
    
    async def process_question_async(self, client_id: str, question: str, question_key: str):
        """질문 비동기 처리 (LangGraph 에이전트 통합)"""
        try:
            log_debug(f"질문 처리 시작: {question_key}")
            
            # LangGraph 에이전트 워크플로우 실행
            from langgraph_agent import process_question_workflow
            
            ws = self.connected_clients.get(client_id)
            if not ws:
                log_error(f"WebSocket 연결을 찾을 수 없음: {client_id}")
                return
            
            # 워크플로우 실행 (aiohttp WebSocket 객체 전달)
            final_state = await process_question_workflow(
                question=question,
                question_key=question_key,
                client_id=client_id,
                websocket=ws
            )
            
            # 오류 처리
            if final_state["processing_status"] == "error":
                await self.send_error(client_id, final_state["error_message"])
            
            log_debug(f"질문 처리 완료: {question_key} (상태: {final_state['processing_status']})")
            
        except Exception as e:
            log_error(f"질문 처리 중 오류: {question_key} - {e}")
            await self.send_error(client_id, f"처리 중 오류가 발생했습니다: {str(e)}")
        finally:
            # 처리 완료 후 목록에서 제거
            self.processing_questions.discard(question_key)
    
    async def start_server(self):
        """서버 시작"""
        log_info(f"Hybrid 서버 시작: {self.host}:{self.port}")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        log_info("Hybrid 서버가 시작되었습니다")
        log_info(f"HTTP 헬스체크: http://{self.host}:{self.port}/health")
        log_info(f"WebSocket 연결: ws://{self.host}:{self.port}/ws")
        
        # Heartbeat 시작
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        # 서버 실행 유지
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            log_info("서버 종료 중...")
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            await runner.cleanup()
    
    async def heartbeat_loop(self):
        """주기적으로 클라이언트에게 ping 전송"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # 연결된 모든 클라이언트에게 ping 전송
                disconnected_clients = []
                for client_id, ws in self.connected_clients.items():
                    try:
                        ping_message = {
                            "type": "ping",
                            "timestamp": datetime.now().isoformat()
                        }
                        await ws.send_str(json.dumps(ping_message))
                        log_debug(f"Heartbeat 전송: {client_id}")
                    except Exception as e:
                        log_debug(f"Heartbeat 실패, 클라이언트 제거: {client_id} - {e}")
                        disconnected_clients.append(client_id)
                
                # 연결이 끊어진 클라이언트 정리
                for client_id in disconnected_clients:
                    if client_id in self.connected_clients:
                        del self.connected_clients[client_id]
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"Heartbeat 루프 오류: {e}")
    
    def get_server_stats(self) -> Dict[str, Any]:
        """서버 통계 정보 반환"""
        return {
            "connected_clients": len(self.connected_clients),
            "processing_questions": len(self.processing_questions),
            "client_ids": list(self.connected_clients.keys())
        }