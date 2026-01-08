/**
 * ZenBot - 대시보드 UI 로직
 */

class ZenBotDashboard {
  constructor() {
    this.messages = [];
    this.isProcessing = false;
    this.ticketData = window.ticketData;
    this.websocketUrl = window.websocketUrl;
    this.isChatOpen = false;
    
    this.init();
  }

  async init() {
    try {
      console.log('[DEBUG] ZenBot 초기화 시작');
      this.cacheElements();
      this.setupEventListeners();
      await initWebSocket(this.websocketUrl);
      console.log('[DEBUG] ZenBot 초기화 완료');
    } catch (error) {
      console.error('[ERROR] 초기화 실패:', error);
      this.showToast('초기화 실패: ' + error.message, 'error');
    }
  }

  cacheElements() {
    this.dashboardView = document.getElementById('dashboardView');
    this.chatView = document.getElementById('chatView');
    this.messagesContainer = document.getElementById('messagesContainer');
    this.messageInput = document.getElementById('messageInput');
    this.sendButton = document.getElementById('sendButton');
    this.charCount = document.getElementById('charCount');
    this.toastContainer = document.getElementById('toastContainer');
    this.ticketModal = document.getElementById('ticketModal');
  }

  setupEventListeners() {
    // 채팅 열기/닫기
    document.getElementById('openChatBtn')?.addEventListener('click', () => this.openChat());
    document.getElementById('closeChatBtn')?.addEventListener('click', () => this.closeChat());
    document.getElementById('chatBtn')?.addEventListener('click', () => this.openChat());

    // 카드 클릭 이벤트
    document.getElementById('screenerCard')?.addEventListener('click', () => this.openScreenerModal());
    document.getElementById('reportCard')?.addEventListener('click', () => this.openReportModal());
    document.getElementById('cloudtrailCard')?.addEventListener('click', () => this.openCloudtrailModal());

    // 모달 닫기
    document.getElementById('screenerModalClose')?.addEventListener('click', () => this.closeScreenerModal());
    document.getElementById('reportModalClose')?.addEventListener('click', () => this.closeReportModal());
    document.getElementById('cloudtrailModalClose')?.addEventListener('click', () => this.closeCloudtrailModal());

    // 모달 배경 클릭으로 닫기
    document.getElementById('screenerModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'screenerModal') this.closeScreenerModal();
    });
    document.getElementById('reportModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'reportModal') this.closeReportModal();
    });
    document.getElementById('cloudtrailModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'cloudtrailModal') this.closeCloudtrailModal();
    });

    // 티켓 정보
    document.getElementById('ticketInfoBtn')?.addEventListener('click', () => this.openTicketModal());
    document.getElementById('ticketModalClose')?.addEventListener('click', () => this.closeTicketModal());
    if (this.ticketModal) {
      this.ticketModal.addEventListener('click', (e) => {
        if (e.target === this.ticketModal) this.closeTicketModal();
      });
    }

    // 채팅 입력
    this.sendButton.addEventListener('click', () => this.handleSend());
    
    // input 이벤트: 문자 입력 시 (한글 입력 중에도 발생)
    this.messageInput.addEventListener('input', () => {
      this.updateCharCount();
      this.updateSendButtonState();
    });
    
    // compositionend 이벤트: 한글/일본어 입력 완료 후
    this.messageInput.addEventListener('compositionend', () => {
      this.autoResizeInput();
    });
    
    // change 이벤트: 값이 변경되었을 때
    this.messageInput.addEventListener('change', () => {
      this.autoResizeInput();
    });
    
    this.messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    // 모달 액션 버튼
    document.getElementById('runScreenerBtn')?.addEventListener('click', () => this.runScreener());
    document.getElementById('generateReportBtn')?.addEventListener('click', () => this.generateReport());
    document.getElementById('queryCloudtrailBtn')?.addEventListener('click', () => this.queryCloudtrail());
  }

  openChat() {
    this.isChatOpen = true;
    this.dashboardView.classList.remove('active');
    this.chatView.classList.add('active');
    this.messageInput.focus();
  }

  closeChat() {
    this.isChatOpen = false;
    this.chatView.classList.remove('active');
    this.dashboardView.classList.add('active');
  }

  openScreenerModal() {
    document.getElementById('screenerModal')?.classList.add('active');
  }

  closeScreenerModal() {
    document.getElementById('screenerModal')?.classList.remove('active');
    document.getElementById('screenerAccountId').value = '';
  }

  openReportModal() {
    document.getElementById('reportModal')?.classList.add('active');
  }

  closeReportModal() {
    document.getElementById('reportModal')?.classList.remove('active');
    document.getElementById('reportAccountId').value = '';
    document.getElementById('reportMonth').value = '';
  }

  openCloudtrailModal() {
    document.getElementById('cloudtrailModal')?.classList.add('active');
  }

  closeCloudtrailModal() {
    document.getElementById('cloudtrailModal')?.classList.remove('active');
    document.getElementById('cloudtrailAccountId').value = '';
    document.getElementById('eventType').value = '';
  }

  openTicketModal() {
    if (this.ticketModal) {
      this.ticketModal.classList.add('active');
    }
  }

  closeTicketModal() {
    if (this.ticketModal) {
      this.ticketModal.classList.remove('active');
    }
  }

  runScreener() {
    const accountId = document.getElementById('screenerAccountId').value.trim();
    if (!accountId) {
      this.showToast('계정 ID를 입력하세요', 'warning');
      return;
    }
    
    this.closeScreenerModal();
    this.openChat();
    this.messageInput.value = `Service Screener를 실행해주세요. 계정 ID: ${accountId}`;
    this.updateCharCount();
    this.autoResizeInput();
    this.updateSendButtonState();
    setTimeout(() => this.handleSend(), 100);
  }

  generateReport() {
    const accountId = document.getElementById('reportAccountId').value.trim();
    const month = document.getElementById('reportMonth').value;
    
    if (!accountId) {
      this.showToast('계정 ID를 입력하세요', 'warning');
      return;
    }
    
    this.closeReportModal();
    this.openChat();
    let message = `월간 보안 보고서를 생성해주세요. 계정 ID: ${accountId}`;
    if (month) message += `, 기간: ${month}`;
    
    this.messageInput.value = message;
    this.updateCharCount();
    this.autoResizeInput();
    this.updateSendButtonState();
    setTimeout(() => this.handleSend(), 100);
  }

  queryCloudtrail() {
    const accountId = document.getElementById('cloudtrailAccountId').value.trim();
    const eventType = document.getElementById('eventType').value;
    
    if (!accountId) {
      this.showToast('계정 ID를 입력하세요', 'warning');
      return;
    }
    
    this.closeCloudtrailModal();
    this.openChat();
    let message = `CloudTrail 로그를 조회해주세요. 계정 ID: ${accountId}`;
    if (eventType) message += `, 이벤트 유형: ${eventType}`;
    
    this.messageInput.value = message;
    this.updateCharCount();
    this.autoResizeInput();
    this.updateSendButtonState();
    setTimeout(() => this.handleSend(), 100);
  }

  updateCharCount() {
    const count = this.messageInput.value.length;
    this.charCount.textContent = count;
  }

  autoResizeInput() {
    // 높이를 초기값으로 리셋
    this.messageInput.style.height = 'auto';
    
    // scrollHeight를 기반으로 새 높이 계산
    const newHeight = Math.min(this.messageInput.scrollHeight, 120);
    this.messageInput.style.height = newHeight + 'px';
  }

  updateSendButtonState() {
    const hasContent = this.messageInput.value.trim().length > 0;
    this.sendButton.disabled = !hasContent || this.isProcessing;
  }

  async handleSend() {
    const message = this.messageInput.value.trim();
    if (!message || this.isProcessing) {
      console.log('[DEBUG] handleSend 무시: message=', message, 'isProcessing=', this.isProcessing);
      return;
    }
    
    console.log('[DEBUG] handleSend 시작:', message);
    
    // 메시지 추가
    this.addMessage(message, 'user');
    this.hideWelcomeMessage();
    
    // 입력 필드 초기화
    this.messageInput.value = '';
    this.messageInput.style.height = 'auto';
    this.messageInput.style.height = '40px';
    this.updateCharCount();
    this.updateSendButtonState();
    
    // 처리 상태 설정
    this.isProcessing = true;
    this.updateSendButtonState();
    
    console.log('[DEBUG] sendQuestion 호출 전');
    const success = sendQuestion(message);
    console.log('[DEBUG] sendQuestion 결과:', success);
    
    if (!success) {
      console.error('[ERROR] 메시지 전송 실패');
      this.isProcessing = false;
      this.updateSendButtonState();
      this.showToast('메시지 전송 실패', 'error');
    }
  }

  addMessage(content, type) {
    const messageId = Date.now();
    const message = {
      id: messageId,
      content: content,
      type: type,
      timestamp: new Date()
    };
    
    this.messages.push(message);
    
    const messageElement = this.createMessageElement(message);
    this.messagesContainer.appendChild(messageElement);
    
    this.scrollToBottom();
  }

  createMessageElement(message) {
    const div = document.createElement('div');
    div.className = `message ${message.type}`;
    div.dataset.id = message.id;
    
    const avatarIcon = message.type === 'user'
      ? '<svg viewBox="0 0 24 24" fill="none"><path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    
    const timeString = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    let bubbleContent = this.formatMessage(message.content);
    
    if (message.type === 'progress') {
      // 진행 메시지: 로딩 스피너 + 텍스트
      bubbleContent = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 16px; height: 16px; border: 2px solid rgba(99, 102, 241, 0.2); border-top-color: #6366f1; border-radius: 50%; animation: spin 1s linear infinite;"></div>
          <span style="color: #6366f1;">${message.content}</span>
        </div>
      `;
    } else if (message.type === 'error') {
      bubbleContent = `<span style="color: #ef4444;">${message.content}</span>`;
    }
    
    div.innerHTML = `
      <div class="message-avatar">${avatarIcon}</div>
      <div class="message-content">
        <div class="message-bubble">${bubbleContent}</div>
        <span class="message-time">${timeString}</span>
      </div>
    `;
    
    return div;
  }

  formatMessage(content) {
    return content
      // URL을 링크로 변환 (http/https로 시작하는 URL)
      .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #818cf8; text-decoration: underline; cursor: pointer;">$1</a>')
      // 마크다운 포맷
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  hideWelcomeMessage() {
    const welcome = this.messagesContainer.querySelector('.welcome-message');
    if (welcome) {
      welcome.style.display = 'none';
    }
  }

  scrollToBottom() {
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
      success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12C21.9988 14.1564 21.3005 16.2547 20.0093 17.9818C18.7182 19.709 16.9033 20.9725 14.8354 21.5839C12.7674 22.1953 10.5573 22.1219 8.53447 21.3746C6.51168 20.6273 4.78465 19.2461 3.61096 17.4371C2.43727 15.628 1.87979 13.4881 2.02168 11.3363C2.16356 9.18455 2.99721 7.13631 4.39828 5.49706C5.79935 3.85781 7.69279 2.71537 9.79619 2.24013C11.8996 1.7649 14.1003 1.98232 16.07 2.85999" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 4L12 14.01L9 11.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M15 9L9 15M9 9L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      warning: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 9V13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="17" r="1" fill="currentColor"/></svg>',
      info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M12 16V12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="8" r="1" fill="currentColor"/></svg>'
    };
    
    toast.innerHTML = `${icons[type] || icons.info}<span class="toast-message">${message}</span>`;
    this.toastContainer.appendChild(toast);
    
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100px)';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// 전역 함수
function addMessage(content, type) {
  if (window.zenBotDashboard) {
    window.zenBotDashboard.addMessage(content, type);
  }
}

function appendToLastMessage(content) {
  if (window.zenBotDashboard && window.zenBotDashboard.messages.length > 0) {
    const lastMessage = window.zenBotDashboard.messages[window.zenBotDashboard.messages.length - 1];
    lastMessage.content += content;
    
    const lastElement = document.querySelector(`[data-id="${lastMessage.id}"] .message-bubble`);
    if (lastElement) {
      lastElement.innerHTML = window.zenBotDashboard.formatMessage(lastMessage.content);
    }
  }
}

function showToast(message, type) {
  if (window.zenBotDashboard) {
    window.zenBotDashboard.showToast(message, type);
  }
}

// 초기화
document.addEventListener('DOMContentLoaded', () => {
  window.zenBotDashboard = new ZenBotDashboard();
});
