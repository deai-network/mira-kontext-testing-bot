/**
 * Generic Chat Widget
 * 
 * Usage:
 * <script src="chat_widget.js"></script>
 * <script>
 *   window.initChatWidget({
 *     webhookUrl: 'https://your-api-endpoint.com/chat',
 *     primaryColor: '#007BFF',
 *     secondaryColor: '#F8F9FA',
 *     botName: 'SupportBot',
 *     botAvatar: '🤖',
 *     welcomeMessage: 'Hello! How can I help you today?',
 *     position: 'bottom-right'
 *   });
 * </script>
 */

(function() {
    'use strict';

    class GenericChatWidget {
        constructor(config) {
            this.config = {
                webhookUrl: config.webhookUrl || '',
                position: config.position || 'bottom-right',
                primaryColor: config.primaryColor || '#3B82F6',
                secondaryColor: config.secondaryColor || '#F3F4F6',
                textColor: config.textColor || '#1F2937',
                botName: config.botName || 'Assistant',
                botAvatar: config.botAvatar || 'A',
                welcomeMessage: config.welcomeMessage || 'Hello! How can I help you today?',
                borderRadius: '16px',
                shadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
            };

            this.isOpen = false;
            this.messages = [];
            this.sessionId = this.generateSessionId();
            
            this.init();
        }

        generateSessionId() {
            return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
        }

        init() {
            this.injectStyles();
            this.createWidget();
            this.attachEventListeners();
            this.showWelcomeMessage();
        }

        injectStyles() {
            const styles = `
                .generic-chat-widget * {
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }

                .generic-chat-widget {
                    position: fixed;
                    ${this.config.position.includes('right') ? 'right: 20px;' : 'left: 20px;'}
                    ${this.config.position.includes('bottom') ? 'bottom: 20px;' : 'top: 20px;'}
                    z-index: 999999;
                    font-family: ${this.config.fontFamily};
                    font-size: 14px;
                    line-height: 1.5;
                }

                .chat-toggle-btn {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: ${this.config.primaryColor};
                    border: none;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: ${this.config.shadow};
                    transition: transform 0.3s ease;
                }

                .chat-toggle-btn:hover {
                    transform: scale(1.05);
                }

                .chat-icon {
                    width: 24px;
                    height: 24px;
                    fill: white;
                }

                .chat-container {
                    width: 380px;
                    height: 600px;
                    background: white;
                    border-radius: ${this.config.borderRadius};
                    box-shadow: ${this.config.shadow};
                    position: absolute;
                    ${this.config.position.includes('right') ? 'right: 0;' : 'left: 0;'}
                    bottom: 80px;
                    transform: translateY(20px) scale(0.95);
                    opacity: 0;
                    visibility: hidden;
                    transition: all 0.3s ease;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }

                .chat-container.open {
                    transform: translateY(0) scale(1);
                    opacity: 1;
                    visibility: visible;
                }

                .chat-header {
                    background: ${this.config.primaryColor};
                    color: white;
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }

                .chat-avatar {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: rgba(255, 255, 255, 0.2);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 16px;
                }

                .chat-messages {
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                    background: ${this.config.secondaryColor};
                }

                .message {
                    margin-bottom: 16px;
                    display: flex;
                }

                .message.bot {
                    justify-content: flex-start;
                }

                .message.user {
                    justify-content: flex-end;
                }

                .message-content {
                    padding: 12px 16px;
                    border-radius: 18px;
                    max-width: 80%;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                }

                .message.bot .message-content {
                    background: white;
                    color: ${this.config.textColor};
                    border-bottom-left-radius: 4px;
                }

                .message.user .message-content {
                    background: ${this.config.primaryColor};
                    color: white;
                    border-bottom-right-radius: 4px;
                }

                .chat-input-area {
                    padding: 16px;
                    background: white;
                    border-top: 1px solid #E5E7EB;
                    display: flex;
                    gap: 10px;
                }

                .chat-input {
                    flex: 1;
                    border: 1px solid #E5E7EB;
                    border-radius: 20px;
                    padding: 10px 16px;
                    outline: none;
                    font-family: inherit;
                }

                .chat-input:focus {
                    border-color: ${this.config.primaryColor};
                }

                .send-btn {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: ${this.config.primaryColor};
                    border: none;
                    color: white;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .typing-indicator {
                    display: none;
                    padding: 12px 16px;
                    background: white;
                    border-radius: 18px;
                    border-bottom-left-radius: 4px;
                    margin-bottom: 16px;
                    width: fit-content;
                }

                .typing-indicator.active {
                    display: flex;
                    gap: 4px;
                }

                .dot {
                    width: 6px;
                    height: 6px;
                    background: #9CA3AF;
                    border-radius: 50%;
                    animation: bounce 1.4s infinite ease-in-out both;
                }

                .dot:nth-child(1) { animation-delay: -0.32s; }
                .dot:nth-child(2) { animation-delay: -0.16s; }

                @keyframes bounce {
                    0%, 80%, 100% { transform: scale(0); }
                    40% { transform: scale(1); }
                }
            `;

            const styleSheet = document.createElement('style');
            styleSheet.textContent = styles;
            document.head.appendChild(styleSheet);
        }

        createWidget() {
            this.widget = document.createElement('div');
            this.widget.className = 'generic-chat-widget';
            this.widget.innerHTML = `
                <div class="chat-container">
                    <div class="chat-header">
                        <div class="chat-avatar">${this.config.botAvatar}</div>
                        <div>
                            <h3 style="font-size: 16px;">${this.config.botName}</h3>
                        </div>
                    </div>
                    <div class="chat-messages" id="chat-messages">
                        <div class="typing-indicator" id="typing-indicator">
                            <div class="dot"></div>
                            <div class="dot"></div>
                            <div class="dot"></div>
                        </div>
                    </div>
                    <div class="chat-input-area">
                        <input type="text" class="chat-input" id="chat-input" placeholder="Type a message...">
                        <button class="send-btn" id="send-btn">➤</button>
                    </div>
                </div>
                <button class="chat-toggle-btn" id="chat-toggle">
                    <svg class="chat-icon" viewBox="0 0 24 24">
                        <path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                    </svg>
                </button>
            `;

            document.body.appendChild(this.widget);
            
            this.container = this.widget.querySelector('.chat-container');
            this.messagesArea = this.widget.querySelector('#chat-messages');
            this.input = this.widget.querySelector('#chat-input');
            this.sendBtn = this.widget.querySelector('#send-btn');
            this.toggleBtn = this.widget.querySelector('#chat-toggle');
            this.typingIndicator = this.widget.querySelector('#typing-indicator');
        }

        attachEventListeners() {
            this.toggleBtn.addEventListener('click', () => this.toggleChat());
            this.sendBtn.addEventListener('click', () => this.handleSend());
            this.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.handleSend();
            });
        }

        toggleChat() {
            this.isOpen = !this.isOpen;
            this.container.classList.toggle('open', this.isOpen);
            if (this.isOpen) {
                setTimeout(() => this.input.focus(), 300);
            }
        }

        showWelcomeMessage() {
            this.addMessage(this.config.welcomeMessage, 'bot');
        }

        addMessage(text, sender) {
            const msgDiv = document.createElement('div');
            msgDiv.className = \`message \${sender}\`;
            msgDiv.innerHTML = \`<div class="message-content">\${this.escapeHtml(text)}</div>\`;
            
            this.messagesArea.insertBefore(msgDiv, this.typingIndicator);
            this.scrollToBottom();
        }

        setTyping(isTyping) {
            if (isTyping) {
                this.typingIndicator.classList.add('active');
                this.scrollToBottom();
            } else {
                this.typingIndicator.classList.remove('active');
            }
        }

        scrollToBottom() {
            this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
        }

        escapeHtml(unsafe) {
            return unsafe
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;")
                 .replace(/\\n/g, "<br>");
        }

        async handleSend() {
            const text = this.input.value.trim();
            if (!text) return;

            this.input.value = '';
            this.addMessage(text, 'user');
            this.setTyping(true);

            try {
                const response = await fetch(this.config.webhookUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sessionId: this.sessionId,
                        message: text
                    })
                });

                if (!response.ok) throw new Error('Network response was not ok');
                
                const data = await response.json();
                
                // Handle n8n array response or standard JSON
                let replyText = "I'm sorry, I couldn't process that.";
                if (Array.isArray(data) && data[0] && data[0].output) {
                    replyText = data[0].output;
                } else if (data.reply) {
                    replyText = data.reply;
                } else if (data.output) {
                    replyText = data.output;
                }

                this.setTyping(false);
                this.addMessage(replyText, 'bot');

            } catch (error) {
                console.error('Chat Error:', error);
                this.setTyping(false);
                this.addMessage('Sorry, I am having trouble connecting right now. Please try again later.', 'bot');
            }
        }
    }

    // Expose to global scope
    window.initChatWidget = function(config) {
        return new GenericChatWidget(config);
    };
})();
