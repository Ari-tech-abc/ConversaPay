/**
 * ConversaPay Dashboard JavaScript
 * Handles authentication, data loading, orders management, and UI interactions
 */

// ============================================
// Configuration
// ============================================

const API_BASE_URL = window.location.origin + '/api/v1';
let currentUser = null;
let currentBusiness = null; // { business_id, business_name, ... }
let isDashboardInitialized = false; // Global lock to prevent duplicate initialization

// ============================================
// SAFETY NET — never leave the user on a blank/stuck loading screen
// ============================================

// 1) Catch any uncaught synchronous error anywhere in the app.
window.addEventListener('error', (event) => {
    console.error('🔴 [SAFETY NET] Uncaught error:', event.message, 'at', event.filename + ':' + event.lineno + ':' + event.colno, event.error);
    forceUnstickUI('Uncaught error: ' + event.message);
});

// 2) Catch any uncaught rejected Promise (e.g. an unawaited async function that throws).
window.addEventListener('unhandledrejection', (event) => {
    console.error('🔴 [SAFETY NET] Unhandled promise rejection:', event.reason);
    forceUnstickUI('Unhandled promise rejection: ' + (event.reason?.message || event.reason));
});

// 3) Absolute last resort: if after 8 seconds the loading overlay is still visible,
//    something silently failed. Force it away and show whatever state we can.
let safetyNetTimer = setTimeout(() => {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay && !overlay.classList.contains('d-none')) {
        console.error('🔴 [SAFETY NET] Loading overlay still visible after 8s — forcing it closed.');
        forceUnstickUI('Timeout: loading took longer than 8 seconds — check the errors logged above this line.');
    }
}, 8000);

function forceUnstickUI(reasonForLog) {
    console.error('🔴 [SAFETY NET] Forcing UI unstuck. Reason:', reasonForLog);
    try { hideLoading(); } catch (e) { console.error('hideLoading itself failed:', e); }
    // If nothing else has rendered any state yet, fall back to the "no business" screen
    // so the user sees *something* actionable instead of a blank page.
    const dashboardContent = document.getElementById('dashboardContent');
    const noBusinessState = document.getElementById('noBusinessState');
    const upgradeState = document.getElementById('upgradeState');
    const anyVisible =
        (dashboardContent && !dashboardContent.classList.contains('d-none')) ||
        (noBusinessState && !noBusinessState.classList.contains('d-none')) ||
        (upgradeState && !upgradeState.classList.contains('d-none'));
    if (!anyVisible && noBusinessState) {
        noBusinessState.classList.remove('d-none');
    }
}

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('✅ [1] DOMContentLoaded fired');
    initializeEventListeners();
    checkAuthStatus();
});

function initializeEventListeners() {
    document.getElementById('logoutBtn')?.addEventListener('click', handleLogout);
    
    // Pro upgrade
    document.getElementById('upgradeToProBtn')?.addEventListener('click', () => handleUpgradeToPlan('pro'));
    document.getElementById('upgradeToPremiumBtn')?.addEventListener('click', () => handleUpgradeToPlan('premium'));
    
    // Business creation
    document.getElementById('showCreateFromEmpty')?.addEventListener('click', showCreateBusinessForm);
    document.getElementById('cancelCreateBusiness')?.addEventListener('click', hideCreateBusinessForm);
    document.getElementById('createBusinessForm')?.addEventListener('submit', handleCreateBusiness);
    
    // Product management
    document.getElementById('addProductBtn')?.addEventListener('click', showAddProductForm);
    document.getElementById('cancelProductBtn')?.addEventListener('click', hideProductForm);
    document.getElementById('productForm')?.addEventListener('submit', handleSaveProduct);
    
    // Integrations
    document.getElementById('downloadWordPressPlugin')?.addEventListener('click', downloadWordPressPlugin);
    document.getElementById('copyEmbedCode')?.addEventListener('click', copyEmbedCode);
    
    // WhatsApp
    document.getElementById('whatsappForm')?.addEventListener('submit', handleSaveWhatsApp);
    document.getElementById('waCopyWebhook')?.addEventListener('click', copyWebhookUrl);
}

// ============================================
// Loading State Management
// ============================================

function showLoading() {
    document.getElementById('loadingOverlay').classList.remove('d-none');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('d-none');
}

// ============================================
// Authentication
// ============================================

function checkAuthStatus() {
    console.log('✅ [2] checkAuthStatus() called');
    const token = ConversaPayAuth.getToken();
    console.log('✅ [2a] token present:', !!token);
    if (token) {
        // Show loading while checking auth and subscription
        showLoading();
        
        fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(response => {
            console.log('✅ [3] /auth/me responded with status:', response.status);
            if (response.ok) return response.json();
            ConversaPayAuth.logout();
            return null;
        })
        .then(data => {
            console.log('✅ [4] /auth/me data:', data);
            if (data) {
                currentUser = data;
                // Check email verification before anything else
                const profile = data.profile || {};
                if (profile.email_verified === false) {
                    hideLoading();
                    const wall = document.getElementById('emailVerificationWall');
                    if (wall) wall.classList.remove('d-none');
                    return;
                }
                checkSubscriptionStatus();
            }
        })
        .catch(error => {
            console.error('🔴 Auth check error:', error);
            hideLoading();
            window.location.href = '/login.html';
        });
    } else {
        hideLoading();
        window.location.href = '/login.html';
    }
}

// ============================================
// Subscription Management
// ============================================

async function checkSubscriptionStatus() {
    console.log('✅ [5] checkSubscriptionStatus() called');
    // Default to free until proven otherwise
    window.userSubscriptionStatus = { isPro: false, planType: 'free' };
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/payments/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        console.log('✅ [6] /payments/profile responded with status:', response.status);
        
        if (response.ok) {
            const profile = await response.json();
            console.log('✅ [7] profile data:', profile);
            const isPro = ['pro', 'premium'].includes((profile.plan_type || '').toLowerCase());
            window.userSubscriptionStatus = {
                isPro,
                planType: profile.plan_type || 'free'
            };
        }
    } catch (error) {
        console.error('🔴 Error checking subscription:', error);
    }
    await loadUserBusinesses();
}

function showUpgradeState() {
    // Show billing section with 2-tier pricing, hide integrations
    document.getElementById('billing-upgrade-section').style.display = 'block';
    document.getElementById('integrations-setup-section').style.display = 'none';
    
    // Hide dashboard content
    document.getElementById('upgradeState').classList.remove('d-none');
    document.getElementById('noBusinessState').classList.add('d-none');
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.add('d-none');
    document.getElementById('proPlanBanner').classList.add('d-none');
    
    // Hide loading
    hideLoading();
}

async function handleUpgradeToPlan(planType, buttonEl) {
    // Accept an explicit button element (used by the lock-overlay buttons, which
    // don't have the fixed IDs below). Fall back to the fixed IDs for the main
    // billing/upgrade screen buttons that don't pass one.
    const btn = buttonEl || document.getElementById(planType === 'pro' ? 'upgradeToProBtn' : 'upgradeToPremiumBtn');
    const planName = planType === 'pro' ? 'Pro' : 'Premium';
    const planPrice = planType === 'pro' ? '200 ₪' : '350 ₪';
    const originalText = btn ? btn.textContent : '';
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'מפנה לתשלום...';
    }
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/payments/create-checkout-session`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: currentUser.user_id || currentUser.id,
                email: currentUser.email,
                full_name: currentUser.full_name || '',
                plan_type: planType
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Redirect to PayMe hosted payment page
            if (data.url) {
                window.location.href = data.url;
            } else {
                throw new Error('No URL returned');
            }
        } else {
            const data = await response.json();
            alert('שגיאה: ' + (data.detail || 'נסה שוב'));
        }
    } catch (error) {
        console.error('Upgrade error:', error);
        alert('שגיאה בתקשורת עם השרת');
    } finally {
        if (btn) {
            btn.disabled = false;
            // Overlay buttons have their own short label; restore that instead of
            // the "💳 שדרג ל-X - Y ₪" format used only by the main billing screen buttons.
            btn.textContent = buttonEl ? originalText : `💳 שדרג ל-${planName} - ${planPrice}`;
        }
    }
}

function handleLogout() {
    if (confirm('האם אתה בטוח שברצונך להתנתק?')) {
        if (window.ConversaPayAuth) {
            window.ConversaPayAuth.logout();
        } else {
            localStorage.removeItem('conversapay_auth_token');
            localStorage.removeItem('conversapay_user');
            window.location.href = '/login.html';
        }
    }
}

// ============================================
// Business Management (No Selector - Auto Bind)
// ============================================

async function loadUserBusinesses() {
    console.log('✅ [8] loadUserBusinesses() called');
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/businesses`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        console.log('✅ [9] /businesses responded with status:', response.status);
        
        if (response.ok) {
            const businesses = await response.json();
            console.log('✅ [10] businesses data (checking it is an array with items):', businesses);
            
            if (!Array.isArray(businesses)) {
                console.error('🔴 [10a] /businesses did NOT return an array! Got:', typeof businesses, businesses);
            }
            
            if (!businesses || businesses.length === 0) {
                // State A: No business - show empty state
                console.log('✅ [11] No businesses found -> showNoBusinessState()');
                showNoBusinessState();
            } else {
                // State B: Has business - auto-bind to first one
                console.log('✅ [11] Business found, binding to first one:', businesses[0]);
                currentBusiness = businesses[0];
                showDashboardState();
            }
        } else {
            // Request failed (401/404/500/etc) - don't leave the user stuck on the loading screen
            console.error('Failed to load businesses. Status:', response.status);
            let detail = '';
            try { detail = (await response.json()).detail || ''; } catch (e) {}
            hideLoading();
            showNoBusinessState();
            alert('שגיאה בטעינת נתוני העסק' + (detail ? (': ' + detail) : ' (קוד שגיאה: ' + response.status + ')') + '\n\nרענן את הדף או פנה לתמיכה אם הבעיה נמשכת.');
        }
    } catch (error) {
        // Network error / server unreachable - same rule: never leave the loading overlay stuck
        console.error('Error loading businesses:', error);
        hideLoading();
        showNoBusinessState();
        alert('שגיאה בתקשורת עם השרת. בדוק את החיבור לאינטרנט או נסה שוב מאוחר יותר.');
    }
}

function showNoBusinessState() {
    const isPro = window.userSubscriptionStatus?.isPro === true;

    // Integrations (WordPress/embed) only for PRO/PREMIUM
    document.getElementById('billing-upgrade-section').style.display = isPro ? 'none' : 'block';
    document.getElementById('integrations-setup-section').style.display = isPro ? 'block' : 'none';

    document.getElementById('upgradeState').classList.toggle('d-none', isPro);
    document.getElementById('noBusinessState').classList.toggle('d-none', !isPro);
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.add('d-none');

    // PRO banner only for paid users
    const banner = document.getElementById('proPlanBanner');
    if (banner) banner.classList.toggle('d-none', !isPro);

    hideLoading();
}

function showCreateBusinessForm() {
    document.getElementById('noBusinessState').classList.add('d-none');
    document.getElementById('createBusinessFormCard').classList.remove('d-none');
}

function hideCreateBusinessForm() {
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('noBusinessState').classList.remove('d-none');
    document.getElementById('createBusinessForm').reset();
}

async function handleCreateBusiness(event) {
    event.preventDefault();
    
    const businessId = document.getElementById('businessId').value;
    const businessName = document.getElementById('businessName').value;
    const description = document.getElementById('businessDescription').value;
    const submitBtn = event.target.querySelector('button[type="submit"]');
    
    submitBtn.disabled = true;
    submitBtn.textContent = 'יוצר...';
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/businesses`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ business_id: businessId, business_name: businessName, description: description })
        });
        
        if (response.ok) {
            const data = await response.json();
            currentBusiness = data;
            showDashboardState();
            document.getElementById('createBusinessForm').reset();
        } else {
            const data = await response.json();
            alert('שגיאה: ' + (data.detail || 'נסה שוב'));
        }
    } catch (error) {
        console.error('Create business error:', error);
        alert('שגיאה בתקשורת עם השרת');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'צור עסק';
    }
}

async function initDashboard() {
    console.log('✅ [12] initDashboard() called. currentBusiness =', currentBusiness);
    // Guard clause: Prevent duplicate initialization
    if (isDashboardInitialized) {
        console.log("Dashboard initialization already in progress or completed. Skipping duplicate call.");
        return;
    }
    isDashboardInitialized = true;

    // Whole function wrapped in try/catch/finally so that NOTHING here can leave
    // the loading overlay stuck, no matter what throws.
    const dashboardContent = document.getElementById('dashboardContent');
    try {
        // STEP 1: Force dashboard container visible FIRST (before any async operations)
        if (dashboardContent) {
            dashboardContent.classList.remove('d-none');
            dashboardContent.style.display = 'block';
        }
        
        // Hide other states
        const noBusinessState = document.getElementById('noBusinessState');
        const createBusinessFormCard = document.getElementById('createBusinessFormCard');
        const upgradeState = document.getElementById('upgradeState');
        
        if (noBusinessState) noBusinessState.classList.add('d-none');
        if (createBusinessFormCard) createBusinessFormCard.classList.add('d-none');
        if (upgradeState) upgradeState.classList.add('d-none');
        
        // Show business name in header
        if (currentBusiness) {
            const nameEl = document.getElementById('businessDisplayName');
            const slugEl = document.getElementById('businessDisplaySlug');
            if (nameEl) nameEl.textContent = `🏢 ${currentBusiness.business_name}`;
            if (slugEl) slugEl.textContent = `מזהה: ${currentBusiness.business_id}`;
            
            // Use currentBusiness.id (UUID) for all API calls
            const BUSINESS_UUID = currentBusiness.id;
            window.currentBusinessId = BUSINESS_UUID;
            console.log('✅ [13] window.currentBusinessId set to:', BUSINESS_UUID);
            
            // Dispatch custom event for widget.js
            const businessReadyEvent = new CustomEvent('conversapay:business-ready', {
                detail: {
                    business_id: BUSINESS_UUID,
                    business_name: currentBusiness.business_name
                }
            });
            document.dispatchEvent(businessReadyEvent);
        }
        
        // Check for session_id from successful payment redirect
        const urlParams = new URLSearchParams(window.location.search);
        const sessionId = urlParams.get('session_id');
        if (sessionId) {
            const banner = document.getElementById('proPlanBanner');
            if (banner) banner.classList.remove('d-none');
            window.history.replaceState({}, document.title, '/dashboard.html');
        }
        
        // STEP 2: Check Pro status and apply overlay if needed (non-blocking)
        console.log('✅ [14] calling checkProStatusForIntegrations()');
        await checkProStatusForIntegrations();
        
        // STEP 3: Update embed code
        console.log('✅ [15] calling updateEmbedCode()');
        updateEmbedCode();
        
        // STEP 4: Load all dashboard data in parallel
        console.log('✅ [16] calling loadAllData()');
        await loadAllData();
        console.log('✅ [17] loadAllData() finished');
        
    } catch (error) {
        console.error('🔴 Error in initDashboard:', error);
    } finally {
        // STEP 5: ALWAYS hide loading and ensure dashboard is visible (absolute guarantee)
        console.log('✅ [18] initDashboard finally block -> hideLoading()');
        hideLoading();
        if (dashboardContent) {
            dashboardContent.classList.remove('d-none');
            dashboardContent.style.display = 'block';
        }
    }
}

function showDashboardState() {
    console.log('✅ [12-pre] showDashboardState() called');
    // Hide billing section, show integrations
    const billingSection = document.getElementById('billing-upgrade-section');
    const integrationsSection = document.getElementById('integrations-setup-section');
    if (billingSection) billingSection.style.display = 'none';
    if (integrationsSection) integrationsSection.style.display = 'block';
    
    // Initialize dashboard with centralized flow.
    // Explicitly catch here too: initDashboard() is async and NOT awaited (this function
    // isn't async), so without this .catch() any error thrown before its own try/catch
    // reaches, becomes an invisible "unhandled promise rejection" — caught by our
    // global safety net above, but logged here as well for clarity.
    initDashboard().catch(error => {
        console.error('🔴 initDashboard() rejected:', error);
        forceUnstickUI('initDashboard rejected: ' + (error?.message || error));
    });
}

// Generic reusable lock overlay — used for any card that should be blurred/locked for free users
function applyLockOverlay(cardElementId, overlayId) {
    const card = document.getElementById(cardElementId);
    if (!card) return;

    // Remove any existing overlay first (avoid duplicates on repeated calls)
    const existing = document.getElementById(overlayId);
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = overlayId;
    overlay.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.75);
        backdrop-filter: blur(5px);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 100;
        border-radius: 12px;
        padding: 30px;
        text-align: center;
        pointer-events: auto;
    `;

    overlay.innerHTML = `
        <div style="font-size: 4rem; margin-bottom: 20px;">🔒</div>
        <h3 style="font-size: 1.3rem; font-weight: 700; color: white; margin-bottom: 12px; direction: rtl;">
            נעול - רכוש PRO או PREMIUM
        </h3>
        <p style="color: rgba(255,255,255,0.9); margin-bottom: 24px; font-size: 1rem; direction: rtl; max-width: 400px;">
            ותקבל את האופציות האלו
        </p>
        <div style="display: flex; gap: 12px; flex-wrap: wrap; justify-content: center;">
            <button onclick="handleUpgradeToPlan('pro', this)" class="btn" style="
                background: linear-gradient(135deg, #00D9FF 0%, #3B82F6 100%);
                color: white;
                padding: 14px 24px;
                font-weight: 700;
                border-radius: 8px;
                border: none;
                cursor: pointer;
                font-size: 1rem;
                direction: rtl;
            ">
                💳 שדרג ל-Pro
            </button>
            <button onclick="handleUpgradeToPlan('premium', this)" class="btn" style="
                background: linear-gradient(135deg, #A855F7 0%, #C084FC 100%);
                color: white;
                padding: 14px 24px;
                font-weight: 700;
                border-radius: 8px;
                border: none;
                cursor: pointer;
                font-size: 1rem;
                direction: rtl;
            ">
                👑 שדרג ל-Premium
            </button>
        </div>
    `;

    // Ensure the card can host an absolutely-positioned overlay, and that
    // the card itself (not just its body) is fully covered edge-to-edge.
    const priorPosition = getComputedStyle(card).position;
    if (priorPosition === 'static') {
        card.style.position = 'relative';
    }
    card.style.overflow = 'hidden';
    card.appendChild(overlay);
}

function removeLockOverlay(overlayId) {
    const existing = document.getElementById(overlayId);
    if (existing) existing.remove();
}

async function checkProStatusForIntegrations() {
    try {
        // Re-fetch profile directly to get the authoritative subscription status.
        // window.userSubscriptionStatus may not yet be set when this runs.
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/payments/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        let isPro = false;
        if (response.ok) {
            const profile = await response.json();
            isPro = profile.plan_type === 'pro' || profile.plan_type === 'premium';
            // Keep window.userSubscriptionStatus in sync
            window.userSubscriptionStatus = {
                isPro,
                planType: profile.plan_type || null
            };
        }

        const lockedCards = [
            { cardId: 'integrationsCard', overlayId: 'integrationLockOverlay' },
            { cardId: 'ordersCard', overlayId: 'ordersLockOverlay' },
            { cardId: 'topProductsCard', overlayId: 'topProductsLockOverlay' }
        ];

        lockedCards.forEach(({ cardId, overlayId }) => {
            removeLockOverlay(overlayId);
            if (!isPro) {
                applyLockOverlay(cardId, overlayId);
            }
        });

        // WhatsApp section: Premium only
        const isPremium = (profile?.plan_type || '').toLowerCase() === 'premium';
        const waSection = document.getElementById('whatsappSection');
        if (waSection) {
            if (isPremium) {
                waSection.classList.remove('d-none');
                loadWhatsAppSettings(profile);
            } else {
                waSection.classList.add('d-none');
            }
        }
    } catch (error) {
        console.error('Error checking Pro status for locked cards:', error);
    }
}
async function checkUserPlan() {
    // No-op: subscription status is handled by checkSubscriptionStatus() in the main auth flow.
    // This function is kept to avoid breaking the window.onload call in dashboard.html.
}

async function checkWebsiteStatus() {
    try {
        const token = ConversaPayAuth.getToken();
        // Use BUSINESS_UUID (the database primary key) for all API calls, not the slug
        const response = await fetch(`${API_BASE_URL}/businesses/${currentBusiness.id}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const business = await response.json();
            const hasWebsite = business.website_url && business.website_url.trim() !== '';
            
            if (!hasWebsite) {
                // Show onboarding card as addition to dashboard
                showWebsiteOnboarding();
            } else {
                // Hide onboarding card for standard dashboard
                const onboardingCard = document.getElementById('websiteOnboardingCard');
                if (onboardingCard) onboardingCard.classList.add('d-none');
            }
        }
    } catch (error) {
        console.error('Error checking website status:', error);
        // Hide onboarding on error
        const onboardingCard = document.getElementById('websiteOnboardingCard');
        if (onboardingCard) onboardingCard.classList.add('d-none');
    }
}

function getSubscriptionTier() {
    const status = window.userSubscriptionStatus;
    if (!status) return 'free';
    // Support both 'pro' and 'premium' plan types
    const planType = (status.planType || '').toLowerCase();
    if (planType === 'premium') return 'premium';
    if (planType === 'pro' || status.isPro) return 'pro';
    return 'free';
}

function showOrdersSection() {
    const tier = getSubscriptionTier();
    const ordersSection = document.querySelectorAll('.card')[2]; // Orders card
    
    if (tier === 'free') {
        // Free tier: Replace orders with upgrade placeholder
        if (ordersSection) {
            ordersSection.classList.remove('d-none');
            ordersSection.innerHTML = `
                <div class="card-header">
                    <h3 class="card-title">🔒 הזמנות ותשלומים</h3>
                </div>
                <div class="card-body" style="text-align:center;padding:40px;">
                    <div style="font-size:4rem;margin-bottom:20px;">💳</div>
                    <h3 style="font-size:1.5rem;font-weight:700;margin-bottom:16px;color:var(--text-primary);">
                        שדרג ל-Pro כדי לראות הזמנות
                    </h3>
                    <p style="color:var(--text-secondary);margin-bottom:32px;max-width:600px;margin-left:auto;margin-right:auto;">
                        גישה להזמנות ולתשלומים דורשת תוכנית Pro או Premium
                    </p>
                    <button onclick="handleUpgradeToPlan('pro', this)" class="btn" style="background:linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-blue) 100%);color:white;padding:12px 20px;font-weight:700;border-radius:8px;border:none;cursor:pointer;">
                        💳 שדרג ל-Pro - 200 ₪/חודש
                    </button>
                </div>
            `;
        }
    } else {
        // Pro/Premium: Show normal orders section
        if (ordersSection) ordersSection.classList.remove('d-none');
    }
}

function showWebsiteOnboarding() {
    // Show onboarding card as an addition to the dashboard
    const onboardingCard = document.getElementById('websiteOnboardingCard');
    if (onboardingCard) {
        onboardingCard.classList.remove('d-none');
        
        // Set dynamic link to site builder - use currentBusiness.id (UUID) for API consistency
        const token = ConversaPayAuth.getToken();
        const siteBuilderUrl = `http://localhost:8001/frontend/index.html?business_id=${currentBusiness.id}&token=${token}`;
        const generateBtn = document.getElementById('generateSiteBtn');
        if (generateBtn) {
            generateBtn.href = siteBuilderUrl;
        }
    }
    
    // Handle orders section based on tier (only updates the orders card, not the whole layout)
    showOrdersSection();
}

function showStandardDashboard() {
    // Hide onboarding card
    const onboardingCard = document.getElementById('websiteOnboardingCard');
    if (onboardingCard) onboardingCard.classList.add('d-none');
    
    // Handle orders section based on tier (only updates the orders card, not the whole layout)
    showOrdersSection();
}

// ============================================
// Integrations
// ============================================

function updateEmbedCode() {
    if (!currentBusiness) return;
    
    const embedCode = `<!-- ConversaPay AI Chatbot -->
<script>
  window.ConversaPayWidgetConfig = { business_id: "${currentBusiness.id}" };
</script>
<script src="${window.location.origin}/frontend/js/widget.js" defer></script>`;
    
    const codeElement = document.getElementById('embedCodeSnippet');
    if (codeElement) {
        codeElement.textContent = embedCode;
    }
}

function downloadWordPressPlugin() {
    if (!currentBusiness) { alert('נא ליצור עסק תחילה'); return; }
    window.location.href = `/frontend/html/setup-guide.html?business_id=${currentBusiness.business_id}&tab=wordpress`;
}

function copyEmbedCode() {
    if (!currentBusiness) { alert('נא ליצור עסק תחילה'); return; }
    window.location.href = `/frontend/html/setup-guide.html?business_id=${currentBusiness.business_id}&tab=html`;
}

async function loadAllData() {
    const tier = getSubscriptionTier();
    
    try {
        // Always load products and analytics for all tiers
        await Promise.all([
            loadProducts(),
            loadAnalytics()
        ]);
        
        // Only load orders for Pro and Premium tiers
        if (tier !== 'free') {
            await loadOrders();
        }
    } catch (error) {
        console.error('Error in loadAllData:', error);
        // Don't throw - allow UI to proceed with empty data
    }
}

// ============================================
// Analytics
// ============================================

let revenueChart = null;
let ordersChart = null;

async function loadAnalytics() {
    if (!currentBusiness) return;
    
    const days = document.getElementById('analyticsPeriod')?.value || 30;
    const token = ConversaPayAuth.getToken();
    
    try {
        // Load main analytics — use currentBusiness.id (UUID), not the slug
        const analyticsPromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.id}/analytics`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null);
        
        // Load revenue data
        const revenuePromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.id}/revenue?days=${days}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null);
        
        // Load order analytics
        const ordersPromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.id}/orders?days=${days}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null);
        
        const [analytics, revenueData, ordersData] = await Promise.all([analyticsPromise, revenuePromise, ordersPromise]);
        
        if (analytics) {
            updateKPICards(analytics);
        }
        
        if (revenueData) {
            renderRevenueChart(revenueData);
        }
        
        if (ordersData) {
            renderOrdersChart(ordersData);
        }
        
        // Load top products
        await loadTopProducts();
        
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

function updateKPICards(analytics) {
    if (!analytics) {
        // Set default zero values if analytics data is missing
        const revenueEl = document.getElementById('kpiRevenue');
        const conversionEl = document.getElementById('kpiConversion');
        const conversionBar = document.getElementById('conversionBar');
        const aovEl = document.getElementById('kpiAOV');
        const sessionsEl = document.getElementById('kpiSessions');
        
        if (revenueEl) revenueEl.textContent = '₪0';
        if (conversionEl) conversionEl.textContent = '0%';
        if (conversionBar) conversionBar.style.width = '0%';
        if (aovEl) aovEl.textContent = '₪0';
        if (sessionsEl) sessionsEl.textContent = '0';
        return;
    }
    
    // Revenue
    const revenueEl = document.getElementById('kpiRevenue');
    if (revenueEl) {
        const revenue = analytics.total_revenue || 0;
        revenueEl.textContent = `₪${revenue.toFixed(2)}`;
    }
    
    // Conversion Rate
    const conversionEl = document.getElementById('kpiConversion');
    const conversionBar = document.getElementById('conversionBar');
    if (conversionEl && conversionBar) {
        const rate = analytics.conversion_rate || 0;
        conversionEl.textContent = `${rate.toFixed(1)}%`;
        conversionBar.style.width = `${Math.min(rate, 100)}%`;
        
        // Color based on performance (cyan for good, purple for medium, red for low)
        if (rate >= 30) {
            conversionBar.style.background = 'linear-gradient(90deg, #00D9FF, #3B82F6)';
        } else if (rate >= 15) {
            conversionBar.style.background = 'linear-gradient(90deg, #A855F7, #C084FC)';
        } else {
            conversionBar.style.background = 'linear-gradient(90deg, #EF4444, #F87171)';
        }
    }
    
    // Average Order Value
    const aovEl = document.getElementById('kpiAOV');
    if (aovEl) {
        const aov = analytics.average_order_value || 0;
        aovEl.textContent = `₪${aov.toFixed(2)}`;
    }
    
    // Fix the English subtitle
    const aovSub = aovEl?.closest('.stat-card')?.querySelector('.stat-sub');
    if (aovSub) {
        aovSub.textContent = 'ערך הזמנה ממוצע';
    }
    
    // Unique Sessions
    const sessionsEl = document.getElementById('kpiSessions');
    if (sessionsEl) {
        sessionsEl.textContent = analytics.unique_chat_sessions || 0;
    }
}

function renderRevenueChart(revenueData) {
    const canvas = document.getElementById('revenueChart');
    if (!canvas) return;
    
    try {
        // Handle empty or missing data
        const revenueByDay = revenueData?.revenue_by_day || [];
        if (revenueByDay.length === 0) {
            // Show empty chart with zero data
            const ctx = canvas.getContext('2d');
            if (revenueChart) {
                revenueChart.destroy();
            }
            
            revenueChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['אין נתונים'],
                    datasets: [{
                        label: 'הכנסות (₪)',
                        data: [0],
                        borderColor: '#A855F7',
                        backgroundColor: 'rgba(168, 85, 247, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 3,
                        pointBackgroundColor: '#A855F7',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            rtl: true,
                            textDirection: 'rtl',
                            callbacks: {
                                label: function(context) {
                                    return `₪${context.parsed.y.toFixed(2)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function(value) {
                                    return `₪${value}`;
                                }
                            }
                        },
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        }
                    }
                }
            });
            return;
        }
        
        const ctx = canvas.getContext('2d');
        
        // Destroy existing chart
        if (revenueChart) {
            revenueChart.destroy();
        }
        
        const labels = revenueByDay.map(d => {
            const date = new Date(d.date);
            return date.toLocaleDateString('he-IL', { month: 'short', day: 'numeric' });
        });
        
        const data = revenueByDay.map(d => d.revenue || 0);
        
        revenueChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'הכנסות (₪)',
                    data: data,
                    borderColor: '#A855F7',
                    backgroundColor: 'rgba(168, 85, 247, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointBackgroundColor: '#A855F7',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        rtl: true,
                        textDirection: 'rtl',
                        callbacks: {
                            label: function(context) {
                                return `₪${context.parsed.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return `₪${value}`;
                            }
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error rendering revenue chart:', error);
        // Show empty chart on error
        const ctx = canvas.getContext('2d');
        if (revenueChart) {
            revenueChart.destroy();
        }
        revenueChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['שגיאה בטעינה'],
                datasets: [{
                    label: 'הכנסות (₪)',
                    data: [0],
                    borderColor: '#EF4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
}

function renderOrdersChart(ordersData) {
    const canvas = document.getElementById('ordersChart');
    if (!canvas) return;
    
    try {
        // Handle empty or missing data
        const ordersByStatus = ordersData?.orders_by_status || {};
        const labels = Object.keys(ordersByStatus).map(s => getStatusText(s));
        const data = Object.values(ordersByStatus);
        
        // If no data, show empty chart
        if (labels.length === 0) {
            labels.push('אין נתונים');
            data.push(0);
        }
        
        const colors = Object.keys(ordersByStatus).map(s => {
            const colorsMap = {
                'pending': '#f59e0b',
                'paid': '#10b981',
                'processing': '#3b82f6',
                'shipped': '#8b5cf6',
                'delivered': '#10b981',
                'canceled': '#ef4444',
                'refunded': '#ef4444',
                'failed': '#ef4444'
            };
            return colorsMap[s] || '#64748b';
        });
        
        // If no data, add default color
        if (colors.length === 0) {
            colors.push('#64748b');
        }
        
        const ctx = canvas.getContext('2d');
        
        // Destroy existing chart
        if (ordersChart) {
            ordersChart.destroy();
        }
        
        ordersChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'מספר הזמנות',
                    data: data,
                    backgroundColor: colors,
                    borderRadius: 8,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        rtl: true,
                        textDirection: 'rtl'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error rendering orders chart:', error);
        // Show empty chart on error
        const ctx = canvas.getContext('2d');
        if (ordersChart) {
            ordersChart.destroy();
        }
        ordersChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['שגיאה בטעינה'],
                datasets: [{
                    label: 'מספר הזמנות',
                    data: [0],
                    backgroundColor: ['#EF4444'],
                    borderRadius: 8,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
}

async function loadTopProducts() {
    if (!currentBusiness) return;
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.id}/analytics`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const analytics = await response.json();
            renderTopProducts(analytics.top_selling_products || []);
        }
    } catch (error) {
        console.error('Error loading top products:', error);
    }
}

function renderTopProducts(products) {
    const noProducts = document.getElementById('noProductsData');
    const tableContainer = document.getElementById('topProductsTableContainer');
    const tbody = document.getElementById('topProductsTableBody');
    
    if (!products || products.length === 0) {
        noProducts.classList.remove('d-none');
        tableContainer.classList.add('d-none');
        return;
    }
    
    noProducts.classList.add('d-none');
    tableContainer.classList.remove('d-none');
    
    tbody.innerHTML = products.map((product, index) => `
        <tr>
            <td><strong>${index + 1}</strong></td>
            <td><strong>${escapeHtml(product.name)}</strong></td>
            <td><code>${product.item_key}</code></td>
            <td><span class="badge badge-success">${product.total_quantity}</span></td>
            <td>${product.order_count}</td>
        </tr>
    `).join('');
}

// ============================================
// Orders
// ============================================

async function loadOrders() {
    // Force use of window.currentBusinessId - the verified global from conversapay:business-ready event
    const businessId = window.currentBusinessId;
    
    // Block execution if UUID is missing or still set to non-UUID fallback
    if (!businessId || businessId === 'conversapay') {
        console.warn('loadOrders blocked: businessId is missing or invalid', businessId);
        return;
    }
    
    try {
        const token = ConversaPayAuth.getToken();
        const statusFilter = document.getElementById('statusFilter')?.value || '';
        
        let url = `${API_BASE_URL}/orders?business_id=${encodeURIComponent(businessId)}&limit=50`;
        if (statusFilter) {
            url += `&status_filter=${encodeURIComponent(statusFilter)}`;
        }
        
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const orders = await response.json();
            renderOrders(orders);
            updateAnalytics(orders);
        } else {
            // Handle HTTP errors (including 500) with UI notice instead of silent failure
            const errorData = await response.json().catch(() => ({}));
            const errorMessage = errorData.detail || `שגיאה בטעינת ההזמנות (${response.status})`;
            
            console.error('Failed to load orders:', response.status, errorMessage);
            
            // Display notice in UI
            const noOrders = document.getElementById('noOrders');
            const tableContainer = document.getElementById('ordersTableContainer');
            const tbody = document.getElementById('ordersTableBody');
            
            if (noOrders) {
                noOrders.classList.remove('d-none');
                noOrders.innerHTML = `<div style="text-align:center;padding:20px;color:#EF4444;">⚠️ ${errorMessage}</div>`;
            }
            if (tableContainer) tableContainer.classList.add('d-none');
            if (tbody) tbody.innerHTML = '';
        }
    } catch (error) {
        // Handle network errors with UI notice
        console.error('Error loading orders:', error);
        
        const noOrders = document.getElementById('noOrders');
        if (noOrders) {
            noOrders.classList.remove('d-none');
            noOrders.innerHTML = '<div style="text-align:center;padding:20px;color:#EF4444;">⚠️ שגיאה בתקשורת עם השרת</div>';
        }
    }
}

function renderOrders(orders) {
    const tbody = document.getElementById('ordersTableBody');
    const noOrders = document.getElementById('noOrders');
    const tableContainer = document.getElementById('ordersTableContainer');
    
    if (!orders || orders.length === 0) {
        noOrders.classList.remove('d-none');
        tableContainer.classList.add('d-none');
        return;
    }
    
    noOrders.classList.add('d-none');
    tableContainer.classList.remove('d-none');
    
    tbody.innerHTML = orders.map((order, index) => {
        const itemsList = order.items && order.items.length > 0
            ? order.items.map(item => `<li>• ${item.name || item.item_key} × ${item.quantity || 1} - ₪${(item.price || 0).toFixed(2)}</li>`).join('')
            : '<li style="color:#9CA3AF;">אין פירוט פריטים</li>';
        
        const customerName = order.customer_info?.name || order.customer_info?.email || 'לקוח אנונימי';
        const orderDate = new Date(order.created_at).toLocaleDateString('he-IL', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
        
        const badgeClass = getStatusBadgeClass(order.status);
        const statusText = getStatusText(order.status);
        
        return `
            <tr>
                <td>${index + 1}</td>
                <td><code>${order.order_number || order.id?.substring(0, 8) || 'N/A'}</code></td>
                <td><strong>${escapeHtml(customerName)}</strong></td>
                <td>
                    <ul class="order-items-list">${itemsList}</ul>
                </td>
                <td><strong>₪${(order.total || 0).toFixed(2)}</strong></td>
                <td><span class="badge badge-${badgeClass}">${statusText}</span></td>
                <td style="font-size:0.85rem;color:#9CA3AF;">${orderDate}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="viewOrderDetails('${order.id}')">👁️ פרטים</button>
                </td>
            </tr>
        `;
    }).join('');
}

function updateAnalytics(orders) {
    const revenueEl = document.getElementById('kpiRevenue');
    const conversionEl = document.getElementById('kpiConversion');
    const conversionBar = document.getElementById('conversionBar');
    const aovEl = document.getElementById('kpiAOV');
    const sessionsEl = document.getElementById('kpiSessions');
    
    if (!orders || orders.length === 0) {
        if (revenueEl) revenueEl.textContent = '₪0';
        if (aovEl) aovEl.textContent = '₪0';
        if (sessionsEl) sessionsEl.textContent = '0';
        if (conversionEl) conversionEl.textContent = '0%';
        if (conversionBar) conversionBar.style.width = '0%';
        return;
    }
    
    let totalRevenue = 0;
    let pendingCount = 0;
    let pendingValue = 0;
    let completedCount = 0;
    let failedCount = 0;
    let totalSessions = 0;
    
    orders.forEach(order => {
        const total = order.total || 0;
        const status = order.status;
        
        if (status === 'paid' || status === 'delivered') {
            totalRevenue += total;
            completedCount++;
        } else if (status === 'pending' || status === 'processing') {
            pendingCount++;
            pendingValue += total;
        } else if (status === 'canceled' || status === 'refunded' || status === 'failed') {
            failedCount++;
        }
        
        // Count unique sessions (simplified - using order count as proxy)
        totalSessions++;
    });
    
    const aov = orders.length > 0 ? totalRevenue / orders.length : 0;
    const conversionRate = totalSessions > 0 ? ((completedCount / totalSessions) * 100) : 0;
    
    if (revenueEl) revenueEl.textContent = `₪${totalRevenue.toFixed(2)}`;
    if (aovEl) aovEl.textContent = `₪${aov.toFixed(2)}`;
    if (sessionsEl) sessionsEl.textContent = totalSessions.toString();
    if (conversionEl) conversionEl.textContent = `${conversionRate.toFixed(1)}%`;
    if (conversionBar) conversionBar.style.width = `${Math.min(conversionRate, 100)}%`;
}

async function viewOrderDetails(orderId) {
    if (!currentBusiness || !orderId) return;
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/orders/${orderId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const order = await response.json();
            const customerName = order.customer_info?.name || order.customer_info?.email || 'לקוח אנונימי';
            const statusText = getStatusText(order.status);
            
            const itemsDetail = order.items && order.items.length > 0
                ? order.items.map(item => 
                    `• ${item.name || item.item_key} - ₪${(item.price || 0).toFixed(2)} × ${item.quantity || 1}`
                  ).join('\n')
                : 'אין פירוט';
            
            alert(
                `📋 פרטי הזמנה\n` +
                `─────────────────\n` +
                `מספר: ${order.order_number}\n` +
                `לקוח: ${customerName}\n` +
                `סטטוס: ${statusText}\n` +
                `סכום: ₪${(order.total || 0).toFixed(2)}\n` +
                `תאריך: ${new Date(order.created_at).toLocaleDateString('he-IL', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })}\n` +
                `─────────────────\n` +
                `פריטים:\n${itemsDetail}`
            );
        } else {
            alert('שגיאה בטעינת פרטי ההזמנה');
        }
    } catch (error) {
        console.error('Error viewing order:', error);
        alert('שגיאה בתקשורת עם השרת');
    }
}

// ============================================
// Status Helpers
// ============================================

function getStatusBadgeClass(status) {
    const classes = {
        'pending': 'warning',
        'paid': 'success',
        'processing': 'info',
        'shipped': 'primary',
        'delivered': 'success',
        'canceled': 'danger',
        'refunded': 'danger',
        'failed': 'danger'
    };
    return classes[status] || 'secondary';
}

function getStatusText(status) {
    const texts = {
        'pending': 'ממתין לתשלום',
        'paid': 'שולם ✓',
        'processing': 'בטיפול',
        'shipped': 'נשלח',
        'delivered': 'נמסר',
        'canceled': 'בוטל',
        'refunded': 'הוחזר',
        'failed': 'נכשל'
    };
    return texts[status] || status;
}

// ============================================
// Products
// ============================================

function showAddProductForm() {
    document.getElementById('productFormContainer').classList.remove('d-none');
    document.getElementById('productFormTitle').textContent = 'הוסף מוצר חדש';
    document.getElementById('productForm').reset();
    document.getElementById('productId').value = '';
    document.getElementById('productItemKey').disabled = false;
}

function hideProductForm() {
    document.getElementById('productFormContainer').classList.add('d-none');
}

async function handleSaveProduct(event) {
    event.preventDefault();
    if (!currentBusiness) { alert('נא לבחור עסק תחילה'); return; }
    
    const productId = document.getElementById('productId').value;
    const itemKey = document.getElementById('productItemKey').value;
    const name = document.getElementById('productName').value;
    const description = document.getElementById('productDescription').value;
    const price = parseFloat(document.getElementById('productPrice').value);
    const imageUrl = document.getElementById('productImageUrl').value;
    const isActive = document.getElementById('productIsActive').checked;
    
    const submitBtn = document.getElementById('productSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'שומר...';
    
    try {
        const productData = {
            business_id: currentBusiness.id,
            item_key: itemKey, name,
            description: description || null,
            price: price,
            image_url: imageUrl || null,
            is_active: isActive
        };
        
        const method = productId ? 'PUT' : 'POST';
        const url = productId ? `${API_BASE_URL}/products/${productId}` : `${API_BASE_URL}/products`;
        const token = ConversaPayAuth.getToken();
        
        const response = await fetch(url, {
            method, headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(productData)
        });
        
        if (response.ok) {
            hideProductForm();
            loadProducts();
        } else {
            const data = await response.json();
            alert('שגיאה: ' + (data.detail || 'נסה שוב'));
        }
    } catch (error) {
        console.error('Save product error:', error);
        alert('שגיאה בתקשורת עם השרת');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = productId ? 'עדכן מוצר' : 'שמור מוצר';
    }
}

async function loadProducts() {
    if (!currentBusiness) return;
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/products?business_id=${currentBusiness.id}&active_only=false`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const products = await response.json();
            const noProducts = document.getElementById('noProducts');
            const productsGrid = document.getElementById('productsGrid');
            
            if (products.length === 0) {
                noProducts.classList.remove('d-none');
                productsGrid.classList.add('d-none');
            } else {
                noProducts.classList.add('d-none');
                productsGrid.classList.remove('d-none');
                
                productsGrid.innerHTML = products.map(product => `
                    <div class="card" style="margin-bottom:16px;">
                        <div class="card-body">
                            <div class="d-flex justify-between align-start" style="gap:20px;">
                                <div style="flex: 0 0 80px; height:80px; background:${product.image_url ? 'transparent' : 'rgba(168, 85, 247, 0.1)'}; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:2.5rem; overflow:hidden; border: 1px solid rgba(255, 255, 255, 0.1);">
                                    ${product.image_url ? `<img src="${product.image_url}" alt="${product.name}" style="width:100%;height:100%;object-fit:cover;">` : '📦'}
                                </div>
                                <div style="flex:1;">
                                    <div class="d-flex justify-between" style="margin-bottom:8px;">
                                        <div>
                                            <h4 style="margin:0;font-size:1rem;">${escapeHtml(product.name)}</h4>
                                    <code style="font-size:0.8rem;color:#9CA3AF;">${product.item_key}</code>
                                        </div>
                                        <div style="font-size:1.2rem;font-weight:700;color:#A855F7;">₪${(product.price || 0).toFixed(2)}</div>
                                    </div>
                                    ${product.description ? `<p style="color:#9CA3AF;font-size:0.9rem;margin:4px 0 8px;">${escapeHtml(product.description)}</p>` : ''}
                                    <div class="d-flex justify-between align-center">
                                        <span class="badge ${product.is_active ? 'badge-success' : 'badge-danger'}">
                                            ${product.is_active ? '✓ פעיל' : '✗ לא פעיל'}
                                        </span>
                                        <div class="d-flex gap-2">
                                            <button class="btn btn-sm btn-outline" onclick="editProduct('${product.id}')">ערוך</button>
                                            <button class="btn btn-sm btn-danger" onclick="deleteProduct('${product.id}')">מחק</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Error loading products:', error);
    }
}

async function editProduct(productId) {
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/products/${productId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const product = await response.json();
            document.getElementById('productId').value = product.id;
            document.getElementById('productItemKey').value = product.item_key;
            document.getElementById('productName').value = product.name;
            document.getElementById('productDescription').value = product.description || '';
            document.getElementById('productPrice').value = product.price;
            document.getElementById('productImageUrl').value = product.image_url || '';
            document.getElementById('productIsActive').checked = product.is_active;
            
            document.getElementById('productFormTitle').textContent = 'ערוך מוצר';
            document.getElementById('productSubmitBtn').textContent = 'עדכן מוצר';
            document.getElementById('productFormContainer').classList.remove('d-none');
            document.getElementById('productItemKey').disabled = true;
            document.getElementById('productFormContainer').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            alert('שגיאה בטעינת פרטי המוצר');
        }
    } catch (error) {
        console.error('Error editing product:', error);
        alert('שגיאה בתקשורת עם השרת');
    }
}

async function deleteProduct(productId) {
    if (!confirm('האם אתה בטוח שברצונך למחוק מוצר זה?')) return;
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/products/${productId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            loadProducts();
        } else {
            alert('שגיאה במחיקת מוצר');
        }
    } catch (error) {
        console.error('Delete product error:', error);
        alert('שגיאה בתקשורת עם השרת');
    }
}

// ============================================
// Utility Functions
// ============================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// WhatsApp Integration (Premium)
// ============================================

function loadWhatsAppSettings(profile) {
    if (!profile) return;
    const phoneId = document.getElementById('waPhoneNumberId');
    const token = document.getElementById('waAccessToken');
    const verify = document.getElementById('waVerifyToken');
    if (phoneId) phoneId.value = profile.whatsapp_phone_number_id || '';
    if (token) token.value = profile.whatsapp_access_token || '';
    if (verify) verify.value = profile.whatsapp_verify_token || '';
    if (profile.whatsapp_verify_token) showWebhookUrl(profile.whatsapp_verify_token);
}

function showWebhookUrl(verifyToken) {
    const urlEl = document.getElementById('waWebhookUrl');
    const copyBtn = document.getElementById('waCopyWebhook');
    if (!urlEl) return;
    const webhookUrl = `${window.location.origin}/api/v1/whatsapp/webhook`;
    urlEl.textContent = `Webhook URL: ${webhookUrl}`;
    urlEl.style.display = 'block';
    if (copyBtn) copyBtn.style.display = 'inline-flex';
}

async function copyWebhookUrl() {
    const url = `${window.location.origin}/api/v1/whatsapp/webhook`;
    await navigator.clipboard.writeText(url).catch(() => {});
    const btn = document.getElementById('waCopyWebhook');
    if (btn) { btn.textContent = '✓ הועתק!'; setTimeout(() => btn.textContent = '📋 העתק Webhook URL', 2000); }
}

async function handleSaveWhatsApp(event) {
    event.preventDefault();
    const phoneId = document.getElementById('waPhoneNumberId').value.trim();
    const accessToken = document.getElementById('waAccessToken').value.trim();
    const verifyToken = document.getElementById('waVerifyToken').value.trim();
    const statusEl = document.getElementById('waStatus');
    const submitBtn = event.target.querySelector('button[type="submit"]');

    if (!phoneId || !accessToken || !verifyToken) {
        statusEl.style.display = 'block';
        statusEl.innerHTML = '<span style="color:#EF4444;">⚠️ יש למלא את כל השדות</span>';
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'שומר...';

    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/auth/whatsapp-settings`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                whatsapp_phone_number_id: phoneId,
                whatsapp_access_token: accessToken,
                whatsapp_verify_token: verifyToken
            })
        });

        if (response.ok) {
            statusEl.style.display = 'block';
            statusEl.innerHTML = '<span style="color:#10B981;">✅ הגדרות WhatsApp נשמרו בהצלחה!</span>';
            showWebhookUrl(verifyToken);
        } else {
            const data = await response.json();
            statusEl.style.display = 'block';
            statusEl.innerHTML = `<span style="color:#EF4444;">שגיאה: ${data.detail || 'נסה שוב'}</span>`;
        }
    } catch (error) {
        statusEl.style.display = 'block';
        statusEl.innerHTML = '<span style="color:#EF4444;">שגיאה בתקשורת עם השרת</span>';
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '💾 שמור הגדרות WhatsApp';
    }
}

// ============================================
// Auto-refresh
// ============================================

setInterval(() => {
    if (currentBusiness && ConversaPayAuth.getToken()) {
        loadOrders();
    }
}, 30000);