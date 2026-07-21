# ConversaPay - Complete Project Architecture Map

## 📌 Project Overview

**ConversaPay** is a multi-tenant SaaS platform that transforms websites into AI-powered sales machines. The platform combines:
- **AI Chatbot:** Gemini-powered conversational agent that sells products
- **Payment Processing:** PayMe (Israeli) + Stripe (legacy) for secure checkout
- **Analytics Dashboard:** Real-time business intelligence
- **Multi-Channel Support:** Web chat + WhatsApp (Premium tier)
- **Website Builder:** AI-generated landing pages
- **WordPress Plugin:** Easy embedding for non-technical users

**Tech Stack:**
- Backend: FastAPI (Python)
- Frontend: Vanilla JavaScript, HTML/CSS
- Database: Supabase (PostgreSQL with RLS)
- AI: Google Gemini API
- Payments: PayMe (primary) + Stripe (legacy)
- Email: Resend
- WhatsApp: Meta WhatsApp Cloud API

**Version:** 2.0.0  
**Last Updated:** 2026-07-21  
**Status:** Production Ready ✅

---

## 📁 Complete Project Structure

```
conversapay-project/
│
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (not in git)
├── .gitignore                       # Git ignore rules
├── Dockerfile                       # Docker configuration
│
├── backend/                         # Core backend package
│   ├── __init__.py
│   ├── config.py                    # Configuration settings (Supabase, API keys, PayMe)
│   │
│   ├── routers/                     # API route handlers (14 routers)
│   │   ├── __init__.py
│   │   ├── auth.py                  # Authentication (register, login, verify email)
│   │   ├── businesses.py            # Business CRUD operations
│   │   ├── products.py              # Product management
│   │   ├── chat.py                  # AI chat endpoint (Gemini integration)
│   │   ├── orders.py                # Order management & tracking
│   │   ├── payments.py              # Payment processing (Stripe legacy)
│   │   ├── payme_webhook.py         # PayMe webhook handler (NEW - primary payment)
│   │   ├── whatsapp.py              # WhatsApp webhook handler (NEW - Premium tier)
│   │   ├── analytics.py             # Business analytics & metrics
│   │   ├── logs.py                  # Activity logging
│   │   ├── webhooks.py              # Generic webhook handlers
│   │   ├── widget.py                # Public widget config endpoint
│   │   └── dev_simulator.py         # Dev-only payment simulator (never in production)
│   │
│   ├── services/                    # Business logic layer (6 services)
│   │   ├── __init__.py
│   │   ├── gemini_service.py        # Gemini AI integration
│   │   ├── payme_service.py         # PayMe payment logic (NEW - primary)
│   │   ├── email_service.py         # Email notifications (Resend)
│   │   ├── session_service.py       # Session & conversation management (NEW)
│   │   ├── product_service.py       # Product search & matching (NEW)
│   │   └── monitoring_service.py    # Application monitoring
│   │
│   ├── middleware/                  # Custom middleware
│   │   ├── __init__.py
│   │   ├── auth.py                  # JWT verification middleware
│   │   └── rate_limiter.py          # Rate limiting for public endpoints (NEW)
│   │
│   ├── models/                      # Pydantic models/schemas
│   │   ├── __init__.py
│   │   └── schemas.py               # Request/response validation models
│   │
│   ├── static/                      # Static assets
│   │   ├── robots.txt               # SEO robots file
│   │   ├── sitemap.xml              # SEO sitemap
│   │   └── js/
│   │       └── widget.js            # Production widget (served from here)
│   │
│   └── scripts/                     # Database migration scripts
│       ├── apply_migration.sql
│       ├── migrate_email_verification.py
│       └── run_migration.py
│
├── frontend/                        # Frontend assets
│   └── js/
│       ├── auth.js                  # Authentication logic (login/register)
│       ├── dashboard.js             # Dashboard functionality
│       └── widget.js                # Embeddable chat widget (source)
│
├── database/                        # Database schemas
│   ├── schema.sql                   # Complete database schema (13 tables)
│   └── supabase_migration.sql       # Migration helper
│
├── conversapay-site-builder/        # AI Website Builder (separate service)
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── config.py                # Site builder configuration
│   │   ├── main.py                  # FastAPI app (port 8001)
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── generator.py         # AI site generation endpoint
│   ├── frontend/
│   │   └── index.html               # Site builder wizard UI
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── wordpress-plugin/                # WordPress integration
│   ├── conversapay-chat.php         # Main plugin file
│   └── README.md                    # Plugin documentation
│
├── home.html                        # Landing page (served at /)
├── dashboard.html                   # Main dashboard (analytics, orders, products)
├── login.html                       # Login page (premium dark theme)
├── register.html                    # Registration page (premium dark theme)
├── pay.html                         # Payment simulator page
├── index.html                       # Sandbox chat preview
│
├── ARCHITECTURE.md                  # Production architecture overview
├── PROJECT_MAP.md                   # This file - complete architecture guide
└── README.md                        # Project readme
```

---

## 🏗️ Architecture Deep Dive

### 1. **Request Flow: Multi-Tenant SaaS**

```
Client Request
    ↓
main.py (FastAPI App)
    ↓
DualCORSMiddleware (CORS validation - widget vs dashboard)
    ↓
RateLimiter (for public endpoints like chat)
    ↓
Auth Middleware (JWT validation for protected routes)
    ↓
Router (auth/businesses/chat/etc.)
    ↓
Service Layer (business logic)
    ↓
Database (Supabase/PostgreSQL with RLS)
    ↓
Response
```

### 2. **Authentication Flow**

```
1. User submits login/register form
   ↓
2. Frontend (auth.js) → POST /api/v1/auth/login or /register
   ↓
3. Backend validates credentials via Supabase Auth
   ↓
4. Returns JWT token
   ↓
5. Frontend stores token in localStorage
   ↓
6. All subsequent requests include: Authorization: Bearer <token>
   ↓
7. Middleware (auth.py) validates JWT on each request
```

### 3. **AI Chat Flow (Web Widget)**

```
1. Customer visits website with embedded widget
   ↓
2. widget.js loads and fetches config from /api/v1/widget/config/{business_id}
   ↓
3. Customer sends message
   ↓
4. Widget → POST /api/v1/chat
   ↓
5. chat.py router receives request
   ↓
6. RateLimiter checks IP (10 requests/minute)
   ↓
7. session_service.get_or_create_conversation() - database-backed
   ↓
8. gemini_service.chat() processes with Gemini AI
   ↓
9. AI determines intent (product inquiry, checkout, etc.)
   ↓
10. product_service.search_products() if product inquiry
   ↓
11. If checkout intent: Returns payment_url from PayMe/Stripe
   ↓
12. Widget displays response with payment button
   ↓
13. Customer completes payment
   ↓
14. Webhook (payme_webhook.py or payments.py) updates order status
```

### 4. **WhatsApp Chat Flow (Premium Tier)**

```
1. Customer sends WhatsApp message to business number
   ↓
2. Meta WhatsApp Cloud API → POST /api/v1/webhooks/whatsapp
   ↓
3. whatsapp.py router receives webhook
   ↓
4. Validates phone_number_id and Premium tier status
   ↓
5. session_service.get_or_create_conversation() with channel="whatsapp"
   ↓
6. session_service.get_or_create_customer() with phone identifier
   ↓
7. gemini_service.chat() processes with business context
   ↓
8. AI response saved to database
   ↓
9. send_whatsapp_message() sends response via Meta Graph API
   ↓
10. Returns 200 OK to Meta (retry loop satisfied)
```

### 5. **Payment Flow (PayMe - Primary)**

```
1. User selects Pro (₪200) or Premium (₪350) plan
   ↓
2. POST /api/v1/payments/create-checkout-session
   ↓
3. payme_service.create_hosted_setup_session() creates PayMe sale
   ↓
4. Returns sale_url (hosted payment page)
   ↓
5. User redirected to PayMe hosted page
   ↓
6. User completes payment on PayMe
   ↓
7. PayMe sends IPN to /api/v1/webhooks/payme
   ↓
8. payme_webhook.py processes webhook
   ↓
9. _activate_subscription() updates profile:
   - is_pro = true
   - plan_type = "pro" or "premium"
   - payme_card_token stored for recurring billing
   ↓
10. User can now access Pro/Premium features
```

### 6. **Dashboard Analytics Flow**

```
1. User logs in → dashboard.html loads
   ↓
2. dashboard.js checks business.website_url
   ↓
3a. IF no website → Show onboarding card → Link to site builder
3b. IF has website → Show standard dashboard
   ↓
4. Load analytics: GET /api/v1/analytics/businesses/{id}/analytics
   ↓
5. Load orders: GET /api/v1/orders?business_id={id}
   ↓
6. Load products: GET /api/v1/products?business_id={id}
   ↓
7. Render charts (Chart.js) and tables
   ↓
8. Auto-refresh every 30 seconds
```

---

## 📂 File-by-File Purpose Guide

### **Root Level Files**

#### `main.py`
**Purpose:** Application entry point and configuration
- Initializes FastAPI app with lifespan events
- Configures DualCORSMiddleware for dual-tier CORS
- Registers all 14 routers
- Serves static HTML pages (home, dashboard, login, register, pay)
- Handles errors (404, 500)
- Dynamic port binding for Render deployment
- **Key Sections:**
  - `lifespan()`: Startup/shutdown events with configuration validation
  - `DualCORSMiddleware`: Widget vs Dashboard CORS policies
  - Router registration: All API endpoints
  - Static file mounting: `/static` and `/frontend`

#### `requirements.txt`
**Purpose:** Python dependencies
- FastAPI, uvicorn, pydantic-settings
- Supabase client
- Google Generative AI
- Resend (email)
- httpx (HTTP client for PayMe/WhatsApp)
- python-dotenv

#### `.env`
**Purpose:** Environment variables (not in git)
- Supabase credentials
- API keys (Gemini, PayMe, Stripe, Resend)
- CORS origins
- Environment flags

---

### **Backend Core**

#### `backend/config.py`
**Purpose:** Centralized configuration
- Loads environment variables with Pydantic Settings
- Provides settings object with type safety
- API keys, database URLs, CORS origins
- Environment detection (dev/prod)
- **PayMe Configuration:**
  - `PAYME_PAY_KEY`, `PAYME_SELLER_KEY`, `PAYME_SELLER_ID`
  - `PAYME_BUSINESS_ID`, `PAYME_API_URL`, `PAYME_SANDBOX_URL`
- **WhatsApp Configuration:** (stored in profiles table)
- **Properties:**
  - `cors_origins_list`: Parsed CORS origins
  - `is_production`: Environment check
  - `is_development`: Environment check

#### `backend/routers/auth.py`
**Purpose:** Authentication endpoints
- `POST /api/v1/auth/register`: User registration with email verification
- `POST /api/v1/auth/login`: User login (returns JWT)
- `POST /api/v1/auth/logout`: Session invalidation
- `GET /api/v1/auth/me`: Get current user
- `GET /api/v1/auth/verify`: Email verification handler
- Uses Supabase Auth for JWT management
- Generates secure verification tokens with `secrets.token_urlsafe(32)`

#### `backend/routers/businesses.py`
**Purpose:** Business management
- `GET /api/v1/businesses`: List user's businesses
- `POST /api/v1/businesses`: Create new business
- `GET /api/v1/businesses/{id}`: Get business details
- `PUT /api/v1/businesses/{id}`: Update business
- `DELETE /api/v1/businesses/{id}`: Delete business
- Multi-tenant: Each user can have multiple businesses
- Enforces Pro subscription for business creation

#### `backend/routers/products.py`
**Purpose:** Product catalog management
- `GET /api/v1/products`: List products (with filters)
- `POST /api/v1/products`: Create product
- `PUT /api/v1/products/{id}`: Update product
- `DELETE /api/v1/products/{id}`: Delete product
- Fields: name, price, description, image_url, is_active, item_key
- Uses product_service for search and matching

#### `backend/routers/chat.py`
**Purpose:** AI chat endpoint
- `POST /api/v1/chat`: Send message to AI (Gemini)
- Rate limited (10 requests/minute per IP)
- Integrates with Gemini API via gemini_service
- Determines user intent (product inquiry, checkout, etc.)
- Creates/updates chat sessions in database
- Logs conversations for analytics
- Returns AI response + optional payment_url

#### `backend/routers/orders.py`
**Purpose:** Order management
- `GET /api/v1/orders`: List orders (with filters)
- `GET /api/v1/orders/{id}`: Get order details
- `POST /api/v1/orders`: Create order (from chat)
- `PUT /api/v1/orders/{id}/status`: Update status
- `GET /api/v1/orders/summary`: Analytics summary
- Statuses: pending, paid, processing, shipped, delivered, canceled, refunded
- Creates unique order numbers with `generate_order_number()`

#### `backend/routers/payments.py`
**Purpose:** Payment processing (Stripe legacy)
- `POST /api/v1/payments/create-checkout-session`: Create Stripe session
- `POST /api/v1/payments/webhook`: Stripe webhook handler
- `GET /api/v1/payments/profile`: Get subscription status
- `GET /api/v1/payments/wordpress-plugin/{business_id}`: Download WP plugin
- Handles Pro subscription ($29/month) - being replaced by PayMe

#### `backend/routers/payme_webhook.py` ⭐ NEW
**Purpose:** PayMe webhook handler (primary payment gateway)
- `POST /api/v1/webhooks/payme`: Instant Payment Notifications (IPN)
- Processes successful payments to activate subscriptions
- Handles failures/cancellations to deactivate subscriptions
- Stores PayMe card tokens for recurring billing (הוראת קבע)
- Updates profile: `is_pro`, `plan_type`, `payme_card_token`, `payme_sale_id`
- 2-tier pricing: Pro (₪200/month) and Premium (₪350/month)

#### `backend/routers/whatsapp.py` ⭐ NEW
**Purpose:** WhatsApp webhook handler (Premium tier only)
- `GET /api/v1/webhooks/whatsapp`: Meta webhook verification
- `POST /api/v1/webhooks/whatsapp`: WhatsApp message handler
- Validates merchant has Premium tier (`is_pro=true`, `plan_type="premium"`)
- Looks up merchant by `whatsapp_phone_number_id`
- Creates conversations with channel="whatsapp"
- Processes messages through Gemini AI (same as web chat)
- Sends responses via Meta Graph API
- Returns 200 OK to satisfy Meta's retry loop

#### `backend/routers/analytics.py`
**Purpose:** Business analytics
- `GET /api/v1/analytics/businesses/{id}/analytics`: KPI metrics
- `GET /api/v1/analytics/businesses/{id}/revenue`: Revenue over time
- `GET /api/v1/analytics/businesses/{id}/orders`: Order analytics
- Metrics: total_revenue, conversion_rate, average_order_value, unique_sessions

#### `backend/routers/logs.py`
**Purpose:** Activity logging
- `GET /api/v1/logs`: List logs (with filters)
- `POST /api/v1/logs`: Create log entry
- Levels: debug, info, warning, error, critical
- Sources: api, ai, payment, webhook, system

#### `backend/routers/webhooks.py`
**Purpose:** Generic webhook handlers
- Configurable webhook endpoints for businesses
- Event types: order.created, payment.succeeded, etc.
- Retry logic and failure tracking

#### `backend/routers/widget.py`
**Purpose:** Public widget configuration
- `GET /api/v1/widget/config/{business_id}`: Get bot config
- **Security:** Validates requesting domain against whitelist
- Returns: bot_name, greeting, theme_colors, features
- No sensitive data exposed

#### `backend/routers/dev_simulator.py` ⚠️ DEV ONLY
**Purpose:** Development payment simulator
- Simulates PayMe/Stripe webhooks for local testing
- **NEVER loaded in production** (guarded by `settings.is_production`)
- Helps test payment flows without real payment gateway

---

### **Services Layer**

#### `backend/services/gemini_service.py`
**Purpose:** Gemini AI integration
- Sends prompts to Gemini API
- Parses AI responses
- Determines user intent (chat, checkout, error)
- Extracts product recommendations
- Handles checkout intents
- Maintains conversation context

#### `backend/services/payme_service.py` ⭐ NEW
**Purpose:** PayMe payment logic (primary gateway)
- Creates hosted payment page sessions
- Supports 2-tier pricing: Pro (₪200) and Premium (₪350)
- Handles recurring billing setup (הוראת קבע)
- Uses PayMe's `/generate-sale` endpoint
- Returns `sale_url` for redirect
- Verifies webhook signatures (basic validation)

#### `backend/services/email_service.py`
**Purpose:** Email notifications (Resend)
- Sends order confirmations
- Sends payment receipts
- Sends admin notifications
- Sends email verification links
- Professional HTML templates with ConversaPay branding

#### `backend/services/session_service.py` ⭐ NEW
**Purpose:** Session & conversation management
- Database-backed sessions (replaced in-memory storage)
- `get_or_create_conversation()`: Manages chat sessions
- `get_conversation_history()`: Retrieves message history
- `add_message()`: Saves messages to database
- `close_conversation()`: Marks conversations as closed
- `get_or_create_customer()`: Manages customer records
- `get_conversation_stats()`: Analytics on conversations
- Supports multiple channels: web, whatsapp, telegram, api

#### `backend/services/product_service.py` ⭐ NEW
**Purpose:** Product search and matching
- `search_products()`: Semantic and keyword matching
- `get_product_by_item_key()`: Lookup by item key
- `get_product_by_id()`: Lookup by UUID
- `get_all_products()`: List all products for business
- `format_product_for_ai()`: Formats product info for Gemini (Hebrew)
- Scoring algorithm: exact match (100), contains (50), word match (15)

#### `backend/services/monitoring_service.py`
**Purpose:** Application monitoring
- Tracks application health
- External service status (PayMe, Gemini, Resend)
- Database connection health
- Rate limiter statistics

---

### **Middleware**

#### `backend/middleware/auth.py`
**Purpose:** JWT authentication middleware
- Verifies JWT tokens from Supabase Auth
- Extracts user info from token
- Attaches user to request state
- Returns 401 if invalid
- Auto-logout on 401 responses

#### `backend/middleware/rate_limiter.py` ⭐ NEW
**Purpose:** Rate limiting for public endpoints
- Token bucket algorithm
- Limits requests per IP address
- Default: 10 requests/minute for chat endpoint
- `get_client_ip()`: Handles proxies and load balancers
- `check_rate_limit()`: Dependency for FastAPI endpoints
- Returns 429 with Retry-After header when exceeded

---

### **Models**

#### `backend/models/schemas.py`
**Purpose:** Pydantic models for request/response validation
- **Enums:** SubscriptionTier, SubscriptionStatus, ChannelType, OrderStatus, PaymentStatus, etc.
- **Business Models:** BusinessBase, BusinessCreate, BusinessUpdate, BusinessResponse
- **Product Models:** ProductBase, ProductCreate, ProductUpdate, ProductResponse
- **Customer Models:** CustomerBase, CustomerCreate, CustomerUpdate, CustomerResponse
- **Conversation Models:** ConversationBase, ConversationCreate, ConversationUpdate, ConversationResponse
- **Message Models:** MessageBase, MessageCreate, MessageResponse
- **Order Models:** OrderItem, OrderBase, OrderCreate, OrderUpdate, OrderResponse
- **Subscription Models:** SubscriptionCreate, SubscriptionResponse
- **Payment Models:** PaymentBase, PaymentCreate, PaymentResponse
- **Profile Models:** ProfileBase, ProfileCreate, ProfileUpdate, ProfileResponse (includes WhatsApp fields)
- **Auth Models:** UserRegister, UserLogin, TokenResponse, PasswordResetRequest, PasswordReset
- **Log Models:** LogCreate, LogResponse
- **API Key Models:** ApiKeyBase, ApiKeyCreate, ApiKeyResponse, ApiKeyWithSecret
- **Webhook Models:** WebhookBase, WebhookCreate, WebhookUpdate, WebhookResponse
- **Analytics Models:** AnalyticsOverviewResponse, DashboardStats, RevenueStats, OrderStats

---

### **Frontend Files**

#### `frontend/js/auth.js`
**Purpose:** Authentication logic
- Login form submission
- Registration form submission
- Token storage in localStorage
- Token validation
- Logout functionality
- Redirect logic

#### `frontend/js/dashboard.js`
**Purpose:** Dashboard functionality
- Business state management
- Website status check (onboarding flow)
- Analytics loading (KPIs, charts)
- Order management (list, filter, view details)
- Product management (CRUD operations)
- Integration code generation
- WordPress plugin download
- Auto-refresh every 30s

#### `frontend/js/widget.js`
**Purpose:** Embeddable chat widget
- Dynamic injection into host sites
- Floating chat toggle button
- Chat window with glass morphism
- Message bubbles (user: purple, bot: blue)
- Real-time chat via API
- Typing indicators
- Payment link handling
- Public API: `window.ConversaPayWidget`

---

### **Dashboard HTML**

#### `dashboard.html`
**Purpose:** Main business dashboard
- **States:**
  1. Upgrade state (non-Pro users)
  2. No business state (Pro users without business)
  3. Onboarding state (no website → site builder link)
  4. Dashboard state (full analytics)

- **Sections:**
  - Business header
  - AI Website Builder onboarding card
  - KPI Bento Grid (revenue, conversion, AOV, sessions)
  - Analytics charts (revenue line chart, orders bar chart)
  - Orders table with filters
  - Top products table
  - Product management
  - Integrations (WordPress download, embed code)

- **Design:** Linear/Stripe dark theme, glass morphism, purple gradients

---

### **Authentication Pages**

#### `login.html`
**Purpose:** User login
- Premium dark theme (#0B0F19)
- Glass morphism card
- Email/password fields
- Remember me checkbox
- Gradient button (purple → blue)
- Links to register

#### `register.html`
**Purpose:** User registration
- Premium dark theme
- Full name, email, password, business name
- Password strength indicator
- Business info box
- Gradient submit button
- Email verification requirement

---

### **WordPress Plugin**

#### `wordpress-plugin/conversapay-chat.php`
**Purpose:** WordPress integration
- **Admin:** Settings page under Settings → ConversaPay Chat
- **Frontend:** Injects widget.js into wp_footer
- **Configuration:** Business ID, position, color, page targeting
- **Security:** Sanitization, nonce verification
- **Activation:** Creates default settings

**Key Functions:**
- `conversapay_chat_admin_menu()`: Add admin menu
- `conversapay_chat_settings_page()`: Settings UI
- `conversapay_chat_inject_widget()`: Inject script tag
- `conversapay_chat_sanitize_settings()`: Input sanitization

---

### **Database Schema**

#### `database/schema.sql`
**Purpose:** Complete database structure (13 tables)
- **Tables:**
  - `profiles`: User accounts and subscription status
  - `businesses`: Business profiles (tenant root)
  - `products`: Product catalog
  - `customers`: Customer database
  - `conversations`: Chat session tracking
  - `messages`: Message history
  - `orders`: Order records
  - `payments`: Payment transactions
  - `subscriptions`: Subscription management
  - `api_keys`: API key management
  - `webhooks`: Webhook configuration
  - `logs`: Application logging
  - `email_templates`: Customizable email templates

- **Security:**
  - Row Level Security (RLS) on all tables
  - Multi-tenant data isolation
  - Subscription field protection triggers
  - Updated_at triggers on all tables

---

## 🔐 Security Architecture

### **Authentication**
- JWT tokens via Supabase Auth
- Middleware validates on every request
- Tokens stored in localStorage
- Auto-logout on 401
- Email verification required for registration

### **Authorization**
- Row Level Security (RLS) in database
- Business ownership validation
- Role-based access (admin, user, viewer)
- Subscription field protection (database trigger)

### **Widget Security**
- Domain whitelist validation
- Origin/Referer header checking
- 403 Forbidden for unauthorized domains
- No private keys in public responses

### **Rate Limiting**
- Token bucket algorithm
- 10 requests/minute for chat endpoint
- IP-based tracking (handles proxies)
- Returns 429 with Retry-After header

### **CORS Policy**
- **Widget endpoints:** `*` (any origin, no credentials)
- **Dashboard endpoints:** Configured origins only, credentials allowed
- **Webhooks:** `*` (any origin, no credentials)

---

## 🎨 Design System

### **Color Palette**
- **Primary Background:** `#0B0F19` (midnight dark)
- **Secondary Background:** `#111827` (dark gray)
- **Primary Accent:** `#A855F7` (purple)
- **Secondary Accent:** `#00D9FF` (cyan)
- **Text Primary:** `#F9FAFB` (white)
- **Text Secondary:** `#9CA3AF` (gray)
- **Success:** `#10B981` (green)
- **Warning:** `#F59E0B` (orange)
- **Danger:** `#EF4444` (red)

### **Typography**
- **Font:** Plus Jakarta Sans
- **Weights:** 300, 400, 500, 600, 700, 800
- **Letter Spacing:** -0.02em (headings), 0.025em (labels)

### **Components**
- **Cards:** Glass morphism (backdrop-blur, rgba backgrounds)
- **Buttons:** Gradient backgrounds, hover scale transforms
- **Inputs:** Dark backgrounds, purple focus states
- **Borders:** rgba(255, 255, 255, 0.1)
- **Shadows:** Purple glow effects

---

## 🔄 Data Flow Diagrams

### **User Registration → First Sale**

```
1. User registers (register.html)
   ↓
2. POST /api/v1/auth/register
   - Creates Supabase Auth user
   - Creates profile in database
   - Generates email verification token
   - Saves token (24h expiration)
   - Sends email via Resend
   ↓
3. User verifies email (GET /api/v1/auth/verify?token=xxx)
   ↓
4. User logs in (login.html)
   ↓
5. POST /api/v1/auth/login → JWT token
   ↓
6. Dashboard loads (dashboard.html)
   ↓
7. No business → Show "Create Business" form
   ↓
8. POST /api/v1/businesses
   ↓
9. No website → Show AI Site Builder onboarding
   ↓
10. User generates site (site-builder)
    ↓
11. Business now has website_url
    ↓
12. Dashboard shows analytics
    ↓
13. User adds products (dashboard.html)
    ↓
14. POST /api/v1/products
    ↓
15. Customer visits website
    ↓
16. Widget loads (widget.js)
    ↓
17. Customer chats → POST /api/v1/chat
    ↓
18. AI suggests products (gemini_service + product_service)
    ↓
19. Customer clicks buy
    ↓
20. POST /api/v1/orders
    ↓
21. PayMe checkout session created
    ↓
22. Customer pays on PayMe hosted page
    ↓
23. PayMe webhook updates order status
    ↓
24. Dashboard shows new order + revenue
```

### **WhatsApp Message Flow (Premium)**

```
1. Customer sends WhatsApp message
   ↓
2. Meta Cloud API → POST /api/v1/webhooks/whatsapp
   ↓
3. Validate Premium tier status
   ↓
4. Get/create conversation (channel="whatsapp")
   ↓
5. Get/create customer (phone identifier)
   ↓
6. Load conversation history
   ↓
7. Process with Gemini AI
   ↓
8. Save user + assistant messages
   ↓
9. Send response via WhatsApp
   ↓
10. Return 200 OK to Meta
```

---

## 🚀 Deployment Architecture

### **Production (Render)**
```
┌─────────────────────────────────────┐
│         Render.com Platform         │
├─────────────────────────────────────┤
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │   FastAPI    │  │   Static    │ │
│  │   Backend    │  │   Files     │ │
│  │  (Port 8000)│  │  (HTML/JS)  │ │
│  └──────────────┘  └─────────────┘ │
│         ↓                    ↓      │
│  ┌─────────────────────────────┐   │
│  │   Supabase Database         │   │
│  │   (PostgreSQL + RLS)        │   │
│  └─────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
          ↓                    ↓
    ┌──────────┐      ┌──────────────┐
    │  Gemini  │      │    PayMe     │
    │   API    │      │     API      │
    └──────────┘      └──────────────┐
          ↓                    ↓
    ┌──────────────┐      ┌──────────────┐
    │   Resend     │      │   WhatsApp   │
    │ Email Service│      │  Cloud API   │
    └──────────────┘      └──────────────┘
```

### **Site Builder (Separate Service)**
```
┌─────────────────────────────────────┐
│   conversapay-site-builder          │
│   (Port 8001)                       │
│   ┌─────────────────────────────┐   │
│   │   FastAPI App               │   │
│   │   - /api/v1/builder/generate│   │
│   └─────────────────────────────┘   │
└─────────────────────────────────────┘
          ↓
    ┌──────────┐
    │  Gemini  │
    │   API    │
    └──────────┘
```

### **Environment Variables**
```env
# Application
SECRET_KEY=<generate-secure-32-char-key>
ENVIRONMENT=production
DEBUG=false
API_PREFIX=/api/v1

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJxxx...
SUPABASE_SERVICE_ROLE_KEY=eyJxxx...

# AI
GEMINI_API_KEY=AIzaSy...

# PayMe (Primary Payment Gateway)
PAYME_PAY_KEY=xxx
PAYME_SELLER_KEY=xxx
PAYME_SELLER_ID=xxx
PAYME_BUSINESS_ID=xxx
PAYME_API_URL=https://live.payme.io/api
PAYME_SANDBOX_URL=https://sandbox.payme.io/api

# Stripe (Legacy - being replaced)
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (Resend)
RESEND_API_KEY=re_...
EMAIL_FROM_ADDRESS=no-reply@conversapay.org
EMAIL_FROM_NAME=ConversaPay

# CORS
CORS_ORIGINS=https://conversapay.org,https://www.conversapay.org

# URLs
FRONTEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
BASE_URL=http://localhost:8000

# Monitoring (Optional)
SENTRY_DSN=...
UPTIMEROBOT_API_KEY=...
```

---

## 📊 Database Schema Overview

### **Core Tables (13 tables)**

#### `profiles`
- id (UUID, PK)
- user_id (UUID, unique, FK to Supabase Auth)
- email, full_name, role (admin/user/viewer)
- is_pro (boolean), plan_type (free/pro/premium)
- subscription_expires_at
- stripe_customer_id, stripe_subscription_id
- **WhatsApp Premium fields:** whatsapp_phone_number_id, whatsapp_access_token, whatsapp_verify_token
- **Email verification fields:** email_verified, email_verification_token, email_verification_expires_at
- created_at, updated_at

#### `businesses`
- id (UUID, PK)
- business_id (string, unique)
- business_name, description
- owner_id (UUID, FK to profiles)
- subscription_tier, subscription_status
- stripe_customer_id, stripe_subscription_id
- settings (JSONB), bot_name, greeting_message, theme_colors
- is_active (boolean)
- created_at, updated_at

#### `products`
- id (UUID, PK)
- business_id (UUID, FK)
- item_key (string, unique per business)
- name, description, price, currency (default ILS)
- image_url, is_active, inventory_count (-1 = unlimited)
- metadata (JSONB)
- created_at, updated_at

#### `customers`
- id (UUID, PK)
- business_id (UUID, FK)
- email, phone, name
- total_purchases, purchase_count, last_purchase_at
- metadata (JSONB)
- created_at, updated_at

#### `conversations`
- id (UUID, PK)
- business_id (UUID, FK)
- customer_id (UUID, FK, nullable)
- session_id (string, unique)
- channel (web/whatsapp/telegram/api)
- status (active/closed/archived)
- started_at, ended_at
- metadata (JSONB)
- created_at, updated_at

#### `messages`
- id (UUID, PK)
- conversation_id (UUID, FK)
- role (user/assistant/system)
- content (text)
- intent (string)
- metadata (JSONB)
- created_at

#### `orders`
- id (UUID, PK)
- business_id (UUID, FK)
- customer_id (UUID, FK, nullable)
- conversation_id (UUID, FK, nullable)
- order_number (string, unique)
- status, payment_status
- subtotal, tax, total, currency (default ILS)
- items (JSONB array)
- customer_info, shipping_address (JSONB)
- notes (text)
- created_at, updated_at

#### `payments`
- id (UUID, PK)
- business_id (UUID, FK)
- order_id (UUID, FK, nullable)
- stripe_payment_intent_id, stripe_session_id
- amount, currency, status, payment_method
- customer_email, customer_name
- metadata (JSONB)
- paid_at
- created_at, updated_at

#### `subscriptions`
- id (UUID, PK)
- business_id (UUID, FK)
- stripe_subscription_id, stripe_price_id
- tier (free/pro/enterprise), status
- current_period_start, current_period_end
- cancel_at_period_end, canceled_at
- metadata (JSONB)
- created_at, updated_at

#### `api_keys`
- id (UUID, PK)
- business_id (UUID, FK)
- name, key_hash, key_prefix
- permissions (JSONB array)
- last_used_at, expires_at, is_active
- created_at

#### `webhooks`
- id (UUID, PK)
- business_id (UUID, FK)
- url, events (JSONB array)
- secret, is_active
- last_triggered_at, failure_count
- created_at, updated_at

#### `logs`
- id (UUID, PK)
- business_id (UUID, FK, nullable)
- level, source, message
- details (JSONB)
- user_agent, ip_address (INET)
- created_at

#### `email_templates`
- id (UUID, PK)
- business_id (UUID, FK, nullable)
- template_type (welcome/receipt/password_reset/order_confirmation)
- subject, body_html, body_text
- is_active
- created_at, updated_at

---

## 🔌 API Endpoints Reference

### **Authentication** (`/api/v1/auth`)
- `POST /register` - Register user with email verification
- `POST /login` - Login user
- `POST /logout` - Logout user
- `GET /me` - Get current user
- `GET /verify` - Email verification

### **Businesses** (`/api/v1/businesses`)
- `GET /` - List businesses
- `POST /` - Create business
- `GET /{id}` - Get business
- `PUT /{id}` - Update business
- `DELETE /{id}` - Delete business

### **Products** (`/api/v1/products`)
- `GET /` - List products
- `POST /` - Create product
- `PUT /{id}` - Update product
- `DELETE /{id}` - Delete product

### **Chat** (`/api/v1/chat`)
- `POST /` - Send message to AI (rate limited)
- `GET /sessions` - List chat sessions
- `GET /sessions/{id}/messages` - Get messages

### **Orders** (`/api/v1/orders`)
- `GET /` - List orders
- `GET /{id}` - Get order details
- `POST /` - Create order
- `PUT /{id}/status` - Update status
- `GET /summary` - Analytics summary

### **Payments** (`/api/v1/payments`)
- `POST /create-checkout-session` - Create Stripe session (legacy)
- `POST /webhook` - Stripe webhook
- `GET /profile` - Get subscription status
- `GET /wordpress-plugin/{business_id}` - Download WP plugin

### **PayMe Webhooks** (`/api/v1/webhooks/payme`)
- `POST /` - PayMe IPN handler (primary payment webhook)

### **WhatsApp Webhooks** (`/api/v1/webhooks/whatsapp`)
- `GET /` - Meta webhook verification
- `POST /` - WhatsApp message handler (Premium only)

### **Analytics** (`/api/v1/analytics`)
- `GET /businesses/{id}/analytics` - Get KPIs
- `GET /businesses/{id}/revenue` - Revenue data
- `GET /businesses/{id}/orders` - Order analytics

### **Widget (Public)** (`/api/v1/widget`)
- `GET /config/{business_id}` - Get widget config (domain-validated)

### **Website Builder** (`/api/v1/builder`)
- `POST /generate` - Generate website with AI

### **Logs** (`/api/v1/logs`)
- `GET /` - List logs
- `POST /` - Create log entry

### **Health Check**
- `GET /health` - Application health status

---

## 🧪 Testing Strategy

### **Unit Tests**
- Router tests (each endpoint)
- Service tests (business logic)
- Middleware tests (auth, CORS, rate limiting)
- Utility function tests

### **Integration Tests**
- Full chat flow (message → AI → response)
- Payment flow (PayMe checkout → webhook → order update)
- Authentication flow (register → verify email → login → protected route)
- Widget embedding (domain validation)
- WhatsApp flow (webhook → AI → response)

### **E2E Tests**
- User registration → business creation → product addition → customer chat → purchase
- WordPress plugin installation → widget appearance → chat → payment
- WhatsApp integration → message → AI response → payment

---

## 📈 Scalability Considerations

### **Current Architecture**
- Single FastAPI instance
- Supabase for database (managed PostgreSQL)
- Stateless API (can scale horizontally)
- Static files served by FastAPI (can move to CDN)
- In-memory rate limiter (can move to Redis)

### **Future Scaling**
1. **Load Balancer:** Multiple FastAPI instances behind Nginx
2. **CDN:** Cloudflare for static assets
3. **Redis:** Session caching, rate limiting, distributed locks
4. **Queue:** Celery for async tasks (emails, webhooks)
5. **Monitoring:** Prometheus + Grafana
6. **Logging:** Structured logging to ELK stack
7. **Caching:** Redis for widget config and session data

---

## 🛠️ Development Workflow

### **Local Development**
```bash
# 1. Clone repository
git clone <repo-url>
cd conversapay-project

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
# Edit .env with your Supabase, PayMe, and API credentials

# 5. Run database migrations
# Execute database/schema.sql in Supabase Dashboard

# 6. Start main server
python main.py
# Access: http://localhost:8000

# 7. Start site builder (optional, in separate terminal)
cd conversapay-site-builder
python backend/main.py
# Access: http://localhost:8001
```

### **Site Builder Development**
```bash
cd conversapay-site-builder
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python backend/main.py
# Access: http://localhost:8001/frontend/index.html
```

---

## 📝 Code Conventions

### **Python**
- Type hints on all functions
- Docstrings for all public functions
- Pydantic models for validation
- Async/await for all I/O
- Logging instead of print
- Service layer pattern for business logic

### **JavaScript**
- ES6+ syntax
- Async/await for API calls
- Event delegation where possible
- Consistent naming: camelCase
- Error handling on all async operations

### **CSS**
- CSS custom properties (variables)
- Mobile-first responsive design
- BEM-like naming for classes
- Inline styles for dynamic values
- Glass morphism effects

---

## 🔍 Key Configuration Points

### **For New Developers**
1. Read `PROJECT_MAP.md` (this file)
2. Read `ARCHITECTURE.md` for production overview
3. Set up `.env` with Supabase and PayMe credentials
4. Run database migrations from `database/schema.sql`
5. Start server with `python main.py`
6. Explore API at `/docs`
7. Test chat flow with widget.js
8. Test WhatsApp integration (requires Premium tier and Meta Business API)

### **For AI Tools**
This file serves as the complete context for:
- Understanding project purpose and architecture
- Navigating file structure
- Understanding data flow
- Making informed code changes
- Generating documentation
- Creating new features

---

## 📞 Support & Documentation

- **Main Docs:** https://conversapay.org/docs
- **API Reference:** https://conversapay.org/docs/api
- **WordPress Plugin:** See `wordpress-plugin/README.md`
- **Site Builder:** See `conversapay-site-builder/README.md`

---

## 🎯 Subscription Tiers

### **Free Tier**
- Basic AI chatbot
- 1 business
- 10 products max
- Web chat only
- Basic analytics

### **Pro Tier (₪200/month)**
- Unlimited products
- Advanced analytics
- WordPress plugin
- Custom branding
- Priority support
- PayMe recurring billing

### **Premium Tier (₪350/month)**
- All Pro features
- WhatsApp Business integration
- Multi-channel support (web + WhatsApp)
- Advanced AI training
- Dedicated support
- PayMe recurring billing

---

## 🔄 Recent Changes (2026-07-21)

### **Major Updates**
- ✅ **PayMe Integration:** Primary Israeli payment gateway with recurring billing
- ✅ **WhatsApp Webhook:** Premium tier WhatsApp Business integration
- ✅ **Rate Limiting:** Protection for public chat endpoints
- ✅ **Session Service:** Database-backed conversation management
- ✅ **Product Service:** Intelligent product search and matching
- ✅ **Email Verification:** User registration with email confirmation
- ✅ **Dual CORS Middleware:** Separate policies for widget vs dashboard
- ✅ **WhatsApp Support:** Full WhatsApp Business API integration

### **Architecture Evolution**
- Migrated from Stripe-only to PayMe (primary) + Stripe (legacy)
- Added WhatsApp as premium channel alongside web chat
- Implemented database-backed sessions (replaced in-memory storage)
- Added rate limiting for public API endpoints
- Enhanced security with subscription field protection triggers
- Added product service for intelligent search
- Added session service for conversation management

---

**Last Updated:** 2026-07-21  
**Version:** 2.0.0  
**Status:** Production Ready ✅

**Platform:** Render + Supabase + PayMe + Gemini + Resend + WhatsApp