/**
 * Saltware AWS Assistant - Zendesk App
 * WebSocket 기반 실시간 AWS 통합 관리 도구
 */

class SaltwareAWSAssistant {
    constructor() {
        this.client = null; // Zendesk Apps Framework 클라이언트
        this.socket = null; // Socket.IO 클라이언트
        this.globalSocket = null; // 글로벌 Socket.IO 클라이언트
        this.isConnected = false;
        this.currentProgress = 0;
        this.serverUrl = null; // 서버 URL 저장
        
        // DOM 요소들
        this.elements = {
            connectionStatus: document.getElementById('connectionStatus'),
            statusDot: document.querySelector('.status-dot'),
            statusText: document.querySelector('.status-text'),
            chatMessages: document.getElementById('chatMessages'),
            messageInput: document.getElementById('messageInput'),
            sendButton: document.getElementById('sendButton'),
            progressContainer: document.getElementById('progressContainer'),
            progressFill: document.getElementById('progressFill'),
            progressPercentage: document.getElementById('progressPercentage'),
            progressMessage: document.getElementById('progressMessage'),
            resultsContainer: document.getElementById('resultsContainer'),
            resultsContent: document.getElementById('resultsContent'),
            closeResults: document.getElementById('closeResults')
        };
        
        this.init();
    }
    
    /**
     * 앱 초기화
     */
    async init() {
        try {
            console.log('🚀 Saltware AWS Assistant 초기화 시작');
            
            // Zendesk Apps Framework 초기화 (실패해도 계속 진행)
            try {
                await this.initZendeskClient();
            } catch (error) {
                console.warn('⚠️ Zendesk 클라이언트 초기화 실패 (로컬 테스트 모드):', error);
            }
            
            // 이벤트 리스너 설정 (WebSocket 연결 전에)
            this.setupEventListeners();
            
            // 즉시 로컬 테스트 모드로 활성화 (사용자 경험 개선)
            this.enableInputForLocalTest();
            this.updateConnectionStatus(false, '로컬 테스트 모드');
            
            // WebSocket 연결 시도 (백그라운드에서)
            this.initWebSocket().catch(error => {
                console.warn('⚠️ WebSocket 초기화 실패 (서버 없음):', error);
            });
            
            // 2초 후에도 연결이 안 되면 로컬 테스트 모드 유지
            setTimeout(() => {
                if (!this.isConnected) {
                    console.log('🧪 로컬 테스트 모드 유지');
                    this.updateConnectionStatus(false, '로컬 테스트 모드');
                }
            }, 2000);
            
            console.log('✅ 초기화 완료 (로컬 테스트 모드)');
            
            // 브라우저 알림 권한 요청
            if (window.Notification && Notification.permission === 'default') {
                Notification.requestPermission();
            }
        } catch (error) {
            console.error('❌ 초기화 실패:', error);
            this.showError('앱 초기화에 실패했습니다. 페이지를 새로고침해주세요.');
        }
    }
    
    /**
     * Zendesk Apps Framework 클라이언트 초기화
     */
    async initZendeskClient() {
        return new Promise((resolve, reject) => {
            if (typeof ZAFClient !== 'undefined') {
                this.client = ZAFClient.init();
                
                this.client.on('app.registered', (appData) => {
                    console.log('📱 Zendesk 앱 등록 완료:', appData);
                    resolve();
                });
                
                // 앱 크기 조정
                this.client.invoke('resize', { width: '100%', height: '600px' });
            } else {
                console.warn('⚠️ Zendesk Apps Framework를 사용할 수 없습니다. 로컬 테스트 모드로 실행합니다.');
                resolve();
            }
        });
    }
    
    /**
     * WebSocket 연결 초기화
     */
    async initWebSocket() {
        try {
            // WebSocket 서버 URL 가져오기 (Zendesk 설정 또는 기본값)
            this.serverUrl = 'http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/zendesk';
            
            if (this.client) {
                try {
                    const settings = await this.client.metadata();
                    this.serverUrl = settings.settings.websocket_server_url || this.serverUrl;
                } catch (error) {
                    console.log('📝 Zendesk 설정을 가져올 수 없습니다. 기본 URL을 사용합니다.');
                }
            }
            
            console.log('🔌 WebSocket 서버 연결 시도:', this.serverUrl);
            
            // Socket.IO 클라이언트 생성
            this.socket = io(this.serverUrl, {
                path: '/zendesk/socket.io',
                transports: ['polling', 'websocket'],  // polling을 우선으로 (더 안정적)
                timeout: 20000,  // 타임아웃 증가
                reconnection: true,
                reconnectionAttempts: 10,  // 재연결 시도 증가
                reconnectionDelay: 1000,
                forceNew: true  // 새 연결 강제
            });
            
            // WebSocket 이벤트 리스너 설정
            this.setupWebSocketListeners();
            
        } catch (error) {
            console.error('❌ WebSocket 초기화 실패:', error);
            this.updateConnectionStatus(false, 'WebSocket 연결 실패');
        }
    }
    
    /**
     * WebSocket 이벤트 리스너 설정
     */
    setupWebSocketListeners() {
        // 연결 성공
        this.socket.on('connect', () => {
            console.log('✅ WebSocket 연결 성공');
            this.isConnected = true;
            this.updateConnectionStatus(true, '서버 연결됨');
            this.enableInput();
            this.addMessage('🔗 WebSocket 서버에 연결되었습니다. 이제 실제 AWS 관리 기능이 가능합니다!', 'bot');
        });
        
        // 연결 해제
        this.socket.on('disconnect', (reason) => {
            console.log('❌ WebSocket 연결 해제:', reason);
            this.isConnected = false;
            this.updateConnectionStatus(false, '연결 해제됨');
            this.disableInput();
        });
        
        // 연결 오류
        this.socket.on('connect_error', (error) => {
            console.error('❌ WebSocket 연결 오류:', error);
            this.updateConnectionStatus(false, '연결 오류');
        });
        
        // 진행률 업데이트
        this.socket.on('progress', (data) => {
            console.log('📊 진행률 업데이트 수신:', data);
            console.log('📊 현재 연결 상태:', this.socket.connected);
            console.log('📊 현재 진행률 요소 존재:', !!this.elements.progressContainer);
            console.log('📊 현재 진행률 요소 표시 상태:', this.elements.progressContainer?.style.display);
            
            // 모든 progress 이벤트에 대해 강제 알림
            console.log('🚨 ALERT: 진행률', data.progress + '% 수신됨!');
            
            // 브라우저 알림으로 강제 확인 (모든 progress에 대해)
            if (window.Notification && Notification.permission === 'granted') {
                new Notification('진행률 업데이트', { body: data.progress + '% - ' + data.message });
            }
            
            // 브라우저 제목도 변경해서 확실히 확인
            document.title = `AWS Assistant - ${data.progress}%`;
            
            try {
                this.updateProgress(data.progress, data.message);
                console.log('📊 ✅ 진행률 업데이트 완료:', data.progress + '%');
            } catch (error) {
                console.error('📊 ❌ 진행률 업데이트 실패:', error);
            }
        });
        
        // 최종 결과
        this.socket.on('result', (data) => {
            console.log('📋 결과 수신:', data);
            console.log('🚨 ALERT: 최종 결과 수신됨!');
            
            // 브라우저 알림으로 강제 확인
            if (window.Notification && Notification.permission === 'granted') {
                new Notification('분석 완료', { body: '결과가 도착했습니다!' });
            }
            
            this.showResult(data);
            this.hideProgress();
        });
        
        // 에러 메시지
        this.socket.on('error', (data) => {
            console.error('❌ 서버 에러:', data);
            this.showError(data.message || '서버에서 오류가 발생했습니다.');
            this.hideProgress();
        });
        
        // 모든 이벤트 디버깅 (강화)
        this.socket.onAny((eventName, ...args) => {
            console.log('🔍 WebSocket 이벤트 수신:', eventName, args);
            
            // 특별히 progress 이벤트 강조
            if (eventName === 'progress') {
                console.log('🎯 PROGRESS 이벤트 감지!', args[0]);
                // 브라우저 콘솔에 큰 메시지로 표시
                console.log('%c🚨 PROGRESS: ' + args[0]?.progress + '%', 'color: red; font-size: 20px; font-weight: bold;');
            }
        });
        
        // 글로벌 연결은 CORS 문제로 제거하고 메인 연결에 집중
    }
    
    /**
     * DOM 이벤트 리스너 설정
     */
    setupEventListeners() {
        // 메시지 전송 버튼
        this.elements.sendButton.addEventListener('click', () => {
            this.sendMessage();
        });
        
        // Enter 키로 메시지 전송
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // 결과 창 닫기
        this.elements.closeResults.addEventListener('click', () => {
            this.hideResults();
        });
        
        // 결과 창 배경 클릭으로 닫기
        this.elements.resultsContainer.addEventListener('click', (e) => {
            if (e.target === this.elements.resultsContainer) {
                this.hideResults();
            }
        });
    }
    
    /**
     * 메시지 전송
     */
    sendMessage() {
        const message = this.elements.messageInput.value.trim();
        
        if (!message) {
            return;
        }
        
        // 사용자 메시지 표시
        this.addMessage(message, 'user');
        
        // 입력 필드 초기화
        this.elements.messageInput.value = '';
        
        if (!this.isConnected) {
            // 로컬 테스트 모드: Mock 응답
            this.addMessage('🧪 로컬 테스트 모드입니다. WebSocket 서버가 연결되면 실제 AWS 관리 기능이 가능합니다.', 'bot');
            
            // Mock 진행률 시뮬레이션
            this.showProgress('테스트 진행률 시뮬레이션...');
            let progress = 0;
            const interval = setInterval(() => {
                progress += 20;
                this.updateProgress(progress, `테스트 단계 ${progress/20}/5`);
                
                if (progress >= 100) {
                    clearInterval(interval);
                    setTimeout(() => {
                        this.hideProgress();
                        this.addMessage('✅ 테스트 완료! 실제 환경에서는 AWS 관리 결과가 표시됩니다.', 'bot');
                    }, 500);
                }
            }, 800);
            
            return;
        }
        
        // 진행률 표시 시작
        this.showProgress('요청을 처리하고 있습니다...');
        
        // WebSocket으로 메시지 전송
        this.socket.emit('aws_query', {
            query: message,
            timestamp: new Date().toISOString(),
            user_id: 'zendesk_user', // 실제로는 Zendesk 사용자 ID
            ticket_id: 'test_ticket' // 실제로는 현재 티켓 ID
        });
        
        console.log('📤 메시지 전송:', message);
    }
    
    /**
     * 채팅 메시지 추가
     */
    addMessage(content, type = 'bot') {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ' + type + '-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (typeof content === 'string') {
            contentDiv.innerHTML = this.formatMessage(content);
        } else {
            contentDiv.appendChild(content);
        }
        
        messageDiv.appendChild(contentDiv);
        this.elements.chatMessages.appendChild(messageDiv);
        
        // 스크롤을 맨 아래로
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }
    
    /**
     * 메시지 포맷팅 (마크다운 스타일 지원)
     */
    formatMessage(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }
    
    /**
     * 연결 상태 업데이트
     */
    updateConnectionStatus(isConnected, statusText) {
        this.elements.statusDot.className = `status-dot ${isConnected ? 'online' : 'offline'}`;
        this.elements.statusText.textContent = statusText;
    }
    
    /**
     * 입력 활성화
     */
    enableInput() {
        this.elements.messageInput.disabled = false;
        this.elements.sendButton.disabled = false;
        this.elements.messageInput.placeholder = 'AWS 관련 질문을 입력하세요... (예: 계정 123456789012 월간 보고서 생성해줘)';
    }
    
    /**
     * 입력 비활성화
     */
    disableInput() {
        this.elements.messageInput.disabled = true;
        this.elements.sendButton.disabled = true;
        this.elements.messageInput.placeholder = 'WebSocket 서버에 연결 중...';
    }
    
    /**
     * 로컬 테스트용 입력 활성화
     */
    enableInputForLocalTest() {
        this.elements.messageInput.disabled = false;
        this.elements.sendButton.disabled = false;
        this.elements.messageInput.placeholder = '로컬 테스트 모드 - 메시지를 입력해보세요';
    }
    
    /**
     * 진행률 표시
     */
    showProgress(message = '처리 중...') {
        this.elements.progressContainer.style.display = 'block';
        this.elements.progressMessage.textContent = message;
        this.updateProgress(0, message);
    }
    
    /**
     * 진행률 업데이트
     */
    updateProgress(progress, message) {
        console.log('🔄 updateProgress 호출됨:', { progress, message, currentProgress: this.currentProgress });
        
        this.currentProgress = Math.max(0, Math.min(100, progress));
        
        if (this.elements.progressFill) {
            this.elements.progressFill.style.width = this.currentProgress + '%';
            console.log('🔄 진행률 바 업데이트:', this.currentProgress + '%');
        } else {
            console.error('🔄 ❌ progressFill 요소를 찾을 수 없음');
        }
        
        if (this.elements.progressPercentage) {
            this.elements.progressPercentage.textContent = Math.round(this.currentProgress) + '%';
            console.log('🔄 진행률 텍스트 업데이트:', Math.round(this.currentProgress) + '%');
        } else {
            console.error('🔄 ❌ progressPercentage 요소를 찾을 수 없음');
        }
        
        if (message && this.elements.progressMessage) {
            this.elements.progressMessage.textContent = message;
            console.log('🔄 진행률 메시지 업데이트:', message);
        } else if (message) {
            console.error('🔄 ❌ progressMessage 요소를 찾을 수 없음');
        }
        
        console.log('🔄 ✅ updateProgress 완료');
    }
    
    /**
     * 진행률 숨기기
     */
    hideProgress() {
        this.elements.progressContainer.style.display = 'none';
        this.currentProgress = 0;
    }
    
    /**
     * 결과 표시
     */
    showResult(data) {
        // 봇 메시지로 결과 요약 추가
        if (data.summary) {
            this.addMessage(data.summary, 'bot');
        }
        
        // 상세 결과가 있으면 모달로 표시
        if (data.reports && data.reports.length > 0) {
            this.showDetailedResults(data);
        }
    }
    
    /**
     * 상세 결과 모달 표시
     */
    showDetailedResults(data) {
        let content = '<div style="padding: 20px;">';
        
        if (data.reports) {
            content += '<h3>📊 생성된 보고서</h3><ul>';
            data.reports.forEach(report => {
                content += `<li><a href="${report.url}" target="_blank">${report.name}</a></li>`;
            });
            content += '</ul>';
        }
        
        if (data.data) {
            content += '<h3>📋 분석 데이터</h3>';
            content += '<pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; overflow-x: auto;">';
            content += JSON.stringify(data.data, null, 2);
            content += '</pre>';
        }
        
        content += '</div>';
        
        this.elements.resultsContent.innerHTML = content;
        this.elements.resultsContainer.style.display = 'flex';
    }
    
    /**
     * 결과 모달 숨기기
     */
    hideResults() {
        this.elements.resultsContainer.style.display = 'none';
    }
    
    /**
     * 에러 메시지 표시
     */
    showError(message) {
        this.addMessage(`❌ 오류: ${message}`, 'bot');
    }
}

// 앱 시작
document.addEventListener('DOMContentLoaded', () => {
    console.log('🎯 Saltware AWS Assistant 로드 완료');
    new SaltwareAWSAssistant();
});