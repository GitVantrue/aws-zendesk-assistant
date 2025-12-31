/**
 * AWS AgentCore Chatbot - Zendesk App
 * Main application module
 */

// ============================================
// AWS Signature V4 Implementation
// ============================================

class AWSSignatureV4 {
  constructor(credentials, region, service) {
    this.accessKeyId = credentials.accessKeyId;
    this.secretAccessKey = credentials.secretAccessKey;
    this.region = region;
    this.service = service;
  }

  async sign(request) {
    const date = new Date();
    const dateString = this.formatDate(date);
    const dateTimeString = this.formatDateTime(date);

    const canonicalRequest = await this.createCanonicalRequest(request, dateTimeString);
    const stringToSign = this.createStringToSign(dateString, dateTimeString, canonicalRequest);
    const signature = await this.calculateSignature(dateString, stringToSign);

    const authorizationHeader = this.buildAuthorizationHeader(dateString, signature, request.headers);

    return {
      ...request,
      headers: {
        ...request.headers,
        'X-Amz-Date': dateTimeString,
        'Authorization': authorizationHeader
      }
    };
  }

  formatDate(date) {
    return date.toISOString().slice(0, 10).replace(/-/g, '');
  }

  formatDateTime(date) {
    return date.toISOString().replace(/[:-]|\.\d{3}/g, '');
  }

  async createCanonicalRequest(request, dateTimeString) {
    const method = request.method || 'POST';
    const uri = request.uri || '/';
    const queryString = request.queryString || '';
    
    const signedHeaders = Object.keys(request.headers)
      .map(h => h.toLowerCase())
      .sort()
      .join(';');

    const canonicalHeaders = Object.entries(request.headers)
      .map(([key, value]) => `${key.toLowerCase()}:${value.trim()}`)
      .sort()
      .join('\n') + '\n';

    const bodyHash = await this.hash(request.body || '');

    return [
      method,
      uri,
      queryString,
      canonicalHeaders,
      signedHeaders,
      bodyHash
    ].join('\n');
  }

  createStringToSign(dateString, dateTimeString, canonicalRequest) {
    const credentialScope = `${dateString}/${this.region}/${this.service}/aws4_request`;
    return [
      'AWS4-HMAC-SHA256',
      dateTimeString,
      credentialScope,
      this.hashSync(canonicalRequest)
    ].join('\n');
  }

  async calculateSignature(dateString, stringToSign) {
    const kDate = await this.hmac(`AWS4${this.secretAccessKey}`, dateString);
    const kRegion = await this.hmac(kDate, this.region);
    const kService = await this.hmac(kRegion, this.service);
    const kSigning = await this.hmac(kService, 'aws4_request');
    const signature = await this.hmac(kSigning, stringToSign, true);
    return signature;
  }

  buildAuthorizationHeader(dateString, signature, headers) {
    const signedHeaders = Object.keys(headers)
      .map(h => h.toLowerCase())
      .sort()
      .join(';');

    const credentialScope = `${dateString}/${this.region}/${this.service}/aws4_request`;

    return `AWS4-HMAC-SHA256 Credential=${this.accessKeyId}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;
  }

  async hash(message) {
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(hashBuffer))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  }

  hashSync(message) {
    // Synchronous hash using web crypto
    return this.hash(message);
  }

  async hmac(key, message, hex = false) {
    const encoder = new TextEncoder();
    const keyData = typeof key === 'string' ? encoder.encode(key) : key;
    const messageData = encoder.encode(message);

    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      keyData,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );

    const signature = await crypto.subtle.sign('HMAC', cryptoKey, messageData);

    if (hex) {
      return Array.from(new Uint8Array(signature))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
    }

    return new Uint8Array(signature);
  }
}

// ============================================
// AWS AgentCore Service
// ============================================

class AgentCoreService {
  constructor(config) {
    this.region = config.region;
    this.agentId = config.agentId;
    this.agentAliasId = config.agentAliasId;
    this.signer = new AWSSignatureV4(
      {
        accessKeyId: config.accessKeyId,
        secretAccessKey: config.secretAccessKey
      },
      config.region,
      'bedrock'
    );
    this.sessionId = this.generateSessionId();
  }

  generateSessionId() {
    return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  resetSession() {
    this.sessionId = this.generateSessionId();
  }

  async invokeAgent(inputText, ticketContext = null) {
    const endpoint = `https://bedrock-agent-runtime.${this.region}.amazonaws.com`;
    const path = `/agents/${this.agentId}/agentAliases/${this.agentAliasId}/sessions/${this.sessionId}/text`;

    // Build prompt with ticket context
    let fullPrompt = inputText;
    if (ticketContext) {
      fullPrompt = this.buildContextualPrompt(inputText, ticketContext);
    }

    const body = JSON.stringify({
      inputText: fullPrompt,
      enableTrace: false
    });

    const request = {
      method: 'POST',
      uri: path,
      headers: {
        'Host': `bedrock-agent-runtime.${this.region}.amazonaws.com`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: body
    };

    try {
      const signedRequest = await this.signer.sign(request);

      const response = await fetch(`${endpoint}${path}`, {
        method: 'POST',
        headers: signedRequest.headers,
        body: body
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`AgentCore API Error: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      return this.parseResponse(data);
    } catch (error) {
      console.error('AgentCore invocation failed:', error);
      throw error;
    }
  }

  buildContextualPrompt(userInput, ticketContext) {
    const contextParts = [];

    if (ticketContext.subject) {
      contextParts.push(`Ticket Subject: ${ticketContext.subject}`);
    }
    if (ticketContext.description) {
      contextParts.push(`Ticket Description: ${ticketContext.description}`);
    }
    if (ticketContext.requesterName) {
      contextParts.push(`Customer Name: ${ticketContext.requesterName}`);
    }
    if (ticketContext.status) {
      contextParts.push(`Ticket Status: ${ticketContext.status}`);
    }
    if (ticketContext.priority) {
      contextParts.push(`Priority: ${ticketContext.priority}`);
    }
    if (ticketContext.comments && ticketContext.comments.length > 0) {
      const recentComments = ticketContext.comments.slice(-3);
      contextParts.push(`Recent Comments:\n${recentComments.map(c => `- ${c.author}: ${c.body}`).join('\n')}`);
    }

    const contextString = contextParts.length > 0 
      ? `[Zendesk Ticket Context]\n${contextParts.join('\n')}\n\n[User Query]\n`
      : '';

    return `${contextString}${userInput}`;
  }

  parseResponse(data) {
    // Handle different response formats from AgentCore
    if (data.completion) {
      return data.completion;
    }
    if (data.output && data.output.text) {
      return data.output.text;
    }
    if (typeof data === 'string') {
      return data;
    }
    return JSON.stringify(data);
  }
}

// ============================================
// Zendesk App Client
// ============================================

class ZendeskChatbotApp {
  constructor() {
    this.client = null;
    this.agentService = null;
    this.ticketContext = null;
    this.messages = [];
    this.isProcessing = false;

    // DOM Elements
    this.messagesContainer = null;
    this.messageInput = null;
    this.sendButton = null;
    this.charCount = null;
    this.ticketSubject = null;
    this.loadingOverlay = null;
    this.toastContainer = null;

    this.init();
  }

  async init() {
    try {
      // Initialize Zendesk client
      this.client = ZAFClient.init();
      
      // Cache DOM elements
      this.cacheElements();
      
      // Show loading
      this.showLoading(true);

      // Get app settings and initialize AgentCore service
      const settings = await this.getSettings();
      this.agentService = new AgentCoreService({
        region: settings.awsRegion,
        accessKeyId: settings.awsAccessKeyId,
        secretAccessKey: settings.awsSecretAccessKey,
        agentId: settings.agentId,
        agentAliasId: settings.agentAliasId
      });

      // Get ticket context
      await this.loadTicketContext();

      // Setup event listeners
      this.setupEventListeners();

      // Resize the app frame
      await this.client.invoke('resize', { width: '100%', height: '500px' });

      // Hide loading
      this.showLoading(false);

      console.log('AWS AgentCore Chatbot initialized successfully');
    } catch (error) {
      console.error('Failed to initialize chatbot:', error);
      this.showLoading(false);
      this.showToast('Failed to initialize chatbot. Please refresh.', 'error');
    }
  }

  cacheElements() {
    this.messagesContainer = document.getElementById('messagesContainer');
    this.messageInput = document.getElementById('messageInput');
    this.sendButton = document.getElementById('sendButton');
    this.charCount = document.getElementById('charCount');
    this.ticketSubject = document.getElementById('ticketSubject');
    this.loadingOverlay = document.getElementById('loadingOverlay');
    this.toastContainer = document.getElementById('toastContainer');
  }

  async getSettings() {
    const metadata = await this.client.metadata();
    return metadata.settings;
  }

  async loadTicketContext() {
    try {
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

      this.ticketContext = {
        id: ticketData['ticket.id'],
        subject: ticketData['ticket.subject'],
        description: ticketData['ticket.description'],
        status: ticketData['ticket.status'],
        priority: ticketData['ticket.priority'],
        requesterName: ticketData['ticket.requester.name'],
        requesterEmail: ticketData['ticket.requester.email'],
        comments: ticketData['ticket.comments'] || []
      };

      // Update UI
      if (this.ticketSubject && this.ticketContext.subject) {
        this.ticketSubject.textContent = this.ticketContext.subject;
      }
    } catch (error) {
      console.error('Failed to load ticket context:', error);
      this.ticketContext = null;
    }
  }

  setupEventListeners() {
    // Send button click
    this.sendButton.addEventListener('click', () => this.handleSend());

    // Input events
    this.messageInput.addEventListener('input', () => {
      this.updateCharCount();
      this.autoResizeInput();
      this.updateSendButtonState();
    });

    // Enter to send (Shift+Enter for new line)
    this.messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    // Clear chat button
    document.getElementById('clearChat').addEventListener('click', () => {
      this.clearChat();
    });

    // Quick action buttons
    document.querySelectorAll('.quick-action-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = e.currentTarget.dataset.action;
        this.handleQuickAction(action);
      });
    });
  }

  updateCharCount() {
    const count = this.messageInput.value.length;
    this.charCount.textContent = count;
  }

  autoResizeInput() {
    this.messageInput.style.height = 'auto';
    this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
  }

  updateSendButtonState() {
    const hasContent = this.messageInput.value.trim().length > 0;
    this.sendButton.disabled = !hasContent || this.isProcessing;
  }

  async handleSend() {
    const message = this.messageInput.value.trim();
    if (!message || this.isProcessing) return;

    // Clear input
    this.messageInput.value = '';
    this.updateCharCount();
    this.autoResizeInput();
    this.updateSendButtonState();

    // Add user message
    this.addMessage(message, 'user');

    // Hide welcome message if visible
    this.hideWelcomeMessage();

    // Send to AgentCore
    await this.sendToAgent(message);
  }

  async handleQuickAction(action) {
    if (this.isProcessing) return;

    let prompt = '';
    switch (action) {
      case 'summarize':
        prompt = 'Please summarize this ticket concisely, highlighting the main issue and any important details.';
        break;
      case 'suggest':
        prompt = 'Please suggest a professional and helpful response to this customer ticket.';
        break;
      case 'analyze':
        prompt = 'Please analyze the sentiment of this ticket and provide insights about the customer\'s emotional state and urgency level.';
        break;
      default:
        return;
    }

    // Add user message
    this.addMessage(prompt, 'user');
    this.hideWelcomeMessage();

    // Send to AgentCore
    await this.sendToAgent(prompt);
  }

  async sendToAgent(message) {
    this.isProcessing = true;
    this.updateSendButtonState();

    // Show typing indicator
    const typingIndicator = this.showTypingIndicator();

    try {
      const response = await this.agentService.invokeAgent(message, this.ticketContext);
      
      // Remove typing indicator
      typingIndicator.remove();

      // Add AI response
      this.addMessage(response, 'ai');
    } catch (error) {
      console.error('Failed to get response:', error);
      
      // Remove typing indicator
      typingIndicator.remove();

      // Show error message
      this.addMessage('Sorry, I encountered an error processing your request. Please try again.', 'ai');
      this.showToast('Failed to get response from AI', 'error');
    } finally {
      this.isProcessing = false;
      this.updateSendButtonState();
    }
  }

  addMessage(content, type) {
    const messageId = Date.now();
    const message = { id: messageId, content, type, timestamp: new Date() };
    this.messages.push(message);

    const messageElement = this.createMessageElement(message);
    this.messagesContainer.appendChild(messageElement);

    // Scroll to bottom
    this.scrollToBottom();
  }

  createMessageElement(message) {
    const div = document.createElement('div');
    div.className = `message ${message.type}`;
    div.dataset.id = message.id;

    const avatarIcon = message.type === 'ai' 
      ? '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none"><path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    const timeString = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    div.innerHTML = `
      <div class="message-avatar">${avatarIcon}</div>
      <div class="message-content">
        <div class="message-bubble">${this.formatMessage(message.content)}</div>
        <span class="message-time">${timeString}</span>
        ${message.type === 'ai' ? `
          <div class="message-actions">
            <button class="action-btn" onclick="app.copyMessage('${message.id}')">
              <svg viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" stroke-width="2"/><path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" stroke="currentColor" stroke-width="2"/></svg>
              Copy
            </button>
            <button class="action-btn" onclick="app.insertIntoTicket('${message.id}')">
              <svg viewBox="0 0 24 24" fill="none"><path d="M11 4H4C2.89543 4 2 4.89543 2 6V20C2 21.1046 2.89543 22 4 22H18C19.1046 22 20 21.1046 20 20V13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              Insert
            </button>
          </div>
        ` : ''}
      </div>
    `;

    return div;
  }

  formatMessage(content) {
    // Basic markdown-like formatting
    return content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  showTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'message ai typing';
    div.innerHTML = `
      <div class="message-avatar">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
      <div class="message-content">
        <div class="message-bubble">
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
    `;
    this.messagesContainer.appendChild(div);
    this.scrollToBottom();
    return div;
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

  clearChat() {
    // Keep only the welcome message
    const welcome = this.messagesContainer.querySelector('.welcome-message');
    this.messagesContainer.innerHTML = '';
    if (welcome) {
      welcome.style.display = '';
      this.messagesContainer.appendChild(welcome);
    }
    this.messages = [];
    
    // Reset session
    if (this.agentService) {
      this.agentService.resetSession();
    }

    this.showToast('Conversation cleared', 'success');
  }

  async copyMessage(messageId) {
    const message = this.messages.find(m => m.id === parseInt(messageId));
    if (message) {
      try {
        await navigator.clipboard.writeText(message.content);
        this.showToast('Copied to clipboard', 'success');
      } catch (error) {
        console.error('Failed to copy:', error);
        this.showToast('Failed to copy', 'error');
      }
    }
  }

  async insertIntoTicket(messageId) {
    const message = this.messages.find(m => m.id === parseInt(messageId));
    if (message && this.client) {
      try {
        await this.client.set('comment.text', message.content);
        this.showToast('Inserted into ticket reply', 'success');
      } catch (error) {
        console.error('Failed to insert:', error);
        this.showToast('Failed to insert into ticket', 'error');
      }
    }
  }

  showLoading(show) {
    if (this.loadingOverlay) {
      this.loadingOverlay.classList.toggle('active', show);
    }
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'error' 
      ? '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M15 9L9 15M9 9L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
      : '<svg class="toast-icon" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12C21.9988 14.1564 21.3005 16.2547 20.0093 17.9818C18.7182 19.709 16.9033 20.9725 14.8354 21.5839C12.7674 22.1953 10.5573 22.1219 8.53447 21.3746C6.51168 20.6273 4.78465 19.2461 3.61096 17.4371C2.43727 15.628 1.87979 13.4881 2.02168 11.3363C2.16356 9.18455 2.99721 7.13631 4.39828 5.49706C5.79935 3.85781 7.69279 2.71537 9.79619 2.24013C11.8996 1.7649 14.1003 1.98232 16.07 2.85999" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 4L12 14.01L9 11.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    toast.innerHTML = `${icon}<span class="toast-message">${message}</span>`;
    this.toastContainer.appendChild(toast);

    // Auto remove after 3 seconds
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(20px)';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

// ============================================
// Initialize App
// ============================================

let app;
document.addEventListener('DOMContentLoaded', () => {
  app = new ZendeskChatbotApp();
});

// Export for global access (needed for onclick handlers)
window.app = app;

