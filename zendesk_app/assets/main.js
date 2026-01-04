/**
 * AWS Zendesk Assistant - Zendesk 앱 로더
 * 역할: 티켓 정보 수집 + Python 서버 연결
 */

class ZendeskAssistantLoader {
  constructor() {
    this.client = null;
    this.serverUrl = null;
    this.ticketData = null;
  }

  async init() {
    try {
      console.log('[DEBUG] Zendesk Assistant 초기화 시작');
      
      // Zendesk 클라이언트 초기화
      this.client = ZAFClient.init();
      console.log('[DEBUG] ZAF 클라이언트 초기화 완료');
      
      // 서버 URL 결정 (우선순위)
      // 1. 메타데이터에서 가져오기
      // 2. 환경 변수 (window.ZENDESK_SERVER_URL)
      // 3. 현재 호스트 기반 (EC2 ALB 호환)
      // 4. 기본값
      
      let metadata;
      try {
        metadata = await this.client.metadata();
        console.log('[DEBUG] 메타데이터:', metadata);
        this.serverUrl = metadata.settings.serverUrl;
      } catch (metadataError) {
        console.warn('[WARN] 메타데이터 조회 실패:', metadataError);
      }
      
      // 메타데이터에서 못 가져왔으면 다른 방법 시도
      if (!this.serverUrl) {
        // 환경 변수 확인
        if (typeof window.ZENDESK_SERVER_URL !== 'undefined') {
          this.serverUrl = window.ZENDESK_SERVER_URL;
          console.log('[DEBUG] 환경 변수에서 서버 URL 가져옴:', this.serverUrl);
        } else {
          // 현재 호스트 기반으로 서버 URL 구성 (EC2 ALB 호환)
          const protocol = window.location.protocol;
          const host = window.location.host;
          this.serverUrl = `${protocol}//${host}`;
          console.log('[DEBUG] 현재 호스트 기반 서버 URL:', this.serverUrl);
        }
      }
      
      // 최후의 기본값
      if (!this.serverUrl) {
        this.serverUrl = 'http://localhost:8000';
        console.warn('[WARN] 기본값 사용:', this.serverUrl);
      }
      
      console.log('[DEBUG] 최종 서버 URL:', this.serverUrl);
      
      // 티켓 정보 수집
      await this.loadTicketData();
      
      // Python 서버로 리다이렉트
      this.redirectToServer();
      
    } catch (error) {
      console.error('[ERROR] 초기화 실패:', error);
      console.error('[ERROR] 스택:', error.stack);
      this.showError(error.message);
    }
  }

  async loadTicketData() {
    try {
      console.log('[DEBUG] 티켓 정보 수집 중...');
      
      const ticketData = await this.client.get([
        'ticket.id',
        'ticket.subject',
        'ticket.description',
        'ticket.status',
        'ticket.priority',
        'ticket.requester.name',
        'ticket.requester.email',
        'ticket.comments'
      ]);

      this.ticketData = {
        id: ticketData['ticket.id'],
        subject: ticketData['ticket.subject'],
        description: ticketData['ticket.description'],
        status: ticketData['ticket.status'],
        priority: ticketData['ticket.priority'],
        requesterName: ticketData['ticket.requester.name'],
        requesterEmail: ticketData['ticket.requester.email'],
        comments: ticketData['ticket.comments'] || []
      };

      console.log('[DEBUG] 티켓 정보 수집 완료:', this.ticketData.id);
      
    } catch (error) {
      console.error('[ERROR] 티켓 정보 수집 실패:', error);
      throw error;
    }
  }

  async redirectToServer() {
    try {
      // 1단계: 티켓 정보를 서버에 POST로 전송
      console.log('[DEBUG] 티켓 정보를 서버에 전송 중...');
      
      // HTTPS 사용 (젠데스크는 HTTPS만 허용)
      const apiUrl = this.serverUrl.replace(/^http:/, 'https:');
      
      const response = await fetch(`${apiUrl}/api/ticket`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(this.ticketData)
      });
      
      if (!response.ok) {
        throw new Error(`서버 응답 오류: ${response.status}`);
      }
      
      console.log('[DEBUG] 티켓 정보 전송 완료');
      
      // 2단계: iframe 로드 (URL은 간단하게)
      const iframeUrl = `${apiUrl}/`;
      
      console.log('[DEBUG] iframe 로드 시작:', iframeUrl);
      
      // iframe 생성 및 로드
      const iframe = document.createElement('iframe');
      iframe.id = 'aws-assistant-iframe';
      iframe.src = iframeUrl;
      iframe.style.width = '100%';
      iframe.style.height = '100%';
      iframe.style.border = 'none';
      iframe.style.margin = '0';
      iframe.style.padding = '0';
      
      // iframe 로드 이벤트 리스너
      iframe.onload = () => {
        console.log('[DEBUG] iframe 로드 완료');
      };
      
      iframe.onerror = (error) => {
        console.error('[ERROR] iframe 로드 실패:', error);
        this.showError('iframe 로드 실패: ' + error);
      };
      
      // 기존 콘텐츠 제거
      document.body.innerHTML = '';
      document.body.style.margin = '0';
      document.body.style.padding = '0';
      document.body.style.overflow = 'hidden';
      
      // iframe 추가
      document.body.appendChild(iframe);
      
      console.log('[DEBUG] iframe DOM에 추가 완료');
      
    } catch (error) {
      console.error('[ERROR] 서버 연결 실패:', error);
      console.error('[ERROR] 스택:', error.stack);
      this.showError('서버 연결 실패: ' + error.message);
    }
  }

  showError(message) {
    document.body.innerHTML = `
      <div style="
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        background: #f5f5f5;
      ">
        <div style="
          text-align: center;
          padding: 20px;
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        ">
          <h2 style="color: #d32f2f; margin-bottom: 10px;">오류 발생</h2>
          <p style="color: #666;">${message}</p>
          <p style="color: #999; font-size: 12px; margin-top: 10px;">
            관리자에게 문의하세요.
          </p>
        </div>
      </div>
    `;
  }
}

// 앱 초기화
document.addEventListener('DOMContentLoaded', () => {
  const loader = new ZendeskAssistantLoader();
  loader.init();
});
