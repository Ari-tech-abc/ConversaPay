# ConversaPay - Production Architecture

## Overview
ConversaPay is a multi-tenant SaaS platform that transforms websites into AI-powered sales machines. The platform combines AI chatbot capabilities, payment processing, analytics, and multi-channel support (web, WhatsApp) for businesses.

**Version:** 2.0.0  
**Last Updated:** 2026-07-21  
**Status:** Production Ready ✅

---

## 1. Technology Stack

### Backend
- **Framework:** FastAPI 0.139.0
- **Server:** Uvicorn 0.51.0
- **Language:** Python 3.11+
- **Configuration:** Pydantic Settings + python-dotenv

### Database & Auth
- **Database:** Supabase (PostgreSQL)
- **Authentication:** Supabase Auth (JWT)
- **Row Level Security:** Enabled on all tables

### AI & Services
- **AI Engine:** Google Gemini API
- **Email Service:** Resend SDK
- **Payment Gateway:** PayMe (Israeli) + Stripe (legacy)
- **WhatsApp:** Meta WhatsApp Cloud API

### Frontend
- **Technology:** Vanilla JavaScript, HTML/CSS
- **Design:** Linear/Stripe dark theme with glass morphism
- **Charts:** Chart.js for analytics visualization

---

## 2. System Architecture

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    Render.com Platform                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  FastAPI Backend (main.py)                            │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Routers (14 endpoints)                         │  │  │
│  │  │  - auth, businesses, products, chat, orders     │  │  │
│  │  │  - payments, analytics, logs, webhooks           │  │  │
│  │  │  - widget, payme_webhook, whatsapp_webhook       │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Services (6 services)                          │  │  │
│  │  │  - gemini_service, payme_service                │  │  │
│  │  │  - email_service, session_service                │  │  │
│  │  │  - product_service, monitoring_service           │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Middleware                                      │  │  │
│  │  │  - DualCORSMiddleware (widget vs dashboard)      │  │  │
│  │  │  - RateLimiter (chat endpoint protection)        │  │  │
│  │  │  - Auth middleware (JWT validation)              │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
          ↓                    ↓                    ↓
     ┌─────────┐      ┌──────────────┐      ┌──────────┐
     │ Supabase │      │    PayMe     │      │  Gemini  │
     │ Database │      │   Payments   │      │    AI    │
     └─────────┘      └──────────────┘      └──────────┘
          ↓                    ↓                    ↓
     ┌─────────────┐    ┌──────────┐      ┌──────────────┐
     │   Resend     │    │ Stripe   │      │   WhatsApp   │
     │ Email Service│    │(legacy)  │      │  Cloud API   │
     └─────────────┘    └──────────┘      └──────────────┘
```

### Request Flow
```
Client Request
    ↓
DualCORSMiddleware (CORS validation based on endpoint type)
    ↓
RateLimiter (for public endpoints like chat)
    ↓
Auth Middleware (JWT validation for protected routes)
    ↓
Router (auth/businesses/chat/etc.)
    ↓
Service Layer (business logic)
    ↓
Supabase Database (PostgreSQL with RLS)
    ↓
Response
```

---

## 3. Project Structure

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
│   ├── config.py                    # Configuration settings
│   │
│   ├── routers/                     # API route handlers (14 routers)
│   │   ├── __init__.py
│   │   ├── auth.py                  # Authentication (register, login, verify)
│   │   ├── businesses.py            # Business CRUD operations
│   │   ├── products.py              # Product management
│   │   ├── chat.py                  # AI chat endpoint (Gemini)
│   │   ├── orders.py                # Order management & tracking
│   │   ├── payments.py              # Payment processing (Stripe legacy)
│   │   ├── payme_webhook.py         # PayMe webhook handler (NEW)
│   │   ├── whatsapp.py              # WhatsApp webhook handler (NEW)
│   │   ├── analytics.py             # Business analytics & metrics
│   │   ├── logs.py                  # Activity logging
│   │   ├── webhooks.py              # Generic webhook handlers
│   │   ├── widget.py                # Public widget config endpoint
│   │   └── dev_simulator.py         # Dev-only payment simulator
│   │
│   ├── services/                    # Business logic layer (6 services)
│   │   ├── __init__.py
│   │   ├── gemini_service.py        # Gemini AI integration
│   │   ├── payme_service.py         # PayMe payment logic (NEW)
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
│       ├── auth.js                  # Authentication logic
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
├── dashboard.html                   # Main dashboard (analytics, orders)
├── login.html                       # Login page
├── register.html                    # Registration page
├── pay.html                         # Payment simulator page
├── index.html                       # Sandbox chat preview
│
├── ARCHITECTURE.md                  # This file
├── PROJECT_MAP.md                   # Detailed project map
└── README.md                        # Project readme
```

---

## 4. Database Schema

### Core Tables (13 tables)

#### 1. profiles
User subscription status and profile information
- `user_id` (UUID, FK to Supabase Auth)
- `email`, `full_name`, `role`
- `is_pro` (boolean), `plan_type` (free/pro/premium)
- `subscription_expires_at`, `stripe_customer_id`, `stripe_subscription_id`
- **WhatsApp Premium fields:** `whatsapp_phone_number_id`, `whatsapp_access_token`, `whatsapp_verify_token`
- **Email verification fields:** `email_verified`, `email_verification_token`, `email_verification_expires_at`

#### 2. businesses
Tenant root table - each user can have multiple businesses
- `business_id` (string, unique), `business_name`, `description`
- `owner_id` (UUID, FK to profiles)
- `subscription_tier`, `subscription_status`
- `settings` (JSONB), `bot_name`, `greeting_message`, `theme_colors`
- `is_active` (boolean)

#### 3. products
Product catalog for each business
- `business_id` (UUID, FK), `item_key` (string, unique per business)
- `name`, `description`, `price`, `currency` (default ILS)
- `image_url`, `is_active`, `inventory_count` (-1 = unlimited)
- `metadata` (JSONB)

#### 4. customers
Customer database for each business
- `business_id` (UUID, FK), `email`, `phone`, `name`
- `total_purchases`, `purchase_count`, `last_purchase_at`
- `metadata` (JSONB)

#### 5. conversations
Chat session tracking
- `business_id` (UUID, FK), `customer_id` (UUID, FK, nullable)
- `session_id` (string, unique), `channel` (web/whatsapp/telegram/api)
- `status` (active/closed/archived), `started_at`, `ended_at`
- `metadata` (JSONB)

#### 6. messages
Individual chat messages
- `conversation_id` (UUID, FK), `role` (user/assistant/system)
- `content` (text), `intent` (string), `metadata` (JSONB)

#### 7. orders
Order records
- `business_id` (UUID, FK), `customer_id` (UUID, FK, nullable)
- `conversation_id` (UUID, FK, nullable)
- `order_number` (string, unique), `status`, `payment_status`
- `subtotal`, `tax`, `total`, `currency` (default ILS)
- `items` (JSONB array), `customer_info` (JSONB), `shipping_address` (JSONB)

#### 8. payments
Payment transaction records
- `business_id` (UUID, FK), `order_id` (UUID, FK, nullable)
- `stripe_payment_intent_id`, `stripe_session_id`
- `amount`, `currency`, `status`, `payment_method`
- `customer_email`, `customer_name`, `metadata` (JSONB)
- `paid_at`

#### 9. subscriptions
Subscription management (Stripe-based)
- `business_id` (UUID, FK)
- `stripe_subscription_id`, `stripe_price_id`
- `tier` (free/pro/enterprise), `status`
- `current_period_start`, `current_period_end`, `cancel_at_period_end`

#### 10. api_keys
API key management for programmatic access
- `business_id` (UUID, FK), `name`, `key_hash`, `key_prefix`
- `permissions` (JSONB array), `last_used_at`, `expires_at`, `is_active`

#### 11. webhooks
Webhook configuration for event notifications
- `business_id` (UUID, FK), `url`, `events` (JSONB array)
- `secret`, `is_active`, `last_triggered_at`, `failure_count`

#### 12. logs
Application logging
- `business_id` (UUID, FK, nullable), `level`, `source`, `message`
- `details` (JSONB), `user_agent`, `ip_address` (INET)

#### 13. email_templates
Customizable email templates
- `business_id` (UUID, FK, nullable), `template_type`
- `subject`, `body_html`, `body_text`, `is_active`

### Security Features
- **Row Level Security (RLS):** Enabled on all tables
- **Multi-tenant isolation:** Users can only access their own businesses
- **Subscription field protection:** Database trigger prevents unauthorized updates
- **Updated_at triggers:** Automatic timestamp updates on all tables

---

## 5. API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user with email verification
- `POST /login` - Login user (returns JWT)
- `POST /logout` - Logout user
- `GET /me` - Get current user profile
- `GET /verify` - Email verification endpoint

### Businesses (`/api/v1/businesses`)
- `GET /` - List user's businesses
- `POST /` - Create new business
- `GET /{id}` - Get business details
- `PUT /{id}` - Update business
- `DELETE /{id}` - Delete business

### Products (`/api/v1/products`)
- `GET /` - List products (with filters)
- `POST /` - Create product
- `PUT /{id}` - Update product
- `DELETE /{id}` - Delete product

### Chat (`/api/v1/chat`)
- `POST /` - Send message to AI (Gemini)
- `GET /sessions` - List chat sessions
- `GET /sessions/{id}/messages` - Get messages

### Orders (`/api/v1/orders`)
- `GET /` - List orders (with filters)
- `GET /{id}` - Get order details
- `POST /` - Create order
- `PUT /{id}/status` - Update order status
- `GET /summary` - Analytics summary

### Payments (`/api/v1/payments`)
- `POST /create-checkout-session` - Create Stripe session (legacy)
- `POST /webhook` - Stripe webhook handler
- `GET /profile` - Get subscription status
- `GET /wordpress-plugin/{business_id}` - Download WP plugin

### PayMe Webhooks (`/api/v1/webhooks/payme`)
- `POST /` - PayMe IPN handler (instant payment notifications)

### WhatsApp Webhooks (`/api/v1/webhooks/whatsapp`)
- `GET /` - Meta webhook verification
- `POST /` - WhatsApp message handler (Premium tier only)

### Analytics (`/api/v1/analytics`)
- `GET /businesses/{id}/analytics` - KPI metrics
- `GET /businesses/{id}/revenue` - Revenue over time
- `GET /businesses/{id}/orders` - Order analytics

### Widget (Public) (`/api/v1/widget`)
- `GET /config/{business_id}` - Get widget config (domain-validated)

### Website Builder (`/api/v1/builder`)
- `POST /generate` - Generate website with AI (Gemini)

### Logs (`/api/v1/logs`)
- `GET /` - List logs
- `POST /` - Create log entry

### Health Check
- `GET /health` - Application health status

---

## 6. Key Features

### Multi-Tier Subscription Model
- **Free Tier:** Basic chatbot, limited features
- **Pro Tier (₪200/month):** Full chatbot, analytics, WordPress plugin
- **Premium Tier (₪350/month):** Pro features + WhatsApp Business integration

### Dual Payment Gateway Support
- **PayMe (Primary):** Israeli payment gateway with hosted payment pages
  - Supports recurring billing (הוראת קבע)
  - 2-tier pricing: Pro (₪200) and Premium (₪350)
  - Webhook-based subscription activation
- **Stripe (Legacy):** Being phased out, maintained for backward compatibility

### Multi-Channel Support
- **Web Chat:** Embedded widget on business websites
- **WhatsApp:** Premium tier only, requires Meta Business API setup
- **API:** Direct API access for custom integrations

### AI-Powered Features
- **Gemini Integration:** Intent detection, product recommendations, checkout flows
- **Session Management:** Database-backed conversation history
- **Product Search:** Intelligent semantic and keyword matching
- **Context-Aware:** Customer history, purchase behavior, recent orders

### Security
- **JWT Authentication:** Supabase Auth with middleware validation
- **Rate Limiting:** In-memory token bucket for public endpoints
- **CORS:** Dual-tier policy (widget: *, dashboard: configured origins)
- **RLS:** Multi-tenant data isolation at database level
- **Domain Validation:** Widget config endpoint validates requesting domain

---

## 7. Configuration

### Environment Variables
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

## 8. Deployment

### Production (Render)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main.py`
- **Port:** Dynamic (`$PORT` environment variable)
- **Health Check:** `/health` endpoint

### Site Builder (Separate Service)
- **Port:** 8001
- **Start Command:** `cd conversapay-site-builder && python backend/main.py`
- **Purpose:** AI-powered website generation

### Environment Setup
1. Set all environment variables in Render dashboard
2. Run database migrations from `database/schema.sql`
3. Configure PayMe webhook URL: `https://your-domain.com/api/v1/webhooks/payme`
4. Configure WhatsApp webhook (Premium tier only)

---

## 9. Recent Updates (2026-07-21)

### New Features
- ✅ **PayMe Integration:** Primary Israeli payment gateway with recurring billing
- ✅ **WhatsApp Webhook:** Premium tier WhatsApp Business integration
- ✅ **Rate Limiting:** Protection for public chat endpoints
- ✅ **Session Service:** Database-backed conversation management
- ✅ **Product Service:** Intelligent product search and matching
- ✅ **Email Verification:** User registration with email confirmation
- ✅ **Dual CORS Middleware:** Separate policies for widget vs dashboard

### Architecture Changes
- Migrated from Stripe-only to PayMe (primary) + Stripe (legacy)
- Added WhatsApp as premium channel alongside web chat
- Implemented database-backed sessions (replaced in-memory storage)
- Added rate limiting for public API endpoints
- Enhanced security with subscription field protection triggers

---

## 10. Development Workflow

### Local Development
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
# Edit .env with your Supabase and API credentials

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

### Testing
```bash
# API Documentation
http://localhost:8000/docs

# Health Check
http://localhost:8000/health

# Test Chat Flow
1. Register at /register.html
2. Login at /login.html
3. Create business in dashboard
4. Test widget chat
```

---

## 11. Monitoring & Logging

### Logging Points
- User registration and authentication events
- Payment processing (PayMe/Stripe)
- Webhook processing (PayMe, WhatsApp, Stripe)
- AI chat interactions and intent detection
- Database errors and performance issues
- Rate limit violations

### Monitoring
- Application startup/shutdown events
- Configuration validation on startup
- External service health (PayMe, Gemini, Resend)
- Database connection health
- Rate limiter statistics

---

## Status: ✅ PRODUCTION READY

All core features are implemented and tested. The platform is ready for deployment with PayMe as the primary payment gateway and WhatsApp as the premium communication channel.

**Platform:** Render + Supabase + PayMe + Gemini + Resend + WhatsApp