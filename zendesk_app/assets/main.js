/**
 * AWS Zendesk Assistant - Zendesk 앱
 * 역할: UI 먼저 표시 → WebSocket 백그라운드 연결
 */

(function() {
  console.log('[DEBUG] main.js 로드됨');
  
  // ALB 도메인
  const ALB_DOMAIN = 'q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com';
  const wsUrl = `wss://${ALB_DOMAIN}/ws`;
  
  let ws = null;
  let connectionStatus = 'disconnected';
  
  // ===== UI 렌더링 =====
  function renderUI() {
    const html = `
      <div style="
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        max-width: 600px;
        margin: 0 auto;
        padding: 20px;
        background: white;
        min-height: 100vh;
      ">
        <div style="text-align: center; margin-bottom: 30px;">
          <h1 style="color: #232f3e; margin-bottom: 10px;">AWS Zendesk Assistant</h1>
          <p style="color: #666; font-size: 14px;">AWS 분석 및 지원 도구</p>
        </div>
        
        <div style="
          background: #f5f5f5;
          border-radius: 8px;
          padding: 15px;
          margin-bottom: 20px;
        ">
          <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <div id="statusIndicator" style="
              width: 12px;
              height: 12px;
              border-radius: 50%;
              background: #ff9900;
              margin-right: 10px;
            "></div>
            <span id="statusText" style="font-size: 14px; color: #666;">연결 중...</span>
          </div>
          <div style="font-size: 12px; color: #999;">
            <div>서버: <span id="serverUrl" style="font-family: monospace;">${ALB_DOMAIN}</span></div>
            <div>상태: <span id="connectionState" style="font-family: monospace;">연결 시도 중</span></div>
          </div>
        </div>
        
        <div style="
          background: #fff3cd;
          border-left: 4px solid #ffc107;
          padding: 15px;
          border-radius: 4px;
          margin-bottom: 20px;
        ">
          <p style="font-size: 14px; color: #856404; margin: 0;">
            <strong>준비 중:</strong> 현재 UI 개발 중입니다. 곧 채팅 기능이 추가됩니다.
          </p>
        </div>
        
        <div style="
          background: #f9f9f9;
          border: 1px solid #ddd;
          border-radius: 4px;
          padding: 15px;
        ">
          <h3 style="font-size: 14px; color: #232f3e; margin-bottom: 10px;">기능</h3>
          <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #666;">
            <li>AWS 서비스 분석</li>
            <li>보안 보고서</li>
            <li>CloudTrail 조회</li>
            <li>CloudWatch 모니터링</li>
          </ul>
        </div>
        
        <div style="
          margin-top: 30px;
          padding-top: 20px;
          border-top: 1px solid #eee;
          font-size: 12px;
          color: #999;
          text-align: center;
        ">
          <p>AWS Zendesk Assistant v2.0.3</p>
        </div>
      </div>
    `;
    
    document.body.innerHTML = html;
  }
  
  // ===== 상태 업데이트 =====
  function updateStatus(status, message) {
    connectionStatus = status;
    
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    const connectionState = document.getElementById('connectionState');
    
    if (!statusIndicator || !statusText || !connectionState) return;
    
    const statusConfig = {
      'connected': { color: '#28a745', text: '연결됨' },
      'connecting': { color: '#ff9900', text: '연결 중...' },
      'disconnected': { color: '#dc3545', text: '연결 끊김' },
      'error': { color: '#dc3545', text: '오류' }
    };
    
    const config = statusConfig[status] || statusConfig['disconnected'];
    statusIndicator.style.background = config.color;
    statusText.textContent = config.text;
    connectionState.textContent = message;
    
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
