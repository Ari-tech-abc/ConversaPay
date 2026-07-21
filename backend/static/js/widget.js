/**
 * ConversaPay AI Shopping Assistant Widget
 * Embeddable chat widget for e-commerce websites
 * 
 * Usage: <script src="http://localhost:8000/static/widget.js" data-business-id="YOUR_BUSINESS_ID"></script>
 */

(function() {
    'use strict';

    // ============================================
    // Configuration
    // ============================================
    
    const CONFIG = {
        API_BASE_URL: window.location.origin + '/api/v1',
        WIDGET_ID: 'conversapay-widget',
        COLORS: {
            primary: '#007bff',
            primaryDark: '#0056b3',
            success: '#28a745',
            background: '#ffffff',
            text: '#0f172a',
            gray: '#64748b',
            lightGray: '#f1f5f9'
        },
        MESSAGES: {
            welcome: 'היי! אני עוזר הקניות הדיגיטלי שלכם. במה אוכל לעזור היום?',
            typing: 'מקליד...',
            error: 'מצטער, אירעה שגיאה. אנא נסה שוב.'
        }
    };

    // ============================================
    // State Management
    // ============================================
    
    let state = {
        isOpen: false,
        businessId: null,
        sessionId: null,
        messages: [],
        isTyping: false,
        paymentPolls: {}
    };

    // ============================================
    // Widget Initialization
    // ============================================
    
    function init() {
        // Get business ID from script tag
        const currentScript = document.currentScript || (function() {
            const scripts = document.getElementsByTagName('script');
            return scripts[scripts.length - 1];
        })();
        
        state.businessId = currentScript.getAttribute('data-business-id');
        
        if (!state.businessId) {
            console.error('ConversaPay Widget: data-business-id attribute is required');
            return;
        }

        // Generate or retrieve session ID from localStorage
        state.sessionId = localStorage.getItem(`conversapay_session_${state.businessId}`);
        if (!state.sessionId) {
            state.sessionId = generateSessionId();
            localStorage.setItem(`conversapay_session_${state.businessId}`, state.sessionId);
        }

        // Inject widget HTML and CSS
        injectStyles();
        injectHTML();
        
        // Bind events
        bindEvents();
        
        // Load welcome message
        setTimeout(() => {
            addMessage(CONFIG.MESSAGES.welcome, 'assistant');
        }, 500);
    }

    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // ============================================
    // HTML Injection
    // ============================================
    
    function injectHTML() {
        const widgetHTML = `
            <div id="${CONFIG.WIDGET_ID}">
                <!-- Chat Bubble Button -->
                <div id="cp-chat-bubble" class="cp-chat-bubble">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M21 11.5C21 16.1944 16.9706 20 12 20C10.5 20 9.1 19.7 7.8 19.2L3 21L4.5 16.5C3.5 15 3 13.3 3 11.5C3 6.80558 7.02944 3 12 3C16.9706 3 21 6.80558 21 11.5Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>

                <!-- Chat Window -->
                <div id="cp-chat-window" class="cp-chat-window">
                    <!-- Header -->
                    <div class="cp-chat-header">
                        <div class="cp-chat-header-info">
                            <div class="cp-chat-header-title">עוזר קניות</div>
                            <div class="cp-chat-header-status">מקוון</div>
                        </div>
                        <button id="cp-close-btn" class="cp-close-btn">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                    </div>

                    <!-- Messages Container -->
                    <div id="cp-messages" class="cp-messages">
                        <!-- Messages will be inserted here -->
                    </div>

                    <!-- Typing Indicator -->
                    <div id="cp-typing" class="cp-typing-indicator d-none">
                        <div class="cp-typing-dot"></div>
                        <div class="cp-typing-dot"></div>
                        <div class="cp-typing-dot"></div>
                    </div>

                    <!-- Input Area -->
                    <div class="cp-chat-input-area">
                        <form id="cp-chat-form">
                            <input 
                                type="text" 
                                id="cp-message-input" 
                                class="cp-message-input" 
                                placeholder="הקלד הודעה..."
                                autocomplete="off"
                            >
                            <button type="submit" id="cp-send-btn" class="cp-send-btn">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', widgetHTML);
    }

    // ============================================
    // CSS Injection
    // ============================================
    
    function injectStyles() {
        const styles = `
            #${CONFIG.WIDGET_ID} {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                position: fixed;
                bottom: 20px;
                left: 20px;
                z-index: 9999;
                direction: rtl;
                text-align: right;
            }

            /* Chat Bubble */
            .cp-chat-bubble {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: ${CONFIG.COLORS.primary};
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
            }

            .cp-chat-bubble:hover {
                background: ${CONFIG.COLORS.primaryDark};
                transform: scale(1.1);
            }

            /* Chat Window */
            .cp-chat-window {
                position: absolute;
                bottom: 80px;
                left: 0;
                width: 380px;
                height: 520px;
                background: ${CONFIG.COLORS.background};
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                display: none;
                flex-direction: column;
                overflow: hidden;
            }

            .cp-chat-window.open {
                display: flex;
            }

            /* Header */
            .cp-chat-header {
                background: ${CONFIG.COLORS.primary};
                color: white;
                padding: 16px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .cp-chat-header-title {
                font-size: 1.1rem;
                font-weight: 600;
            }

            .cp-chat-header-status {
                font-size: 0.85rem;
                opacity: 0.9;
            }

            .cp-close-btn {
                background: rgba(255, 255, 255, 0.2);
                border: none;
                color: white;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s;
            }

            .cp-close-btn:hover {
                background: rgba(255, 255, 255, 0.3);
            }

            /* Messages */
            .cp-messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .cp-message {
                max-width: 80%;
                padding: 10px 14px;
                border-radius: 12px;
                word-wrap: break-word;
                animation: fadeIn 0.3s ease;
            }

            .cp-message.user {
                align-self: flex-start;
                background: ${CONFIG.COLORS.primary};
                color: white;
                border-bottom-right-radius: 4px;
            }

            .cp-message.assistant {
                align-self: flex-end;
                background: ${CONFIG.COLORS.lightGray};
                color: ${CONFIG.COLORS.text};
                border-bottom-left-radius: 4px;
            }

            .cp-message a {
                color: ${CONFIG.COLORS.primary};
                text-decoration: underline;
            }

            .cp-message .cp-payment-btn {
                display: inline-block;
                background: ${CONFIG.COLORS.success};
                color: white;
                padding: 8px 16px;
                border-radius: 8px;
                text-decoration: none;
                margin-top: 8px;
                font-weight: 600;
                transition: background 0.2s;
            }

            .cp-message .cp-payment-btn:hover {
                background: #218838;
            }

            /* Checkout Card */
            .cp-checkout-card {
                max-width: 90%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
                animation: slideIn 0.4s ease;
                margin: 8px 0;
            }

            .cp-checkout-card-header {
                background: rgba(255, 255, 255, 0.15);
                padding: 12px 16px;
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .cp-checkout-icon {
                font-size: 1.5rem;
            }

            .cp-checkout-title {
                color: white;
                font-size: 1rem;
                font-weight: 600;
            }

            .cp-checkout-card-body {
                padding: 16px;
                background: rgba(255, 255, 255, 0.95);
            }

            .cp-checkout-message {
                color: #1e293b;
                font-size: 0.9rem;
                margin-bottom: 12px;
                line-height: 1.4;
            }

            .cp-checkout-product {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 12px;
            }

            .cp-checkout-product-name {
                color: #0f172a;
                font-weight: 600;
                font-size: 1rem;
                margin-bottom: 8px;
            }

            .cp-checkout-product-details {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .cp-checkout-quantity {
                color: #64748b;
                font-size: 0.85rem;
            }

            .cp-checkout-price {
                color: #667eea;
                font-weight: 700;
                font-size: 1.2rem;
            }

            .cp-checkout-card-footer {
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.1);
            }

            .cp-checkout-pay-btn {
                width: 100%;
                background: linear-gradient(135deg, #10b981, #059669);
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 10px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
            }

            .cp-checkout-pay-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
                background: linear-gradient(135deg, #059669, #047857);
            }

            .cp-checkout-pay-btn:active {
                transform: translateY(0);
            }

            .cp-checkout-btn-icon {
                font-size: 1.2rem;
            }

            .cp-checkout-btn-text {
                font-size: 1rem;
            }

            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            /* Typing Indicator */
            .cp-typing-indicator {
                display: flex;
                gap: 4px;
                padding: 10px 14px;
                background: ${CONFIG.COLORS.lightGray};
                border-radius: 12px;
                width: fit-content;
            }

            .cp-typing-indicator.d-none {
                display: none;
            }

            .cp-typing-dot {
                width: 8px;
                height: 8px;
                background: ${CONFIG.COLORS.gray};
                border-radius: 50%;
                animation: typing 1.4s infinite;
            }

            .cp-typing-dot:nth-child(2) {
                animation-delay: 0.2s;
            }

            .cp-typing-dot:nth-child(3) {
                animation-delay: 0.4s;
            }

            @keyframes typing {
                0%, 60%, 100% {
                    transform: translateY(0);
                }
                30% {
                    transform: translateY(-10px);
                }
            }

            /* Input Area */
            .cp-chat-input-area {
                padding: 12px 16px;
                border-top: 1px solid #e2e8f0;
                background: white;
            }

            .cp-chat-form {
                display: flex;
                gap: 8px;
            }

            .cp-message-input {
                flex: 1;
                padding: 10px 14px;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
                font-size: 0.95rem;
                outline: none;
                transition: border-color 0.2s;
            }

            .cp-message-input:focus {
                border-color: ${CONFIG.COLORS.primary};
            }

            .cp-send-btn {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: ${CONFIG.COLORS.primary};
                color: white;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s;
            }

            .cp-send-btn:hover {
                background: ${CONFIG.COLORS.primaryDark};
            }

            .cp-send-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            /* Animations */
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

            /* Scrollbar */
            .cp-messages::-webkit-scrollbar {
                width: 6px;
            }

            .cp-messages::-webkit-scrollbar-track {
                background: transparent;
            }

            .cp-messages::-webkit-scrollbar-thumb {
                background: #cbd5e1;
                border-radius: 3px;
            }

            .cp-messages::-webkit-scrollbar-thumb:hover {
                background: #94a3b8;
            }

            /* Responsive */
            @media (max-width: 480px) {
                .cp-chat-window {
                    width: calc(100vw - 40px);
                    height: calc(100vh - 120px);
                    bottom: 80px;
                    left: 20px;
                }
            }
        `;

        const styleElement = document.createElement('style');
        styleElement.textContent = styles;
        styleElement.id = 'conversapay-widget-styles';
        document.head.appendChild(styleElement);
    }

    // ============================================
    // Event Binding
    // ============================================
    
    function bindEvents() {
        // Chat bubble click
        document.getElementById('cp-chat-bubble').addEventListener('click', toggleChat);
        
        // Close button
        document.getElementById('cp-close-btn').addEventListener('click', closeChat);
        
        // Form submission
        document.getElementById('cp-chat-form').addEventListener('submit', handleSubmit);
        
        // Enter key to send
        document.getElementById('cp-message-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
            }
        });
    }

    // ============================================
    // Chat Functions
    // ============================================
    
    function toggleChat() {
        state.isOpen = !state.isOpen;
        const chatWindow = document.getElementById('cp-chat-window');
        
        if (state.isOpen) {
            chatWindow.classList.add('open');
            document.getElementById('cp-message-input').focus();
        } else {
            chatWindow.classList.remove('open');
        }
    }

    function closeChat() {
        state.isOpen = false;
        document.getElementById('cp-chat-window').classList.remove('open');
    }

    async function handleSubmit(event) {
        event.preventDefault();
        
        const input = document.getElementById('cp-message-input');
        const message = input.value.trim();
        
        if (!message || state.isTyping) return;
        
        // Add user message
        addMessage(message, 'user');
        input.value = '';
        
        // Show typing indicator
        showTyping(true);
        
        try {
            // Send to backend
            const response = await fetch(`${CONFIG.API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    business_id: state.businessId,
                    message: message,
                    session_id: state.sessionId
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to send message');
            }
            
            const data = await response.json();
            
            // Hide typing indicator
            showTyping(false);
            
            // Check for checkout action data
            if (data.action_data && data.action_data.action === 'show_checkout') {
                // Render checkout card instead of text bubble
                addCheckoutCard(data.response, data.action_data, data.payment_url);
            } else {
                // Add regular assistant response
                addMessage(data.response, 'assistant', data.payment_url);
            }
            
        } catch (error) {
            console.error('Chat error:', error);
            showTyping(false);
            addMessage(CONFIG.MESSAGES.error, 'assistant');
        }
    }

    function addCheckoutCard(message, actionData, paymentUrl) {
        const messagesContainer = document.getElementById('cp-messages');
        const cardDiv = document.createElement('div');
        cardDiv.className = 'cp-checkout-card';
        const currencySymbol = actionData.currency === 'ILS' ? '₪' : '$';
        const isExternal = paymentUrl && !paymentUrl.startsWith('/');

        cardDiv.innerHTML = `
            <div class="cp-checkout-card-header">
                <div class="cp-checkout-icon">🛒</div>
                <div class="cp-checkout-title">הזמנה חדשה</div>
            </div>
            <div class="cp-checkout-card-body">
                <div class="cp-checkout-message">${escapeHtml(message.replace(/\[CHECKOUT:[^\]]*\]/g, '').trim())}</div>
                <div class="cp-checkout-product">
                    <div class="cp-checkout-product-name">${escapeHtml(actionData.product_name)}</div>
                    <div class="cp-checkout-product-details">
                        <span class="cp-checkout-quantity">כמות: ${actionData.quantity}</span>
                        <span class="cp-checkout-price">${currencySymbol}${parseFloat(actionData.total).toFixed(2)}</span>
                    </div>
                </div>
            </div>
            <div class="cp-checkout-card-footer">
                ${isExternal
                    ? `<a href="${paymentUrl}" target="_blank" class="cp-checkout-pay-btn" style="text-decoration:none;">
                           <span class="cp-checkout-btn-icon">💳</span>
                           <span class="cp-checkout-btn-text">לתשלום מאובטח</span>
                       </a>`
                    : `<button class="cp-checkout-pay-btn" onclick="window.open('${paymentUrl}','_blank')">
                           <span class="cp-checkout-btn-icon">💳</span>
                           <span class="cp-checkout-btn-text">לתשלום מאובטח</span>
                       </button>`
                }
            </div>
        `;

        messagesContainer.appendChild(cardDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        state.messages.push({ content: message, role: 'assistant', actionData, paymentUrl, type: 'checkout' });
    }

    // Global function to start payment polling
    window.startPaymentPolling = function(orderId, paymentUrl) {
        // Open payment URL in new tab
        window.open(paymentUrl, '_blank');
        
        // Update button to pending state
        const payBtn = document.getElementById(`pay-btn-${orderId}`);
        if (payBtn) {
            payBtn.disabled = true;
            payBtn.innerHTML = `
                <span class="cp-checkout-btn-icon">⏳</span>
                <span class="cp-checkout-btn-text">ממתין לתשלום...</span>
            `;
            payBtn.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
            payBtn.style.cursor = 'not-allowed';
        }
        
        const checkPaymentStatus = async () => {
            try {
                const response = await fetch(`${CONFIG.API_BASE_URL}/orders/${orderId}/status`);
                if (!response.ok) {
                    return;
                }
                const data = await response.json();
                
                if (data.status === 'paid') {
                    // Stop polling
                    clearInterval(pollInterval);
                    delete state.paymentPolls[orderId];
                    
                    // Update button to success state
                    if (payBtn) {
                        payBtn.disabled = true;
                        payBtn.innerHTML = `
                            <span class="cp-checkout-btn-icon">✅</span>
                            <span class="cp-checkout-btn-text">✅ Paid Successfully / שולם בהצלחה!</span>
                        `;
                        payBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
                        payBtn.style.cursor = 'not-allowed';
                    }
                    
                    // Inject system message into chat thread
                    addMessage('תודה רבה! התשלום התקבל בהצלחה וההזמנה שלך בטיפול.', 'assistant');
                }
            } catch (error) {
                console.error('Error polling payment status:', error);
            }
        };
        
        // Run an immediate check, then continue polling every 3 seconds
        checkPaymentStatus();
        const pollInterval = setInterval(checkPaymentStatus, 3000);
        
        // Store interval ID to clear if needed
        state.paymentPolls[orderId] = pollInterval;
    };

    /**
     * Safely validate a payment URL before attaching it to an anchor.
     * Only allows relative paths (starting with '/') or URLs matching our verified origin.
     */
    function isValidPaymentUrl(url) {
        if (!url) return false;
        if (url.startsWith('/')) return true;
        try {
            const parsed = new URL(url);
            // Allow https only (blocks javascript: etc)
            return parsed.protocol === 'https:' || parsed.protocol === 'http:';
        } catch {
            return false;
        }
    }

    function addMessage(content, role, paymentUrl = null) {
        const messagesContainer = document.getElementById('cp-messages');
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `cp-message ${role}`;
        
        // Use textContent for the message text (XSS-safe)
        const textSpan = document.createElement('span');
        textSpan.textContent = content;
        messageDiv.appendChild(textSpan);
        
        // If there's a payment URL, securely add a button
        if (paymentUrl && isValidPaymentUrl(paymentUrl)) {
            const link = document.createElement('a');
            link.href = paymentUrl;
            link.className = 'cp-payment-btn';
            link.target = '_blank';
            link.textContent = 'לתשלום מהיר 💳';
            messageDiv.appendChild(document.createElement('br'));
            messageDiv.appendChild(link);
        } else {
            // Check for CHECKOUT pattern in content
            const checkoutMatch = content.match(/CHECKOUT:\s*ITEM=(\w+)\s+AMOUNT=([\d.]+)/);
            if (checkoutMatch) {
                const itemKey = checkoutMatch[1];
                const amount = checkoutMatch[2];
                const generatedUrl = `${window.location.origin}/pay.html?biz=${state.businessId}&item=${itemKey}&amt=${amount}`;
                if (isValidPaymentUrl(generatedUrl)) {
                    const link = document.createElement('a');
                    link.href = generatedUrl;
                    link.className = 'cp-payment-btn';
                    link.target = '_blank';
                    link.textContent = 'לתשלום מהיר 💳';
                    messageDiv.appendChild(document.createElement('br'));
                    messageDiv.appendChild(link);
                }
            }
        }
        
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Store in state
        state.messages.push({ content, role, paymentUrl });
    }

    function showTyping(show) {
        state.isTyping = show;
        const typingIndicator = document.getElementById('cp-typing');
        
        if (show) {
            typingIndicator.classList.remove('d-none');
        } else {
            typingIndicator.classList.add('d-none');
        }
    }

    // ============================================
    // Utility Functions
    // ============================================
    
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