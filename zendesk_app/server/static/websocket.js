/**
 * WebSocket 통신 모듈
 * 역할: 기존 WebSocket 백엔드와 통신
 */

class WebSocketClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 3000;
    this.messageHandlers = [];
    this.connectionHandlers = [];
    this.errorHandlers = [];
  }

  /**
   * WebSocket 연결
   */
  connect() {
    return new Promise((resolve, reject) => {
      try {
        console.log('[DEBUG] WebSocket 연결 시도:', this.url);
        
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log('[DEBUG] WebSocket 연결 성공');
          this.reconnectAttempts = 0;
          
          // 연결 핸들러 실행
          this.connectionHandlers.forEach(handler => handler(true));
          resolve();
        };
        
        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('[DEBUG] WebSocket 메시지 수신:', data.type);
            
            // 메시지 핸들러 실행
            this.messageHandlers.forEach(handler => handler(data));
          } catch (error) {
            console.error('[ERROR] 메시지 파싱 실패:', error);
          }
        };
        
        this.ws.onerror = (error) => {
          console.error('[ERROR] WebSocket 오류:', error);
          
          // 에러 핸들러 실행
          this.errorHandlers.forEach(handler => handler(error));
          reject(error);
        };
        
        this.ws.onclose = () => {
          console.log('[DEBUG] WebSocket 연결 종료');
          this.connectionHandlers.forEach(handler => handler(false));
          
          // 자동 재연결
          this.attemptReconnect();
        };
        
      } catch (error) {
        console.error('[ERROR] WebSocket 연결 실패:', error);
        reject(error);
      }
    });
  }

  /**
   * 메시지 전송
   */
  send(message) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('[ERROR] WebSocket 연결 안 됨');
      return false;
    }
    
    try {
      const data = typeof message === 'string' ? message : JSON.stringify(message);
      this.ws.send(data);
      console.log('[DEBUG] WebSocket 메시지 전송:', message);
      return true;
    } catch (error) {
      console.error('[ERROR] 메시지 전송 실패:', error);
      return false;
    }
  }

  /**
   * 메시지 핸들러 등록
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
  }

  /**
   * 연결 상태 핸들러 등록
   */
  onConnectionChange(handler) {
    this.connectionHandlers.push(handler);
  }

  /**
   * 에러 핸들러 등록
   */
  onError(handler) {
    this.errorHandlers.push(handler);
  }

  /**
   * 자동 재연결
   */
  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[ERROR] 최대 재연결 시도 횟수 초과');
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;
    
    console.log(`[DEBUG] ${delay}ms 후 재연결 시도 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(() => {
      this.connect().catch(error => {
        console.error('[ERROR] 재연결 실패:', error);
      });
    }, delay);
  }

  /**
   * 연결 종료
   */
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * 연결 상태 확인
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

// 전역 WebSocket 클라이언트
let wsClient = null;

/**
 * WebSocket 클라이언트 초기화
 */
function initWebSocket(url) {
  return new Promise((resolve, reject) => {
    // FastAPI 프록시 엔드포인트로 연결 (ALB 도메인 사용)
    // 클라이언트 → FastAPI (/ws) → 백엔드 (localhost:8001)
    const proxyUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsProxyUrl = `${proxyUrl}//${host}/ws`;
    
    console.log('[DEBUG] WebSocket 프록시 URL:', wsProxyUrl);
    
    wsClient = new WebSocketClient(wsProxyUrl);
    
    wsClient.onConnectionChange((connected) => {
      console.log(`[DEBUG] WebSocket 연결 상태: ${connected ? '연결됨' : '연결 끊김'}`);
      
      // UI 업데이트
      const statusDot = document.querySelector('.status-dot');
      const statusText = document.querySelector('.status-text');
      
      if (statusDot && statusText) {
        if (connected) {
          statusDot.style.background = '#31a24c';
          statusText.textContent = '준비됨';
        } else {
          statusDot.style.background = '#ff9800';
          statusText.textContent = '연결 중...';
        }
      }
    });
    
    wsClient.onError((error) => {
      console.error('[ERROR] WebSocket 에러:', error);
      showToast('연결 오류가 발생했습니다', 'error');
    });
    
    wsClient.onMessage((data) => {
      handleWebSocketMessage(data);
    });
    
    wsClient.connect()
      .then(() => resolve(wsClient))
      .catch(error => reject(error));
  });
}

/**
 * WebSocket 메시지 처리
 */
function handleWebSocketMessage(data) {
  const type = data.type;
  
  switch (type) {
    case 'connected':
      console.log('[DEBUG] 서버 연결 확인:', data.message);
      break;
      
    case 'progress':
      console.log('[DEBUG] 진행 상황:', data.message);
      addMessage(data.message, 'progress');
      break;
      
    case 'streaming_start':
      console.log('[DEBUG] 스트리밍 시작');
      addMessage('', 'ai-streaming');
      break;
      
    case 'streaming_chunk':
      console.log('[DEBUG] 스트리밍 청크:', data.chunk_index);
      appendToLastMessage(data.chunk);
      break;
      
    case 'streaming_complete':
      console.log('[DEBUG] 스트리밍 완료');
      hideLoadingOverlay();
      break;
      
    case 'result':
      console.log('[DEBUG] 결과 수신');
      addMessage(data.data.answer, 'ai');
      hideLoadingOverlay();
      break;
      
    case 'error':
      console.error('[ERROR] 서버 오류:', data.message);
      addMessage(`❌ 오류: ${data.message}`, 'error');
      hideLoadingOverlay();
      showToast(data.message, 'error');
      break;
      
    case 'pong':
      console.log('[DEBUG] Pong 수신');
      break;
      
    default:
      console.log('[DEBUG] 알 수 없는 메시지 타입:', type);
  }
}

/**
 * 질문 전송
 */
function sendQuestion(question) {
  if (!wsClient || !wsClient.isConnected()) {
    showToast('서버에 연결되지 않았습니다', 'error');
    return false;
  }
  
  const message = {
    type: 'question',
    message: question,
    session_id: generateSessionId()
  };
  
  return wsClient.send(JSON.stringify(message));
}

/**
 * 세션 ID 생성
 */
function generateSessionId() {
  return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
