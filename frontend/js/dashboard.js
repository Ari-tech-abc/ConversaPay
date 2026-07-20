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

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
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
    const token = ConversaPayAuth.getToken();
    if (token) {
        // Show loading while checking auth and subscription
        showLoading();
        
        fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(response => {
            if (response.ok) return response.json();
            ConversaPayAuth.logout();
            return null;
        })
        .then(data => {
            if (data) {
                currentUser = data;
                // Check subscription status first
                checkSubscriptionStatus();
            }
        })
        .catch(error => {
            console.error('Auth check error:', error);
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
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/payments/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const profile = await response.json();
            const isPro = profile.is_pro || false;
            
            // Always load businesses for all users (free, pro, premium)
            await loadUserBusinesses();
            
            // Store subscription status for later use
            window.userSubscriptionStatus = {
                isPro: isPro,
                planType: profile.plan_type || null
            };
        } else {
            // If profile check fails, still load dashboard as free user
            await loadUserBusinesses();
            window.userSubscriptionStatus = {
                isPro: false,
                planType: null
            };
        }
    } catch (error) {
        console.error('Error checking subscription:', error);
        // Load dashboard as free user on error
        await loadUserBusinesses();
        window.userSubscriptionStatus = {
            isPro: false,
            planType: null
        };
    }
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

async function handleUpgradeToPlan(planType) {
    const btnId = planType === 'pro' ? 'upgradeToProBtn' : 'upgradeToPremiumBtn';
    const btn = document.getElementById(btnId);
    const planName = planType === 'pro' ? 'Pro' : 'Premium';
    const planPrice = planType === 'pro' ? '200 ₪' : '350 ₪';
    
    btn.disabled = true;
    btn.textContent = 'מפנה לתשלום...';
    
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
        btn.disabled = false;
        btn.textContent = `💳 שדרג ל-${planName} - ${planPrice}`;
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
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/businesses`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const businesses = await response.json();
            
            if (businesses.length === 0) {
                // State A: No business - show empty state
                showNoBusinessState();
            } else {
                // State B: Has business - auto-bind to first one
                currentBusiness = businesses[0];
                showDashboardState();
            }
        }
    } catch (error) {
        console.error('Error loading businesses:', error);
    }
}

function showNoBusinessState() {
    // Hide billing section, show integrations for Pro users
    document.getElementById('billing-upgrade-section').style.display = 'none';
    document.getElementById('integrations-setup-section').style.display = 'block';
    
    // Hide upgrade state and show no-business state for Pro users
    document.getElementById('upgradeState').classList.add('d-none');
    document.getElementById('noBusinessState').classList.remove('d-none');
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.add('d-none');
    
    // Show pro plan banner for Pro users
    const banner = document.getElementById('proPlanBanner');
    if (banner) banner.classList.remove('d-none');
    
    // Hide loading
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

function showDashboardState() {
    // Hide billing section, show integrations
    document.getElementById('billing-upgrade-section').style.display = 'none';
    document.getElementById('integrations-setup-section').style.display = 'block';
    
    // Hide empty state, show dashboard
    document.getElementById('noBusinessState').classList.add('d-none');
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.remove('d-none');
    
    // Show business name in header
    document.getElementById('businessDisplayName').textContent = `🏢 ${currentBusiness.business_name}`;
    document.getElementById('businessDisplaySlug').textContent = `מזהה: ${currentBusiness.business_id}`;
    
    // Use currentBusiness.id (UUID) for all API calls - this is the real database primary key
    const BUSINESS_UUID = currentBusiness.id;
    const BUSINESS_SLUG = currentBusiness.business_id || BUSINESS_UUID;
    
    // Set window.currentBusinessId for widget.js fallback - MUST use the database UUID, not the slug
    window.currentBusinessId = BUSINESS_UUID;
    
    // Dispatch custom event for widget.js to listen for - MUST pass the authentic UUID
    const businessReadyEvent = new CustomEvent('conversapay:business-ready', {
        detail: {
            business_id: BUSINESS_UUID,
            business_name: currentBusiness.business_name
        }
    });
    document.dispatchEvent(businessReadyEvent);
    
    // Check for session_id from successful payment redirect
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    if (sessionId) {
        const banner = document.getElementById('proPlanBanner');
        if (banner) banner.classList.remove('d-none');
        window.history.replaceState({}, document.title, '/dashboard.html');
    }
    
    // Check Pro status to determine integrations visibility
    checkProStatusForIntegrations();
    
    // Update embed code with actual business_id
    updateEmbedCode();
    
    // Check if business has a website - show onboarding if not
    checkWebsiteStatus();
}

async function checkProStatusForIntegrations() {
    try {
        const isPro = window.userSubscriptionStatus?.isPro || false;
        
        const integrationsSection = document.getElementById('integrationsCard');
        if (!integrationsSection) return;
        
        if (!isPro) {
            // Free user: Replace integrations with 2-tier upgrade prompt
            integrationsSection.innerHTML = `
                <div class="card-header">
                    <h3 class="card-title">🔒 חיבור לאתר שלך</h3>
                </div>
                <div class="card-body" style="text-align:center;padding:40px;">
                    <div style="font-size:4rem;margin-bottom:20px;">⭐</div>
                    <h3 style="font-size:1.5rem;font-weight:700;margin-bottom:16px;color:var(--text-primary);">
                        שדרג את התוכנית שלך
                    </h3>
                    <p style="color:var(--text-secondary);margin-bottom:32px;max-width:600px;margin-left:auto;margin-right:auto;">
                        בחר את המסלול המתאים וקבל גישה להטמעות ולכלי פיתוח מתקדמים
                    </p>
                    
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;text-align:right;direction:rtl;">
                        <!-- Pro Plan -->
                        <div style="background:rgba(255,255,255,0.05);padding:24px;border-radius:12px;border:2px solid var(--accent-cyan);">
                            <h4 style="color:var(--accent-cyan);font-size:1.2rem;font-weight:700;margin-bottom:12px;">Pro Plan</h4>
                            <div style="font-size:2rem;font-weight:800;color:white;margin-bottom:16px;">200 ₪<span style="font-size:0.9rem;opacity:0.7;">/חודש</span></div>
                            <ul style="list-style:none;padding:0;margin-bottom:20px;text-align:right;">
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ ווידג'ט צף לכל אתר</li>
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ תוסף וורדפרס</li>
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ אנליטיקות בסיסיות</li>
                            </ul>
                            <button onclick="handleUpgradeToPlan('pro')" class="btn" style="width:100%;background:linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-blue) 100%);color:white;padding:12px 20px;font-weight:700;border-radius:8px;border:none;cursor:pointer;">
                                💳 שדרג ל-Pro
                            </button>
                        </div>
                        
                        <!-- Premium Plan -->
                        <div style="background:rgba(255,255,255,0.05);padding:24px;border-radius:12px;border:2px solid var(--accent-purple);">
                            <h4 style="color:var(--accent-purple);font-size:1.2rem;font-weight:700;margin-bottom:12px;">Premium Plan</h4>
                            <div style="font-size:2rem;font-weight:800;color:white;margin-bottom:16px;">350 ₪<span style="font-size:0.9rem;opacity:0.7;">/חודש</span></div>
                            <ul style="list-style:none;padding:0;margin-bottom:20px;text-align:right;">
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ כל תכונות Pro</li>
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ נפח שיחות גבוה יותר</li>
                                <li style="padding:6px 0;color:var(--text-secondary);">✓ תמיכה מועדפת</li>
                            </ul>
                            <button onclick="handleUpgradeToPlan('premium')" class="btn" style="width:100%;background:linear-gradient(135deg, var(--accent-purple) 0%, var(--accent-blue) 100%);color:white;padding:12px 20px;font-weight:700;border-radius:8px;border:none;cursor:pointer;">
                                💳 שדרג ל-Premium
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error checking Pro status for integrations:', error);
    }
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
                // Show onboarding card, hide standard dashboard
                showWebsiteOnboarding();
            } else {
                // Show standard dashboard
                showStandardDashboard();
            }
        } else {
            // Default to standard dashboard on error
            showStandardDashboard();
        }
    } catch (error) {
        console.error('Error checking website status:', error);
        // Default to standard dashboard on error
        showStandardDashboard();
    }
}

function getSubscriptionTier() {
    const status = window.userSubscriptionStatus;
    if (!status) return 'free';
    if (status.planType === 'premium') return 'premium';
    if (status.isPro) return 'pro';
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
                    <button onclick="handleUpgradeToPlan('pro')" class="btn" style="background:linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-blue) 100%);color:white;padding:12px 20px;font-weight:700;border-radius:8px;border:none;cursor:pointer;">
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
    // Show standard dashboard sections (they may be hidden by default in HTML)
    const analyticsSection = document.querySelector('.stats-grid');
    const chartsSection = document.querySelectorAll('.card')[1]; // Charts card
    const productsSection = document.querySelectorAll('.card')[3]; // Products card
    
    if (analyticsSection) analyticsSection.classList.remove('d-none');
    if (chartsSection) chartsSection.classList.remove('d-none');
    if (productsSection) productsSection.classList.remove('d-none');
    
    // Handle orders section based on tier
    showOrdersSection();
    
    // Load dashboard data (orders will be skipped for free users)
    loadAllData();
    
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
}

function showStandardDashboard() {
    // Hide onboarding card
    const onboardingCard = document.getElementById('websiteOnboardingCard');
    if (onboardingCard) onboardingCard.classList.add('d-none');
    
    // Show standard analytics sections
    const analyticsSection = document.querySelector('.stats-grid');
    const chartsSection = document.querySelectorAll('.card')[1];
    const productsSection = document.querySelectorAll('.card')[3];
    
    if (analyticsSection) analyticsSection.classList.remove('d-none');
    if (chartsSection) chartsSection.classList.remove('d-none');
    if (productsSection) productsSection.classList.remove('d-none');
    
    // Handle orders section based on tier
    showOrdersSection();
    
    // Load all data (orders will be skipped for free users)
    loadAllData();
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

async function downloadWordPressPlugin() {
    if (!currentBusiness) {
        alert('נא ליצור עסק תחילה');
        return;
    }
    
    const btn = document.getElementById('downloadWordPressPlugin');
    btn.disabled = true;
    btn.textContent = 'מוריד...';
    
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/payments/wordpress-plugin/${currentBusiness.business_id}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            // Create download link for PHP file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `conversapay-chat-${currentBusiness.business_id}.php`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            // Show instructions after download
            setTimeout(() => {
                alert('📥 התוסף הורד בהצלחה!\n\n' +
                      'הוראות התקנה:\n' +
                      '1. שמור את הקובץ conversapay-chat.php\n' +
                      '2. העלה אותו לתיקיית wp-content/plugins/ בשרת ה-WordPress\n' +
                      '3. הפעל את התוסף בלוח הבקרה של וורדפרס\n' +
                      '4. עבור להגדרות התוסף והכנס את Business ID: ' + currentBusiness.business_id + '\n\n' +
'למדריך מלא: https://conversapay.org/docs/wordpress');
            }, 500);
        } else {
            const data = await response.json();
            alert('שגיאה: ' + (data.detail || 'נסה שוב'));
        }
    } catch (error) {
        console.error('Download plugin error:', error);
        alert('שגיאה בהורדת התוסף');
    } finally {
        btn.disabled = false;
        btn.textContent = '📥 הורד תוסף לוורדפרס';
    }
}

async function copyEmbedCode() {
    const codeElement = document.getElementById('embedCodeSnippet');
    if (!codeElement) return;
    
    const code = codeElement.textContent;
    
    try {
        await navigator.clipboard.writeText(code);
        const btn = document.getElementById('copyEmbedCode');
        const originalText = btn.textContent;
        btn.textContent = '✓ הועתק!';
        btn.style.background = '#10b981';
        
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '';
        }, 2000);
    } catch (error) {
        console.error('Copy error:', error);
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = code;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        
        alert('הקוד הועתק ללוח!');
    }
}

function loadAllData() {
    const tier = getSubscriptionTier();
    
    // Always load products and analytics for all tiers
    loadProducts();
    loadAnalytics();
    
    // Only load orders for Pro and Premium tiers
    if (tier !== 'free') {
        loadOrders();
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
    // Revenue
    const revenueEl = document.getElementById('kpiRevenue');
    if (revenueEl) {
        revenueEl.textContent = `₪${analytics.total_revenue.toFixed(2)}`;
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
        aovEl.textContent = `₪${analytics.average_order_value.toFixed(2)}`;
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
    if (!canvas || !revenueData.revenue_by_day) return;
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart
    if (revenueChart) {
        revenueChart.destroy();
    }
    
    const labels = revenueData.revenue_by_day.map(d => {
        const date = new Date(d.date);
        return date.toLocaleDateString('he-IL', { month: 'short', day: 'numeric' });
    });
    
    const data = revenueData.revenue_by_day.map(d => d.revenue);
    
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
}

function renderOrdersChart(ordersData) {
    const canvas = document.getElementById('ordersChart');
    if (!canvas || !ordersData.orders_by_status) return;
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart
    if (ordersChart) {
        ordersChart.destroy();
    }
    
    const statuses = ordersData.orders_by_status;
    const labels = Object.keys(statuses).map(s => getStatusText(s));
    const data = Object.values(statuses);
    const colors = Object.keys(statuses).map(s => {
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
    pendingValue = 0;
    completedCount = 0;
    failedCount = 0;
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
            business_id: currentBusiness.business_id,
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
// Auto-refresh
// ============================================

setInterval(() => {
    if (currentBusiness && ConversaPayAuth.getToken()) {
        loadOrders();
    }
}, 30000);