"""
WebSocket Server
Zendesk와 통신하는 WebSocket 서버
Reference 코드의 processing_questions 추적 방식 재사용
"""
import asyncio
import json
import websockets
import threading
from typing import Dict, Set, Optional, Any
from datetime import datetime
from utils.logging_config import log_debug, log_error, log_info


class WebSocketServer:
    """
    WebSocket 서버 클래스
    Reference 코드의 processing_questions 추적 방식을 WebSocket에 적용
    """
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        
        # Reference 코드와 동일한 처리 중인 질문 추적
        self.processing_questions: Set[str] = set()
        
        # 연결된 클라이언트 관리
        self.connected_clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        
        # 서버 인스턴스
        self.server = None
        
        log_debug(f"WebSocket 서버 초기화: {host}:{port}")
    
    async def register_client(self, websocket: websockets.WebSocketServerProtocol, path: str) -> str:
        """
        클라이언트 연결 등록
        
        Args:
            websocket: WebSocket 연결
            path: 연결 경로
            
        Returns:
            클라이언트 ID
        """
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}:{datetime.now().timestamp()}"
        self.connected_clients[client_id] = websocket
        
        log_debug(f"클라이언트 연결됨: {client_id}")
        return client_id
    
    async def unregister_client(self, client_id: str):
        """클라이언트 연결 해제"""
        if client_id in self.connected_clients:
            del self.connected_clients[client_id]
            log_debug(f"클라이언트 연결 해제됨: {client_id}")
    
    async def send_message(self, client_id: str, message: Dict[str, Any]) -> bool:
        """
        특정 클라이언트에게 메시지 전송
        
        Args:
            client_id: 클라이언트 ID
            message: 전송할 메시지 (dict)
            
        Returns:
            전송 성공 여부
        """
        if client_id not in self.connected_clients:
            log_error(f"클라이언트를 찾을 수 없음: {client_id}")
            return False
        
        try:
            websocket = self.connected_clients[client_id]
            await websocket.send(json.dumps(message, ensure_ascii=False))
            log_debug(f"메시지 전송 완료: {client_id}")
            return True
        except Exception as e:
            log_error(f"메시지 전송 실패: {client_id} - {e}")
            await self.unregister_client(client_id)
            return False
    
    async def send_progress_update(self, client_id: str, message: str):
        """
        진행 상황 업데이트 전송 (Reference 코드의 즉시 처리 중 메시지와 유사)
        
        Args:
            client_id: 클라이언트 ID
            message: 진행 상황 메시지
        """
        progress_message = {
            "type": "progress",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, progress_message)
    
    async def send_result(self, client_id: str, result: Dict[str, Any]):
        """
        최종 결과 전송
        
        Args:
            client_id: 클라이언트 ID
            result: 결과 데이터
        """
        result_message = {
            "type": "result",
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, result_message)
    
    async def send_error(self, client_id: str, error_message: str):
        """
        에러 메시지 전송
        
        Args:
            client_id: 클라이언트 ID
            error_message: 에러 메시지
        """
        error_msg = {
            "type": "error",
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(client_id, error_msg)
    
    def create_question_key(self, client_id: str, message_id: str) -> str:
        """
        질문 고유 키 생성 (Reference 코드의 question_key와 유사)
        
        Args:
            client_id: 클라이언트 ID
            message_id: 메시지 ID
            
        Returns:
            질문 고유 키
        """
        return f"{client_id}:{message_id}"
    
    async def handle_message(self, websocket: websockets.WebSocketServerProtocol, client_id: str, raw_message: str):
        """
        수신된 메시지 처리
        
        Args:
            websocket: WebSocket 연결
            client_id: 클라이언트 ID
            raw_message: 원본 메시지
        """
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
            question_key = self.create_question_key(client_id, message_id)
            
            if question_key in self.processing_questions:
                log_debug(f"중복 질문 무시: {question_key}")
                return
            
            log_debug(f"새 질문 처리: {question_key}")
            log_debug(f"질문 내용: {question}")
            
            # 처리 중 목록에 추가
            self.processing_questions.add(question_key)
            
            # 즉시 처리 중 메시지 전송 (Reference 코드와 동일)
            await self.send_progress_update(client_id, "🔄 요청을 처리하고 있습니다. 잠시만 기다려주세요...")
            
            # 비동기 처리 시작 (Reference 코드의 threading.Thread와 유사)
            asyncio.create_task(self.process_question_async(client_id, question, question_key))
            
        except json.JSONDecodeError:
            await self.send_error(client_id, "잘못된 JSON 형식입니다")
        except Exception as e:
            log_error(f"메시지 처리 중 오류: {e}")
            await self.send_error(client_id, f"메시지 처리 중 오류가 발생했습니다: {str(e)}")
    
    async def process_question_async(self, client_id: str, question: str, question_key: str):
        """
        질문 비동기 처리 (LangGraph 에이전트 통합)
        
        Args:
            client_id: 클라이언트 ID
            question: 질문 내용
            question_key: 질문 고유 키
        """
        try:
            log_debug(f"질문 처리 시작: {question_key}")
            
            # LangGraph 에이전트 워크플로우 실행
            from langgraph_agent import process_question_workflow
            
            websocket = self.connected_clients.get(client_id)
            if not websocket:
                log_error(f"WebSocket 연결을 찾을 수 없음: {client_id}")
                return
            
            # 워크플로우 실행
            final_state = await process_question_workflow(
                question=question,
                question_key=question_key,
                client_id=client_id,
                websocket=websocket
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
    
    async def handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """
        클라이언트 연결 처리
        
        Args:
            websocket: WebSocket 연결
            path: 연결 경로
        """
        client_id = await self.register_client(websocket, path)
        
        try:
            # 연결 확인 메시지 전송
            welcome_message = {
                "type": "connected",
                "message": "AWS Zendesk Assistant에 연결되었습니다",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }
            await self.send_message(client_id, welcome_message)
            
            # 메시지 수신 대기
            async for message in websocket:
                await self.handle_message(websocket, client_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            log_debug(f"클라이언트 연결 종료: {client_id}")
        except Exception as e:
            log_error(f"클라이언트 처리 중 오류: {client_id} - {e}")
        finally:
            await self.unregister_client(client_id)
    
    async def start_server(self):
        """서버 시작"""
        log_info(f"WebSocket 서버 시작: {self.host}:{self.port}")
        
        # WebSocket 핸들러 래퍼 함수 (최신 websockets 라이브러리 호환)
        async def websocket_handler(websocket):
            await self.handle_client(websocket, "/")
        
        self.server = await websockets.serve(
            websocket_handler,
            self.host,
            self.port
        )
        
        log_info("WebSocket 서버가 시작되었습니다")
        log_info(f"연결 URL: ws://{self.host}:{self.port}")
        
        # 서버 실행 유지
        await self.server.wait_closed()
    
    async def stop_server(self):
        """서버 중지"""
        if self.server:
            log_info("WebSocket 서버 중지 중...")
            self.server.close()
            await self.server.wait_closed()
            log_info("WebSocket 서버가 중지되었습니다")
    
    def get_server_stats(self) -> Dict[str, Any]:
        """서버 통계 정보 반환"""
        return {
            "connected_clients": len(self.connected_clients),
            "processing_questions": len(self.processing_questions),
            "client_ids": list(self.connected_clients.keys())
        }