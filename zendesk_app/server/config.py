"""
Zendesk 앱 설정
"""
import os
from dotenv import load_dotenv

load_dotenv()

# FastAPI 설정
HOST = os.getenv('FASTAPI_HOST', '0.0.0.0')
PORT = int(os.getenv('FASTAPI_PORT', 8000))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# WebSocket 백엔드 설정
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'ws://localhost:8765/ws')

# 템플릿 설정
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

# 로깅 설정
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
