/**
 * AWS Zendesk Assistant - Zendesk 앱
 * 역할: WebSocket으로 Python 서버에 직접 연결
 */

(function() {
  const ALB_HOST = 'q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com';
  const WS_PORT = 8765;
  
  // WebSocket URL 생성 (wss 사용 - Zendesk는 HTTPS)
  const wsUrl = `wss://${ALB_HOST}:${WS_PORT}`;
  
  console.log('[DEBUG] WebSocket URL:', wsUrl);
  
  // WebSocket 연결
  let ws = null;
  
  function connectWebSocket() {
    try {
      ws = new WebSocket(wsUrl);
      
      ws.onopen = function() {
        console.log('[DEBUG] WebSocket 연결 성공');
        // 연결 성공 메시지 표시
        document.body.innerHTML = '<div style="padding: 20px; font-family: Arial;"><h2>AWS Zendesk Assistant</h2><p>연결됨</p></div>';
      };
      
      ws.onmessage = function(event) {
        console.log('[DEBUG] 메시지 수신:', event.data);
      };
      
      ws.onerror = function(error) {
        console.error('[ERROR] WebSocket 오류:', error);
        document.body.innerHTML = '<div style="padding: 20px; color: red;"><h2>연결 오류</h2><p>서버에 연결할 수 없습니다.</p></div>';
      };
      
      ws.onclose = function() {
        console.log('[DEBUG] WebSocket 연결 종료');
        // 3초 후 재연결 시도
        setTimeout(connectWebSocket, 3000);
      };
      
    } catch (error) {
      console.error('[ERROR] WebSocket 생성 실패:', error);
      document.body.innerHTML = '<div style="padding: 20px; color: red;"><h2>오류</h2><p>' + error.message + '</p></div>';
    }
  }
  
  // 초기 연결
  connectWebSocket();
  
  // 전역 WebSocket 객체 노출 (디버깅용)
  window.assistantWS = ws;
})();
