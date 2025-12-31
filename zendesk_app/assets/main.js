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
      
      // 앱 설정 가져오기
      const metadata = await this.client.metadata();
      this.serverUrl = metadata.settings.serverUrl || 'http://localhost:8000';
      
      console.log('[DEBUG] 서버 URL:', this.serverUrl);
      
      // 티켓 정보 수집
      await this.loadTicketData();
      
      // Python 서버로 리다이렉트
      this.redirectToServer();
      
    } catch (error) {
      console.error('[ERROR] 초기화 실패:', error);
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

  redirectToServer() {
    try {
      // 티켓 정보를 URL 파라미터로 인코딩
      const ticketParam = encodeURIComponent(JSON.stringify(this.ticketData));
      const redirectUrl = `${this.serverUrl}/?ticket=${ticketParam}`;
      
      console.log('[DEBUG] Python 서버로 리다이렉트:', redirectUrl);
      
      // iframe 콘텐츠 로드
      window.location.href = redirectUrl;
      
    } catch (error) {
      console.error('[ERROR] 리다이렉트 실패:', error);
      this.showError('서버 연결 실패');
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
