# ConversaPay - Complete Project Architecture Map

## 📌 Project Overview

**ConversaPay** is a multi-tenant SaaS platform that transforms websites into AI-powered sales machines. The platform combines:
- **AI Chatbot**: Gemini-powered conversational agent that sells products
- **Payment Processing**: Stripe integration for secure checkout
- **Analytics Dashboard**: Real-time business intelligence
- **Website Builder**: AI-generated landing pages
- **WordPress Plugin**: Easy embedding for non-technical users

**Tech Stack:**
- Backend: FastAPI (Python)
- Frontend: Vanilla JavaScript, HTML/CSS
- Database: Supabase (PostgreSQL)
- AI: Google Gemini API
- Payments: Stripe
- Email: Resend

---

## 📁 Complete Project Structure

```
conversapay-project/
│
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variables template
├── .gitignore                       # Git ignore rules
│
├── backend/                         # Core backend package
│   ├── __init__.py
│   ├── config.py                    # Configuration settings (Supabase, API keys)
│   │
│   ├── routers/                     # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py                  # Authentication (login, register, JWT)
│   │   ├── businesses.py            # Business CRUD operations
│   │   ├── products.py              # Product management
│   │   ├── chat.py                  # AI chat endpoint (Gemini integration)
│   │   ├── orders.py                # Order management & tracking
│   │   ├── payments.py              # Stripe payment processing
│   │   ├── analytics.py             # Business analytics & metrics
│   │   ├── logs.py                  # Activity logging
│   │   ├── webhooks.py              # Stripe webhook handlers
│   │   ├── widget.py                # Public widget config endpoint
│   │   └── generator.py             # AI website builder (conversapay-site-builder)
│   │
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── gemini_service.py        # Gemini AI integration
│   │   ├── payment_service.py       # Stripe payment logic
│   │   ├── session_service.py       # Session management
│   │   ├── email_service.py         # Email notifications (Resend)
│   │   └── monitoring_service.py    # Application monitoring
│   │
│   ├── middleware/                  # Custom middleware
│   │   ├── __init__.py
│   │   └── auth.py                  # JWT verification middleware
│   │
│   ├── models/                      # Database models (if using ORM)
│   │   └── __init__.py
│   │
│   ├── static/                      # Static assets
│   │   ├── robots.txt               # SEO robots file
│   │   ├── sitemap.xml              # SEO sitemap
│   │   └── js/
│   │       └── widget.js            # Production widget (served from here)
│   │
│   └── templates/                   # Server-side templates (if needed)
│       └── __init__.py
│
├── frontend/                        # Frontend assets
│   ├── index.html                   # Premium landing page (Linear/Stripe design)
│   ├── css/
│   │   └── main.css                 # Legacy styles (being phased out)
│   └── js/
│       ├── auth.js                  # Authentication logic (login/register)
│       ├── dashboard.js             # Dashboard functionality
│       └── widget.js                # Embeddable chat widget (source)
│
├── database/                        # Database schemas
│   ├── schema.sql                   # Complete database schema
│   └── rls_policies.sql             # Row Level Security policies
│
├── wordpress-plugin/                # WordPress integration
│   ├── conversapay-chat.php         # Main plugin file
│   └── README.md                    # Plugin documentation
│
├── conversapay-site-builder/        # AI Website Builder (separate service)
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── config.py                # Site builder configuration
│   │   ├── main.py                  # FastAPI app for site builder
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── generator.py         # AI site generation endpoint
│   ├── frontend/
│   │   └── index.html               # Site builder wizard UI
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── home.html                        # Landing page (served at root)
├── dashboard.html                   # Main dashboard (analytics, orders, products)
├── login.html                       # Login page (premium dark theme)
├── register.html                    # Registration page (premium dark theme)
├── pay.html                         # Stripe payment page
│
└── PROJECT_MAP.md                   # This file - complete architecture guide
```

---

## 🏗️ Architecture Deep Dive

### 1. **Request Flow: Multi-Tenant SaaS**

```
User Request
    ↓
main.py (FastAPI App)
    ↓
DualCORSMiddleware (CORS validation)
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
2. Frontend (auth.js) → POST /api/v1/auth/login
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

### 3. **AI Chat Flow**

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
6. gemini_service.py processes with Gemini AI
   ↓
7. AI determines intent (product inquiry, checkout, etc.)
   ↓
8. If checkout: Returns payment_url from Stripe
   ↓
9. Widget displays response with payment button
   ↓
10. Customer completes payment
    ↓
11. Webhook updates order status
```

### 4. **Dashboard Analytics Flow**

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
- Initializes FastAPI app
- Configures dual-tier CORS middleware
- Registers all routers
- Serves static HTML pages
- Handles errors
- **Key Sections:**
  - `lifespan()`: Startup/shutdown events
  - `DualCORSMiddleware`: Widget vs Dashboard CORS
  - Router registration: All API endpoints
  - Static file mounting: `/static` and `/frontend`

#### `requirements.txt`
**Purpose:** Python dependencies
- FastAPI, uvicorn, pydantic
- Supabase client
- Google Generative AI
- Stripe SDK
- Resend (email)
- python-dotenv

#### `.env.example`
**Purpose:** Environment variables template
- Supabase credentials
- API keys (Gemini, Stripe, Resend)
- CORS origins
- Environment flags

---

### **Backend Core**

#### `backend/config.py`
**Purpose:** Centralized configuration
- Loads environment variables
- Provides settings object
- API keys, database URLs, CORS origins
- Environment detection (dev/prod)

#### `backend/routers/auth.py`
**Purpose:** Authentication endpoints
- `POST /api/v1/auth/register`: User registration
- `POST /api/v1/auth/login`: User login (returns JWT)
- `POST /api/v1/auth/logout`: Session invalidation
- `GET /api/v1/auth/me`: Get current user
- Uses Supabase Auth for JWT management

#### `backend/routers/businesses.py`
**Purpose:** Business management
- `GET /api/v1/businesses`: List user's businesses
- `POST /api/v1/businesses`: Create new business
- `GET /api/v1/businesses/{id}`: Get business details
- `PUT /api/v1/businesses/{id}`: Update business
- `DELETE /api/v1/businesses/{id}`: Delete business
- Multi-tenant: Each user can have multiple businesses

#### `backend/routers/products.py`
**Purpose:** Product catalog management
- `GET /api/v1/products`: List products (with filters)
- `POST /api/v1/products`: Create product
- `PUT /api/v1/products/{id}`: Update product
- `DELETE /api/v1/products/{id}`: Delete product
- Fields: name, price, description, image_url, is_active

#### `backend/routers/chat.py`
**Purpose:** AI chat endpoint
- `POST /api/v1/chat`: Send message to AI
- Integrates with Gemini API
- Determines user intent (product inquiry, checkout, etc.)
- Returns AI response + optional payment_url
- Creates/updates chat sessions
- Logs conversations for analytics

#### `backend/routers/orders.py`
**Purpose:** Order management
- `GET /api/v1/orders`: List orders (with filters)
- `GET /api/v1/orders/{id}`: Get order details
- `POST /api/v1/orders`: Create order (from chat)
- `PUT /api/v1/orders/{id}/status`: Update status
- `GET /api/v1/orders/summary`: Analytics summary
- Statuses: pending, paid, processing, shipped, delivered, canceled, refunded

#### `backend/routers/payments.py`
**Purpose:** Payment processing
- `POST /api/v1/payments/create-checkout-session`: Create Stripe session
- `POST /api/v1/payments/webhook`: Stripe webhook handler
- `GET /api/v1/payments/profile`: Get subscription status
- `GET /api/v1/payments/wordpress-plugin/{business_id}`: Download WP plugin
- Handles Pro subscription ($29/month)

#### `backend/routers/analytics.py`
**Purpose:** Business analytics
- `GET /api/v1/analytics/businesses/{id}/analytics`: KPI metrics
- `GET /api/v1/analytics/businesses/{id}/revenue`: Revenue over time
- `GET /api/v1/analytics/businesses/{id}/orders`: Order analytics
- Metrics: total_revenue, conversion_rate, average_order_value, unique_sessions

#### `backend/routers/widget.py`
**Purpose:** Public widget configuration
- `GET /api/v1/widget/config/{business_id}`: Get bot config
- **Security:** Validates requesting domain against whitelist
- Returns: bot_name, greeting, theme_colors, features
- No sensitive data exposed

#### `backend/routers/generator.py`
**Purpose:** AI website builder (conversapay-site-builder)
- `POST /api/v1/builder/generate`: Generate website with AI
- Uses Gemini to create JSON config
- Renders HTML from config
- Returns complete landing page

#### `backend/services/gemini_service.py`
**Purpose:** Gemini AI integration
- Sends prompts to Gemini API
- Parses AI responses
- Determines user intent
- Extracts product recommendations
- Handles checkout intents

#### `backend/services/payment_service.py`
**Purpose:** Stripe payment logic
- Creates checkout sessions
- Handles webhooks
- Manages subscriptions
- Processes refunds

#### `backend/services/email_service.py`
**Purpose:** Email notifications
- Sends order confirmations
- Sends payment receipts
- Sends admin notifications
- Uses Resend API

#### `backend/middleware/auth.py`
**Purpose:** JWT authentication middleware
- Verifies JWT tokens
- Extracts user info
- Attaches user to request state
- Returns 401 if invalid

---

### **Frontend Files**

#### `frontend/index.html`
**Purpose:** Premium landing page
- Linear/Stripe dark aesthetic (#0B0F19)
- Hero section with gradient text
- Features grid with hover animations
- Pricing section (Free Sandbox vs Pro)
- How It Works section
- Fully self-contained (inline styles)
- Navigation to login/register

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
**Purpose:** Complete database structure
- **Tables:**
  - `users`: User accounts (Supabase Auth)
  - `businesses`: Business profiles
  - `products`: Product catalog
  - `orders`: Order records
  - `order_items`: Line items
  - `chat_sessions`: Conversation tracking
  - `chat_messages`: Message history
  - `payments`: Payment records
  - `subscriptions`: Pro plan management
  - `allowed_domains`: Widget security

#### `database/rls_policies.sql`
**Purpose:** Row Level Security
- Multi-tenant data isolation
- Users can only access their own businesses
- Business owners can manage their products/orders
- Public read access for widget config
- Admin override capabilities

---

## 🔐 Security Architecture

### **Authentication**
- JWT tokens via Supabase Auth
- Middleware validates on every request
- Tokens stored in localStorage
- Auto-logout on 401

### **Authorization**
- Row Level Security (RLS) in database
- Business ownership validation
- Role-based access (owner, admin, viewer)

### **Widget Security**
- Domain whitelist validation
- Origin/Referer header checking
- 403 Forbidden for unauthorized domains
- No private keys in public responses

### **CORS Policy**
- **Widget endpoints:** `*` (any origin)
- **Dashboard endpoints:** Configured origins only
- Credentials only for trusted origins

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
   ↓
3. User logs in (login.html)
   ↓
4. POST /api/v1/auth/login → JWT token
   ↓
5. Dashboard loads (dashboard.html)
   ↓
6. No business → Show "Create Business" form
   ↓
7. POST /api/v1/businesses
   ↓
8. No website → Show AI Site Builder onboarding
   ↓
9. User generates site (site-builder)
   ↓
10. Business now has website_url
    ↓
11. Dashboard shows analytics
    ↓
12. User adds products (dashboard.html)
    ↓
13. POST /api/v1/products
    ↓
14. Customer visits website
    ↓
15. Widget loads (widget.js)
    ↓
16. Customer chats → POST /api/v1/chat
    ↓
17. AI suggests products
    ↓
18. Customer clicks buy
    ↓
19. POST /api/v1/orders
    ↓
20. Stripe checkout session created
    ↓
21. Customer pays
    ↓
22. Webhook updates order status
    ↓
23. Dashboard shows new order + revenue
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
│  │   (Port 8000)│  │  (HTML/JS)  │ │
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
   │  Gemini  │      │    Stripe    │
   │   API    │      │     API      │
   └──────────┘      └──────────────┘
```

### **Environment Variables**
```env
# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJxxx...

# AI
GEMINI_API_KEY=AIzaSy...

# Payments
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email
RESEND_API_KEY=re_...

# App
ENVIRONMENT=production
DEBUG=false
API_PREFIX=/api/v1
CORS_ORIGINS=https://conversapay.org,https://app.conversapay.org
```

---

## 📊 Database Schema Overview

### **Core Tables**

#### `users` (Supabase Auth)
- id (UUID)
- email
- encrypted_password
- email_confirmed_at
- last_sign_in_at

#### `businesses`
- id (UUID)
- user_id (FK to users)
- business_id (string, unique)
- business_name (string)
- description (text)
- website_url (string, nullable)
- allowed_domains (text[])
- bot_name (string)
- greeting_message (text)
- theme_colors (jsonb)
- is_pro (boolean)
- created_at
- updated_at

#### `products`
- id (UUID)
- business_id (FK to businesses)
- item_key (string)
- name (string)
- description (text)
- price (decimal)
- image_url (string)
- is_active (boolean)
- created_at
- updated_at

#### `orders`
- id (UUID)
- business_id (FK to businesses)
- order_number (string, unique)
- customer_info (jsonb)
- items (jsonb)
- total (decimal)
- status (enum: pending, paid, processing, shipped, delivered, canceled, refunded)
- stripe_session_id (string)
- created_at
- updated_at

#### `chat_sessions`
- id (UUID)
- business_id (FK to businesses)
- session_id (string, unique)
- customer_info (jsonb)
- started_at
- last_activity

#### `chat_messages`
- id (UUID)
- session_id (FK to chat_sessions)
- sender (enum: user, bot)
- message (text)
- intent (string)
- metadata (jsonb)
- created_at

---

## 🔌 API Endpoints Reference

### **Authentication**
- `POST /api/v1/auth/register` - Register user
- `POST /api/v1/auth/login` - Login user
- `POST /api/v1/auth/logout` - Logout user
- `GET /api/v1/auth/me` - Get current user

### **Businesses**
- `GET /api/v1/businesses` - List businesses
- `POST /api/v1/businesses` - Create business
- `GET /api/v1/businesses/{id}` - Get business
- `PUT /api/v1/businesses/{id}` - Update business
- `DELETE /api/v1/businesses/{id}` - Delete business

### **Products**
- `GET /api/v1/products` - List products
- `POST /api/v1/products` - Create product
- `PUT /api/v1/products/{id}` - Update product
- `DELETE /api/v1/products/{id}` - Delete product

### **Chat**
- `POST /api/v1/chat` - Send message to AI
- `GET /api/v1/chat/sessions` - List chat sessions
- `GET /api/v1/chat/sessions/{id}/messages` - Get messages

### **Orders**
- `GET /api/v1/orders` - List orders
- `GET /api/v1/orders/{id}` - Get order details
- `POST /api/v1/orders` - Create order
- `PUT /api/v1/orders/{id}/status` - Update status

### **Payments**
- `POST /api/v1/payments/create-checkout-session` - Create Stripe session
- `POST /api/v1/payments/webhook` - Stripe webhook
- `GET /api/v1/payments/profile` - Get subscription status
- `GET /api/v1/payments/wordpress-plugin/{business_id}` - Download WP plugin

### **Analytics**
- `GET /api/v1/analytics/businesses/{id}/analytics` - Get KPIs
- `GET /api/v1/analytics/businesses/{id}/revenue` - Revenue data
- `GET /api/v1/analytics/businesses/{id}/orders` - Order analytics

### **Widget (Public)**
- `GET /api/v1/widget/config/{business_id}` - Get widget config

### **Website Builder**
- `POST /api/v1/builder/generate` - Generate website with AI

---

## 🧪 Testing Strategy

### **Unit Tests**
- Router tests (each endpoint)
- Service tests (business logic)
- Middleware tests (auth, CORS)
- Utility function tests

### **Integration Tests**
- Full chat flow (message → AI → response)
- Payment flow (checkout → webhook → order update)
- Authentication flow (register → login → protected route)
- Widget embedding (domain validation)

### **E2E Tests**
- User registration → business creation → product addition → customer chat → purchase
- WordPress plugin installation → widget appearance → chat → payment

---

## 📈 Scalability Considerations

### **Current Architecture**
- Single FastAPI instance
- Supabase for database (managed PostgreSQL)
- Stateless API (can scale horizontally)
- Static files served by FastAPI (can move to CDN)

### **Future Scaling**
1. **Load Balancer:** Multiple FastAPI instances behind Nginx
2. **CDN:** Cloudflare for static assets
3. **Redis:** Session caching, rate limiting
4. **Queue:** Celery for async tasks (emails, webhooks)
5. **Monitoring:** Prometheus + Grafana
6. **Logging:** Structured logging to ELK stack

---

## 🛠️ Development Workflow

### **Local Development**
```bash
# 1. Clone repository
git clone <repo-url>
cd conversapay-project

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Run database migrations
# (Supabase SQL editor or psql)

# 6. Start server
python main.py
# OR
uvicorn main:app --reload --port 8000

# 7. Access application
# Frontend: http://localhost:8000
# API Docs: http://localhost:8000/docs
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

---

## 🔍 Key Configuration Points

### **For New Developers**
1. Read `PROJECT_MAP.md` (this file)
2. Set up `.env` with Supabase credentials
3. Run database migrations from `database/schema.sql`
4. Start server with `python main.py`
5. Explore API at `/docs`
6. Test chat flow with widget.js

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

**Last Updated:** 2026-07-18
**Version:** 2.0.0
**Status:** Production Ready ✅