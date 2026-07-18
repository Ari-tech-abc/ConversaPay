/**
 * ConversaPay AI Chat Widget
 * Embeddable chat widget for external websites
 * 
 * Usage: <script src="https://your-domain.com/frontend/js/widget.js" data-business-id="YOUR_BUSINESS_ID" defer></script>
 */

(function() {
    'use strict';

    // ============================================
    // Configuration
    // ============================================
    
    const CONFIG = {
        API_BASE_URL: window.location.origin,
        WIDGET_ID: 'conversapay-chat-widget',
        IFRAME_ID: 'conversapay-chat-iframe',
        TOGGLE_ID: 'conversapay-chat-toggle',
        BUSINESS_ID: null,
        COLORS: {
            primary: '#A855F7',
            secondary: '#00D9FF',
            background: '#0B0F19',
            text: '#F9FAFB',
            userBubble: 'rgba(168, 85, 247, 0.2)',
            botBubble: 'rgba(59, 130, 246, 0.15)'
        }
    };

    // ============================================
    // Initialization
    // ============================================

    function init() {
        // Extract business ID from script tag
        const currentScript = document.currentScript || document.querySelector('script[src*="widget.js"]');
        
        if (!currentScript) {
            console.error('ConversaPay Widget: Could not find script tag');
            return;
        }

        CONFIG.BUSINESS_ID = currentScript.getAttribute('data-business-id');
        
        if (!CONFIG.BUSINESS_ID) {
            console.error('ConversaPay Widget: Missing data-business-id attribute');
            return;
        }

        // Load widget configuration
        loadWidgetConfig();
    }

    // ============================================
    // Widget Configuration
    // ============================================

    async function loadWidgetConfig() {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1/widget/config/${CONFIG.BUSINESS_ID}`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                console.error('ConversaPay Widget: Failed to load config');
                return;
            }

            const config = await response.json();
            
            // Merge custom colors if provided
            if (config.theme_colors) {
                CONFIG.COLORS = { ...CONFIG.COLORS, ...config.theme_colors };
            }

            // Inject widget
            injectWidget(config);

        } catch (error) {
            console.error('ConversaPay Widget: Error loading config', error);
        }
    }

    // ============================================
    // Widget Injection
    // ============================================

    function injectWidget(config) {
        // Prevent duplicate injection
        if (document.getElementById(CONFIG.WIDGET_ID)) {
            return;
        }

        // Create widget container
        const widgetContainer = document.createElement('div');
        widgetContainer.id = CONFIG.WIDGET_ID;
        widgetContainer.innerHTML = getWidgetHTML(config);
        
        // Inject styles
        injectStyles();
        
        // Append to body
        document.body.appendChild(widgetContainer);

        // Attach event listeners
        attachEventListeners();
    }

    function getWidgetHTML(config) {
        return `
            <!-- Chat Toggle Button -->
            <div id="${CONFIG.TOGGLE_ID}" class="cp-chat-toggle">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 11.5C21 16.1944 16.9706 20 12 20C10.5 20 9.1 19.7 7.8 19.2L3 21L4.5 16.5C3.5 15 3 13.3 3 11.5C3 6.80558 7.02944 3 12 3C16.9706 3 21 6.80558 21 11.5Z" 
                          stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>

            <!-- Chat Window -->
            <div id="${CONFIG.IFRAME_ID}" class="cp-chat-window">
                <div class="cp-chat-header">
                    <div class="cp-chat-header-info">
                        <div class="cp-chat-avatar">🤖</div>
                        <div>
                            <div class="cp-chat-title">${escapeHtml(config.bot_name || 'AI Assistant')}</div>
                            <div class="cp-chat-status">● Online</div>
                        </div>
                    </div>
                    <button class="cp-chat-close" onclick="window.ConversaPayWidget.close()">✕</button>
                </div>
                <div class="cp-chat-messages" id="cpMessages"></div>
                <div class="cp-chat-input-area">
                    <input 
                        type="text" 
                        id="cpChatInput" 
                        placeholder="Type a message..." 
                        onkeypress="if(event.key==='Enter') window.ConversaPayWidget.sendMessage()"
                    >
                    <button onclick="window.ConversaPayWidget.sendMessage()">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                            <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }

    function injectStyles() {
        const styles = document.createElement('style');
        styles.id = 'conversapay-widget-styles';
        styles.textContent = getWidgetStyles();
        document.head.appendChild(styles);
    }

    function getWidgetStyles() {
        return `
            #conversapay-chat-widget {
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 99999;
                direction: ltr;
            }

            .cp-chat-toggle {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: linear-gradient(135deg, #A855F7 0%, #3B82F6 100%);
                box-shadow: 0 4px 20px rgba(168, 85, 247, 0.4);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
            }

            .cp-chat-toggle:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 30px rgba(168, 85, 247, 0.6);
            }

            .cp-chat-window {
                position: absolute;
                bottom: 75px;
                right: 0;
                width: 380px;
                height: 550px;
                background: #0B0F19;
                border-radius: 20px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
                display: none;
                flex-direction: column;
                overflow: hidden;
                backdrop-filter: blur(20px);
            }

            .cp-chat-window.open {
                display: flex;
                animation: slideUp 0.3s ease;
            }

            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .cp-chat-header {
                background: linear-gradient(135deg, rgba(168, 85, 247, 0.2) 0%, rgba(59, 130, 246, 0.2) 100%);
                padding: 16px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }

            .cp-chat-header-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .cp-chat-avatar {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: linear-gradient(135deg, #A855F7 0%, #3B82F6 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
            }

            .cp-chat-title {
                color: #F9FAFB;
                font-weight: 700;
                font-size: 0.95rem;
            }

            .cp-chat-status {
                color: #10B981;
                font-size: 0.75rem;
                margin-top: 2px;
            }

            .cp-chat-close {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                color: #9CA3AF;
                width: 32px;
                height: 32px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 1.2rem;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
            }

            .cp-chat-close:hover {
                background: rgba(255, 255, 255, 0.2);
                color: #F9FAFB;
            }

            .cp-chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                background: #0B0F19;
            }

            .cp-message {
                max-width: 80%;
                padding: 12px 16px;
                border-radius: 16px;
                font-size: 0.9rem;
                line-height: 1.5;
                word-wrap: break-word;
                animation: fadeIn 0.3s ease;
            }

            @keyframes fadeIn {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .cp-message.user {
                align-self: flex-start;
                background: rgba(168, 85, 247, 0.2);
                color: #F9FAFB;
                border: 1px solid rgba(168, 85, 247, 0.3);
                border-top-left-radius: 4px;
            }

            .cp-message.bot {
                align-self: flex-end;
                background: rgba(59, 130, 246, 0.15);
                color: #F9FAFB;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-top-right-radius: 4px;
            }

            .cp-chat-input-area {
                padding: 12px 16px;
                background: rgba(11, 15, 25, 0.9);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                gap: 8px;
            }

            .cp-chat-input-area input {
                flex: 1;
                padding: 10px 14px;
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                color: #F9FAFB;
                font-size: 0.9rem;
                font-family: inherit;
                outline: none;
                transition: all 0.3s ease;
            }

            .cp-chat-input-area input:focus {
                border-color: rgba(168, 85, 247, 0.5);
                box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.2);
            }

            .cp-chat-input-area input::placeholder {
                color: #6B7280;
            }

            .cp-chat-input-area button {
                background: linear-gradient(135deg, #A855F7 0%, #3B82F6 100%);
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 10px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
            }

            .cp-chat-input-area button:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(168, 85, 247, 0.4);
            }

            .cp-typing-indicator {
                display: none;
                padding: 8px 12px;
                background: rgba(59, 130, 246, 0.15);
                border-radius: 12px;
                color: #9CA3AF;
                font-size: 0.85rem;
                align-self: flex-end;
            }

            .cp-typing-indicator.active {
                display: block;
            }

            /* Scrollbar */
            .cp-chat-messages::-webkit-scrollbar {
                width: 6px;
            }

            .cp-chat-messages::-webkit-scrollbar-track {
                background: rgba(255, 255, 255, 0.05);
            }

            .cp-chat-messages::-webkit-scrollbar-thumb {
                background: rgba(168, 85, 247, 0.5);
                border-radius: 3px;
            }

            .cp-chat-messages::-webkit-scrollbar-thumb:hover {
                background: rgba(168, 85, 247, 0.7);
            }

            /* Responsive */
            @media (max-width: 480px) {
                .cp-chat-window {
                    width: calc(100vw - 40px);
                    height: calc(100vh - 120px);
                    right: 0;
                    bottom: 75px;
                }
            }
        `;
    }

    // ============================================
    // Event Listeners
    // ============================================

    function attachEventListeners() {
        const toggleBtn = document.getElementById(CONFIG.TOGGLE_ID);
        const chatWindow = document.getElementById(CONFIG.IFRAME_ID);

        if (toggleBtn && chatWindow) {
            toggleBtn.addEventListener('click', () => {
                chatWindow.classList.toggle('open');
            });
        }
    }

    // ============================================
    // Public API
    // ============================================

    window.ConversaPayWidget = {
        open: function() {
            const chatWindow = document.getElementById(CONFIG.IFRAME_ID);
            if (chatWindow) {
                chatWindow.classList.add('open');
            }
        },

        close: function() {
            const chatWindow = document.getElementById(CONFIG.IFRAME_ID);
            if (chatWindow) {
                chatWindow.classList.remove('open');
            }
        },

        sendMessage: function() {
            const input = document.getElementById('cpChatInput');
            if (!input) return;

            const message = input.value.trim();
            if (!message) return;

            // Append user message
            appendMessage(message, 'user');
            input.value = '';

            // Show typing indicator
            showTypingIndicator();

            // Send to backend
            fetch(`${CONFIG.API_BASE_URL}/api/v1/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    business_id: CONFIG.BUSINESS_ID
                })
            })
            .then(response => response.json())
            .then(data => {
                hideTypingIndicator();
                
                if (data.intent === 'checkout' && data.payment_url) {
                    appendMessage(
                        `${data.response}<br><br><a href="${data.payment_url}" target="_blank" style="color: #00D9FF; text-decoration: underline;">💳 Complete Payment</a>`,
                        'bot'
                    );
                } else {
                    appendMessage(data.response, 'bot');
                }
            })
            .catch(error => {
                hideTypingIndicator();
                console.error('ConversaPay Widget: Error sending message', error);
                appendMessage('Sorry, I encountered an error. Please try again.', 'bot');
            });
        }
    };

    // ============================================
    // Helper Functions
    // ============================================

    function appendMessage(text, sender) {
        const messagesContainer = document.getElementById('cpMessages');
        if (!messagesContainer) return;

        const messageElement = document.createElement('div');
        messageElement.className = `cp-message ${sender}`;
        messageElement.innerHTML = text;
        messagesContainer.appendChild(messageElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function showTypingIndicator() {
        const messagesContainer = document.getElementById('cpMessages');
        if (!messagesContainer) return;

        const indicator = document.createElement('div');
        indicator.className = 'cp-typing-indicator active';
        indicator.id = 'cpTypingIndicator';
        indicator.textContent = 'Typing...';
        messagesContainer.appendChild(indicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function hideTypingIndicator() {
        const indicator = document.getElementById('cpTypingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================
    // Start Widget
    // ============================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();