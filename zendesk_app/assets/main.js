/**
 * AWS Zendesk Assistant - Zendesk 앱
 * 역할: UI 먼저 표시 → WebSocket 백그라운드 연결
 */

(function() {
  console.log('[DEBUG] main.js 로드됨');
  
  // ALB 도메인
  const ALB_DOMAIN = 'web-tool-lb-627934048.ap-northeast-2.elb.amazonaws.com';
  const wsUrl = `wss://${ALB_DOMAIN}:8001/ws`;
  
  let ws = null;
  let connectionStatus = 'disconnected';
  
  // ===== UI 렌더링 =====
  function renderUI() {
    const appDiv = document.getElementById('app');
    if (!appDiv) {
      console.error('[ERROR] #app 요소를 찾을 수 없습니다');
      return;
    }
    
    const html = `
      <div class="chatbot-container">
        <!-- Header -->
        <header class="chat-header">
          <div class="header-content">
            <div class="ai-avatar">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <div class="header-text">
              <h1>AWS Assistant</h1>
              <span class="status-indicator">
                <span class="status-dot" id="statusDot"></span>
                <span class="status-text" id="statusText">연결 중...</span>
              </span>
            </div>
          </div>
        </header>

        <!-- Status Banner -->
        <div class="status-banner" id="statusBanner">
          <div class="status-info">
            <span class="status-label">서버:</span>
            <span class="status-value" id="serverUrl">${ALB_DOMAIN}</span>
          </div>
          <div class="status-info">
            <span class="status-label">상태:</span>
            <span class="status-value" id="connectionState">연결 시도 중</span>
          </div>
        </div>

        <!-- Messages Container -->
        <main class="messages-container" id="messagesContainer">
          <div class="welcome-message">
            <div class="welcome-icon">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 15C21 15.5304 20.7893 16.0391 20.4142 16.4142C20.0391 16.7893 19.5304 17 19 17H7L3 21V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H19C19.5304 3 20.0391 3.21071 20.4142 3.58579C20.7893 3.96086 21 4.46957 21 5V15Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <h2>AWS Zendesk Assistant</h2>
            <p>AWS 분석 및 지원 도구</p>
            
            <div class="quick-actions">
              <div class="feature-item">
                <strong>기능:</strong>
                <ul>
                  <li>AWS 서비스 분석</li>
                  <li>보안 보고서</li>
                  <li>CloudTrail 조회</li>
                  <li>CloudWatch 모니터링</li>
                </ul>
              </div>
            </div>
          </div>
        </main>

        <!-- Input Area -->
        <footer class="input-area">
          <div class="input-wrapper">
            <textarea 
              id="messageInput" 
              placeholder="메시지를 입력하세요..."
              rows="1"
              maxlength="4000"
              disabled
            ></textarea>
            <button class="btn-send" id="sendButton" disabled>
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
          <div class="input-footer">
            <span class="char-count"><span id="charCount">0</span>/4000</span>
            <span class="powered-by">AWS Zendesk Assistant v2.0.3</span>
          </div>
        </footer>
      </div>

      <style>
        .chatbot-container {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: white;
        }

        .chat-header {
          padding: 16px;
          border-bottom: 1px solid #e0e0e0;
          background: white;
        }

        .header-content {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .ai-avatar {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: #232f3e;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          flex-shrink: 0;
        }

        .ai-avatar svg {
          width: 24px;
          height: 24px;
        }

        .header-text h1 {
          font-size: 16px;
          font-weight: 600;
          color: #232f3e;
          margin: 0;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #666;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #ff9900;
          animation: pulse 2s infinite;
        }

        .status-dot.connected {
          background: #28a745;
          animation: none;
        }

        .status-dot.error {
          background: #dc3545;
          animation: none;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .status-banner {
          padding: 12px 16px;
          background: #f5f5f5;
          border-bottom: 1px solid #e0e0e0;
          font-size: 12px;
          color: #666;
        }

        .status-info {
          display: flex;
          gap: 8px;
          margin-bottom: 4px;
        }

        .status-info:last-child {
          margin-bottom: 0;
        }

        .status-label {
          font-weight: 600;
          color: #333;
        }

        .status-value {
          font-family: monospace;
          word-break: break-all;
        }

        .messages-container {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
        }

        .welcome-message {
          text-align: center;
          max-width: 400px;
        }

        .welcome-icon {
          width: 64px;
          height: 64px;
          margin: 0 auto 16px;
          color: #232f3e;
          opacity: 0.3;
        }

        .welcome-icon svg {
          width: 100%;
          height: 100%;
        }

        .welcome-message h2 {
          font-size: 20px;
          color: #232f3e;
          margin-bottom: 8px;
        }

        .welcome-message p {
          font-size: 14px;
          color: #666;
          margin-bottom: 24px;
        }

        .quick-actions {
          text-align: left;
        }

        .feature-item {
          background: #f9f9f9;
          border: 1px solid #ddd;
          border-radius: 4px;
          padding: 12px;
          font-size: 13px;
        }

        .feature-item strong {
          display: block;
          margin-bottom: 8px;
          color: #232f3e;
        }

        .feature-item ul {
          list-style: none;
          padding: 0;
          margin: 0;
        }

        .feature-item li {
          padding: 4px 0;
          color: #666;
        }

        .feature-item li:before {
          content: "• ";
          margin-right: 6px;
        }

        .input-area {
          padding: 12px 16px;
          border-top: 1px solid #e0e0e0;
          background: white;
        }

        .input-wrapper {
          display: flex;
          gap: 8px;
          margin-bottom: 8px;
        }

        #messageInput {
          flex: 1;
          padding: 10px 12px;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-family: inherit;
          font-size: 14px;
          resize: none;
          max-height: 120px;
        }

        #messageInput:disabled {
          background: #f5f5f5;
          color: #999;
        }

        .btn-send {
          width: 36px;
          height: 36px;
          padding: 0;
          border: none;
          border-radius: 4px;
          background: #232f3e;
          color: white;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .btn-send:disabled {
          background: #ccc;
          cursor: not-allowed;
        }

        .btn-send svg {
          width: 20px;
          height: 20px;
        }

        .input-footer {
          display: flex;
          justify-content: space-between;
          font-size: 11px;
          color: #999;
        }

        .char-count {
          font-family: monospace;
        }
      </style>
    `;
    
    appDiv.innerHTML = html;
    console.log('[DEBUG] UI 렌더링 완료');
  }
  
  // ===== 상태 업데이트 =====
  function updateStatus(status, message) {
    connectionStatus = status;
    
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const connectionState = document.getElementById('connectionState');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    
    if (!statusDot || !statusText || !connectionState) {
      console.warn('[WARN] 상태 업데이트 요소를 찾을 수 없습니다');
      return;
    }
    
    const statusConfig = {
      'connected': { color: '#28a745', text: '연결됨', dotClass: 'connected' },
      'connecting': { color: '#ff9900', text: '연결 중...', dotClass: '' },
      'disconnected': { color: '#dc3545', text: '연결 끊김', dotClass: 'error' },
      'error': { color: '#dc3545', text: '오류', dotClass: 'error' }
    };
    
    const config = statusConfig[status] || statusConfig['disconnected'];
    statusDot.className = `status-dot ${config.dotClass}`;
    statusText.textContent = config.text;
    connectionState.textContent = message;
    
    // 연결 상태에 따라 입력 활성화/비활성화
    if (messageInput && sendButton) {
      const isConnected = status === 'connected';
      messageInput.disabled = !isConnected;
      sendButton.disabled = !isConnected;
    }
    
    console.log(`[STATUS] ${status}: ${message}`);
  }
  
  // ===== WebSocket 연결 =====
  function connectWebSocket() {
    updateStatus('connecting', '서버에 연결 중...');
    
    try {
      ws = new WebSocket(wsUrl);
      
      ws.onopen = function() {
        console.log('[DEBUG] WebSocket 연결 성공');
        updateStatus('connected', '서버 연결됨');
      };
      
      ws.onmessage = function(event) {
        console.log('[DEBUG] 메시지 수신:', event.data);
      };
      
      ws.onerror = function(error) {
        console.error('[ERROR] WebSocket 오류:', error);
        updateStatus('error', 'WebSocket 오류 발생');
      };
      
      ws.onclose = function() {
        console.log('[DEBUG] WebSocket 연결 종료');
        updateStatus('disconnected', '서버 연결 끊김');
        
        // 5초 후 재연결 시도
        setTimeout(connectWebSocket, 5000);
      };
      
    } catch (error) {
      console.error('[ERROR] WebSocket 생성 실패:', error);
      updateStatus('error', error.message);
      
      // 5초 후 재시도
      setTimeout(connectWebSocket, 5000);
    }
  }
  
  // ===== 초기화 =====
  console.log('[DEBUG] UI 렌더링 시작');
  renderUI();
  
  console.log('[DEBUG] WebSocket 연결 시작:', wsUrl);
  connectWebSocket();
  
  // 전역 객체 노출 (디버깅용)
  window.assistantWS = ws;
  window.assistantStatus = function() {
    return {
      status: connectionStatus,
      ws: ws,
      url: wsUrl
    };
  };
  
  console.log('[DEBUG] main.js 초기화 완료');
})();
