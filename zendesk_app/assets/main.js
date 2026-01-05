/**
 * AWS Zendesk Assistant - Zendesk 앱 로더
 * 역할: Python 서버 UI를 iframe으로 로드만 함 (최소 코드)
 */

(function() {
  // 현재 페이지의 프로토콜 사용 (HTTPS 또는 HTTP)
  const protocol = window.location.protocol; // https: 또는 http:
  const serverUrl = protocol + "//q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com";
  
  console.log('[DEBUG] Server URL:', serverUrl);
  
  // iframe 생성 및 로드
  const iframe = document.createElement('iframe');
  iframe.id = 'aws-assistant-iframe';
  iframe.src = serverUrl + '/';
  iframe.style.width = '100%';
  iframe.style.height = '100%';
  iframe.style.border = 'none';
  iframe.style.margin = '0';
  iframe.style.padding = '0';
  
  // 기존 콘텐츠 제거
  document.body.innerHTML = '';
  document.body.style.margin = '0';
  document.body.style.padding = '0';
  document.body.style.overflow = 'hidden';
  
  // iframe 추가
  document.body.appendChild(iframe);
})();
