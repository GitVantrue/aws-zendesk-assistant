/**
 * AWS Zendesk Assistant - Zendesk 앱 로더
 * 역할: Python 서버 UI를 iframe으로 로드만 함 (최소 코드)
 */

(function() {
  // HTTP URL 사용 (ALB를 통해 EC2의 8765 포트로 포워딩)
  const serverUrl = "http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com";
  
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
