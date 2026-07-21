/**
 * ConversaPay AI Chat Widget
 * Embeddable chat widget for external websites
 * 
 * Usage: <script src="https://your-domain.com/frontend/js/widget.js" data-business-id="YOUR_BUSINESS_ID" defer></script>
 * 
 * Security: For non-Pro (Starter) users, the widget silently exits on external domains.
 * Only the private dashboard preview and the official landing page (business_id: "conversapay") are allowed.
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
        },
        // Hebrew localization
        LOCALE: {
            placeholder: 'הקלד הודעה...',
            online: '● מחובר',
            botName: 'נציג ConversaPay',
            typing: 'מקליד...',
            error: 'מצטער, אירעה שגיאה. אנא נסה שוב.',
            paymentLink: '💳 השלם תשלום',
            upgradePrompt: 'מעוניין לשדרג ל-Pro? לחץ כאן',
            proCheckout: 'https://conversapay.org/api/v1/payments/create-checkout-session'
        }
    };

    // ============================================
    // Initialization
    // ============================================

    function init() {
        // Extract business ID from script tag or window config
        const currentScript = document.currentScript || document.querySelector('script[src*="widget.js"]');
        
        // First check for window config (used by home.html)
        if (window.ConversaPayWidgetConfig && window.ConversaPayWidgetConfig.business_id) {
            CONFIG.BUSINESS_ID = window.ConversaPayWidgetConfig.business_id;
        } else if (currentScript) {
            CONFIG.BUSINESS_ID = currentScript.getAttribute('data-business-id');
        }
        
        // If no business_id yet, wait for dashboard.js to provide it
        if (!CONFIG.BUSINESS_ID) {
            console.log('ConversaPay Widget: Waiting for business_id from dashboard...');
            
            // Listen for custom event from dashboard.js
            const waitForBusinessId = (event) => {
                if (event.detail && event.detail.business_id) {
                    CONFIG.BUSINESS_ID = event.detail.business_id;
                    console.log('ConversaPay Widget: Business ID received:', CONFIG.BUSINESS_ID);
                    
                    // STRONG GUARD: block "conversapay", empty strings, and non-UUID formats
                    if (!isValidBusinessId(CONFIG.BUSINESS_ID)) {
                        console.warn('ConversaPay Widget: BLOCKED invalid businessId="' + CONFIG.BUSINESS_ID + '" - aborting widget load to prevent 403 crash');
                        CONFIG.BUSINESS_ID = null; // Reset to prevent further attempts
                        return;
                    }
                    
                    // Load widget configuration (includes pro check)
                    loadWidgetConfig();
                }
            };
            
            // Also check window.currentBusinessId as fallback
            const checkWindowBusinessId = () => {
                if (window.currentBusinessId) {
                    CONFIG.BUSINESS_ID = window.currentBusinessId;
                    console.log('ConversaPay Widget: Business ID from window:', CONFIG.BUSINESS_ID);
                    
                    // STRONG GUARD: block "conversapay", empty strings, and non-UUID formats
                    if (!isValidBusinessId(CONFIG.BUSINESS_ID)) {
                        console.warn('ConversaPay Widget: BLOCKED invalid businessId="' + CONFIG.BUSINESS_ID + '" - aborting widget load to prevent 403 crash');
                        CONFIG.BUSINESS_ID = null; // Reset to prevent further attempts
                        return;
                    }
                    
                    loadWidgetConfig();
                } else {
                    // Retry after 100ms
                    setTimeout(checkWindowBusinessId, 100);
                }
            };
            
            // Try both methods
            document.addEventListener('conversapay:business-ready', waitForBusinessId);
            setTimeout(checkWindowBusinessId, 100);
            
            // Timeout after 5 seconds — hide loading overlay so the page isn't stuck forever
            setTimeout(() => {
                if (!CONFIG.BUSINESS_ID) {
                    console.error('ConversaPay Widget: Timeout waiting for business_id');
                }
                hideLoadingOverlay();
            }, 5000);
            
            return;
        }

        // Load widget configuration (includes pro check)
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
                // If 403 (domain not authorized), silently exit for non-Pro users
                if (response.status === 403) {
                    console.warn('ConversaPay Widget: Domain not authorized. Upgrade to Pro to enable widget on external sites.');
                    hideLoadingOverlay();
                    injectErrorMessage('הדומיין לא מורשה. שדרג ל-Pro כדי להפעיל את הוידג\'ט באתרים חיצוניים.');
                } else {
                    console.error('ConversaPay Widget: Failed to load config');
                    hideLoadingOverlay();
                    injectErrorMessage('שגיאה בטעינת תצורת הוידג\'ט. נסה שוב מאוחר יותר.');
                }
                return;
            }

            const config = await response.json();
            
            // Guard against empty/malformed config
            if (!config || typeof config !== 'object') {
                console.error('ConversaPay Widget: Received empty or malformed config');
                hideLoadingOverlay();
                injectErrorMessage('תצורת הוידג\'ט ריקה. צור קשר עם התמיכה.');
                return;
            }
            
            // Merge custom colors if provided
            if (config.theme_colors) {
                CONFIG.COLORS = { ...CONFIG.COLORS, ...config.theme_colors };
            }
            
            // Use configured bot name or default Hebrew name
            if (config.bot_name) {
                CONFIG.LOCALE.botName = config.bot_name;
            }

            // Inject widget
            injectWidget(config);
            
            // Hide loading overlay after widget is successfully injected
            hideLoadingOverlay();

        } catch (error) {
            console.error('ConversaPay Widget: Error loading config', error);
            // Hide loading overlay even on error so the page isn't stuck
            hideLoadingOverlay();
            injectErrorMessage('שגיאת רשת בטעינת תצורת הוידג\'ט. בדוק את החיבור לאינטרנט ונסה שוב.');
        }
    }

    /**
     * Safely hide the loading overlay if it exists on the page.
     * This is called from multiple paths (success, error, 403, timeout)
     * to ensure the user is never left staring at a loading spinner.
     */
    function hideLoadingOverlay() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('d-none');
        }
    }

    /**
     * Inject a visible error message into the page so it's never left blank.
     * Creates a styled container with the error text and appends it to body.
     * @param {string} message - The error message to display (Hebrew supported).
     */
    function injectErrorMessage(message) {
        // Prevent duplicate error containers
        if (document.getElementById('conversapay-widget-error')) {
            return;
        }
        const errorDiv = document.createElement('div');
        errorDiv.id = 'conversapay-widget-error';
        errorDiv.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;padding:16px 20px;background:#EF4444;color:white;font-family:sans-serif;font-size:14px;text-align:center;direction:rtl;';
        errorDiv.textContent = 'ConversaPay Widget: ' + message;
        document.body.appendChild(errorDiv);
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
                            <div class="cp-chat-title">${escapeHtml(config.bot_name || CONFIG.LOCALE.botName)}</div>
                            <div class="cp-chat-status">${CONFIG.LOCALE.online}</div>
                        </div>
                    </div>
                    <button class="cp-chat-close" onclick="window.ConversaPayWidget.close()">✕</button>
                </div>
                <div class="cp-chat-messages" id="cpMessages"></div>
                <div class="cp-chat-input-area">
                    <input 
                        type="text" 
                        id="cpChatInput" 
                        placeholder="${CONFIG.LOCALE.placeholder}" 
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
                left: 20px;
                z-index: 99999;
                direction: rtl;
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
                left: 0;
                width: 380px;
                height: 550px;
                /* Never let the window be bigger than the available viewport,
                   regardless of screen size — not just on the 480px mobile breakpoint */
                max-width: calc(100vw - 40px);
                max-height: calc(100vh - 110px);
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
                    left: 0;
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

    // Session management
    let currentSessionId = null;

    function getOrCreateSessionId() {
        // Try to get from localStorage
        const stored = localStorage.getItem(`conversapay_session_${CONFIG.BUSINESS_ID}`);
        if (stored) {
            return stored;
        }
        // Generate new session ID
        const newSessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem(`conversapay_session_${CONFIG.BUSINESS_ID}`, newSessionId);
        return newSessionId;
    }

    // Initialize session ID
    currentSessionId = getOrCreateSessionId();

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

    // Validate business_id exists
    if (!CONFIG.BUSINESS_ID) {
        console.error('ConversaPay Widget: Cannot send message - no business_id configured');
        appendMessage('שגיאה: תצורת הוידג\'ט לא הוגדרה כראוי.', 'bot');
        return;
    }

    // Append user message immediately
    appendMessage(message, 'user');
    input.value = '';

    // Show typing indicator
    showTypingIndicator();

    // Prepare request payload - EXACTLY matching ChatRequest model
    const payload = {
        message: message,
        business_id: String(CONFIG.BUSINESS_ID),   // Must be string
        session_id: currentSessionId || null,      // Optional but recommended
        customer_info: this.customerInfo || {}     // Optional
    };

    console.log('Sending chat payload:', payload);

    // Send to backend
    fetch(`${CONFIG.API_BASE_URL}/api/v1/chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(async response => {
        hideTypingIndicator();
        
        // Handle HTTP errors
        if (!response.ok) {
            let errorDetail = 'Unknown error';
            try {
                const errorData = await response.json();
                errorDetail = errorData.detail || errorData.message || JSON.stringify(errorData);
            } catch (e) {
                errorDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            
            console.error('ConversaPay Widget: API error', {
                status: response.status,
                detail: errorDetail
            });
            
            // User-friendly messages
            const errorMessages = {
                422: 'שגיאה בנתונים שנשלחו. נסה שוב.',
                500: 'מצטער, אירעה שגיאה בשרת. נסה שוב מאוחר יותר.',
                404: 'שירות הצ\'אט לא זמין כרגע.',
                429: 'יותר מדי הודעות. המתן רגע ונסה שוב.'
            };
            
            const userMessage = errorMessages[response.status] || 'שגיאה לא צפויה. נסה שוב.';
            appendMessage(userMessage, 'bot');
            return;
        }
        
        return response.json();
    })
    .then(data => {
        if (!data) return;
        
        // Update session ID if provided
        if (data.session_id && data.session_id !== currentSessionId) {
            currentSessionId = data.session_id;
            localStorage.setItem(`conversapay_session_${CONFIG.BUSINESS_ID}`, currentSessionId);
        }
        
        // Handle response
        if (data.intent === 'checkout' && data.payment_url) {
            appendMessage(
                `${data.response}<br><br><a href="${data.payment_url}" target="_blank" rel="noopener noreferrer" style="color: #00D9FF; text-decoration: underline;">לחץ כאן לתשלום</a>`,
                'bot'
            );
        } else if (data.response) {
            appendMessage(data.response, 'bot');
        } else {
            appendMessage("הבנתי, אבל אין לי תשובה כרגע.", 'bot');
        }
    })
    .catch(error => {
        hideTypingIndicator();
        console.error('ConversaPay Widget: Network error', error);
        appendMessage("שגיאה בתקשורת עם השרת. נסה שוב.", 'bot');
    });
    }
}
    // ============================================
    // Validation
    // ============================================

    function isValidBusinessId(businessId) {
        if (!businessId || typeof businessId !== 'string') return false;
        // Reject known fallback strings
        if (businessId === 'conversapay') return false;
        if (businessId === '') return false;
        // Validate UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        return uuidRegex.test(businessId);
    }

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
        indicator.textContent = CONFIG.LOCALE.typing;
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