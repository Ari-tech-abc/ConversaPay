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
    document.getElementById('upgradeToProBtn')?.addEventListener('click', handleUpgradeToPro);
    
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
            
            if (!isPro) {
                // State 0: Non-Pro user - show upgrade state
                showUpgradeState();
            } else {
                // Pro user - load businesses
                loadUserBusinesses();
            }
        } else {
            // If profile check fails, assume not Pro
            showUpgradeState();
        }
    } catch (error) {
        console.error('Error checking subscription:', error);
        showUpgradeState();
    }
}

function showUpgradeState() {
    // Hide all other states
    document.getElementById('upgradeState').classList.remove('d-none');
    document.getElementById('noBusinessState').classList.add('d-none');
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.add('d-none');
    document.getElementById('proPlanBanner').classList.add('d-none');
    
    // Hide loading
    hideLoading();
}

async function handleUpgradeToPro() {
    const btn = document.getElementById('upgradeToProBtn');
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
                full_name: currentUser.full_name || ''
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Redirect to Stripe Checkout
            window.location.href = data.url;
        } else {
            const data = await response.json();
            alert('שגיאה: ' + (data.detail || 'נסה שוב'));
        }
    } catch (error) {
        console.error('Upgrade error:', error);
        alert('שגיאה בתקשורת עם השרת');
    } finally {
        btn.disabled = false;
        btn.textContent = '💳 שדרג ל-Pro והפעל את הבוט';
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
    // Hide empty state, show dashboard
    document.getElementById('noBusinessState').classList.add('d-none');
    document.getElementById('createBusinessFormCard').classList.add('d-none');
    document.getElementById('dashboardContent').classList.remove('d-none');
    
    // Show business name in header
    document.getElementById('businessDisplayName').textContent = `🏢 ${currentBusiness.business_name}`;
    document.getElementById('businessDisplaySlug').textContent = `מזהה: ${currentBusiness.business_id}`;
    
    // Check for session_id from successful payment redirect
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    if (sessionId) {
        const banner = document.getElementById('proPlanBanner');
        if (banner) banner.classList.remove('d-none');
        window.history.replaceState({}, document.title, '/dashboard.html');
    }
    
    // Update embed code with actual business_id
    updateEmbedCode();
    
    // Check if business has a website - show onboarding if not
    checkWebsiteStatus();
}

async function checkWebsiteStatus() {
    try {
        const token = ConversaPayAuth.getToken();
        const response = await fetch(`${API_BASE_URL}/businesses/${currentBusiness.business_id}`, {
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

function showWebsiteOnboarding() {
    // Hide standard analytics sections
    const analyticsSection = document.querySelector('.stats-grid');
    const chartsSection = document.querySelectorAll('.card')[1]; // Charts card
    const ordersSection = document.querySelectorAll('.card')[2]; // Orders card
    const productsSection = document.querySelectorAll('.card')[3]; // Products card
    
    if (analyticsSection) analyticsSection.classList.add('d-none');
    if (chartsSection) chartsSection.classList.add('d-none');
    if (ordersSection) ordersSection.classList.add('d-none');
    if (productsSection) productsSection.classList.add('d-none');
    
    // Show onboarding card
    const onboardingCard = document.getElementById('websiteOnboardingCard');
    if (onboardingCard) {
        onboardingCard.classList.remove('d-none');
        
        // Set dynamic link to site builder
        const token = ConversaPayAuth.getToken();
        const siteBuilderUrl = `http://localhost:8001/frontend/index.html?business_id=${currentBusiness.business_id}&token=${token}`;
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
    const ordersSection = document.querySelectorAll('.card')[2];
    const productsSection = document.querySelectorAll('.card')[3];
    
    if (analyticsSection) analyticsSection.classList.remove('d-none');
    if (chartsSection) chartsSection.classList.remove('d-none');
    if (ordersSection) ordersSection.classList.remove('d-none');
    if (productsSection) productsSection.classList.remove('d-none');
    
    // Load all data
    loadAllData();
}

// ============================================
// Integrations
// ============================================

function updateEmbedCode() {
    if (!currentBusiness) return;
    
    const embedCode = `<!-- ConversaPay AI Chatbot -->
<script>
  window.ConversaPayWidgetConfig = { business_id: "${currentBusiness.business_id}" };
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
    loadOrders();
    loadProducts();
    loadAnalytics();
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
        // Load main analytics
        const analyticsPromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.business_id}/analytics`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null);
        
        // Load revenue data
        const revenuePromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.business_id}/revenue?days=${days}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null);
        
        // Load order analytics
        const ordersPromise = fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.business_id}/orders?days=${days}`, {
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
        const response = await fetch(`${API_BASE_URL}/analytics/businesses/${currentBusiness.business_id}/analytics`, {
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
    if (!currentBusiness) return;
    
    try {
        const token = ConversaPayAuth.getToken();
        const statusFilter = document.getElementById('statusFilter')?.value || '';
        
        let url = `${API_BASE_URL}/orders?business_id=${currentBusiness.business_id}&limit=50`;
        if (statusFilter) {
            url += `&status_filter=${statusFilter}`;
        }
        
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const orders = await response.json();
            renderOrders(orders);
            updateAnalytics(orders);
        }
    } catch (error) {
        console.error('Error loading orders:', error);
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
    if (!orders || orders.length === 0) {
        document.getElementById('statRevenue').textContent = '₪0';
        document.getElementById('statPending').textContent = '0';
        document.getElementById('statPendingValue').textContent = '0';
        document.getElementById('statCompleted').textContent = '0';
        document.getElementById('statFailed').textContent = '0';
        document.getElementById('statTotal').textContent = '0';
        return;
    }
    
    let totalRevenue = 0;
    let pendingCount = 0;
    let pendingValue = 0;
    let completedCount = 0;
    let failedCount = 0;
    
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
    });
    
    document.getElementById('statRevenue').textContent = `₪${totalRevenue.toFixed(2)}`;
    document.getElementById('statPending').textContent = pendingCount;
    document.getElementById('statPendingValue').textContent = pendingValue.toFixed(2);
    document.getElementById('statCompleted').textContent = completedCount;
    document.getElementById('statFailed').textContent = failedCount;
    document.getElementById('statTotal').textContent = orders.length;
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
        const response = await fetch(`${API_BASE_URL}/products?business_id=${currentBusiness.business_id}&active_only=false`, {
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