#!/usr/bin/env python3
"""
Saltware AWS Assistant - Production Server Runner
Gunicorn + eventlet을 사용한 프로덕션 WebSocket 서버
"""

from websocket_server import app, socketio

if __name__ == '__main__':
    print("🚀 Saltware AWS Assistant WebSocket Server 시작 (프로덕션 모드)")
    print("📡 WebSocket 서버: http://0.0.0.0:3001")
    print("🔗 Zendesk 앱에서 연결 가능")
    
    # Gunicorn + eventlet으로 실행
    socketio.run(app, host='0.0.0.0', port=3001, debug=False)