-- Admin management schema. Run once in Supabase.
CREATE TABLE IF NOT EXISTS admin_users (
 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), email VARCHAR(255) UNIQUE NOT NULL,
 username TEXT, password_hash VARCHAR(255) NOT NULL, full_name VARCHAR(255),
 role VARCHAR(50) NOT NULL CHECK (role IN ('super_admin','admin','moderator')),
 status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active','inactive','suspended')),
 last_login TIMESTAMPTZ, login_attempts INTEGER DEFAULT 0, locked_until TIMESTAMPTZ,
 two_factor_enabled BOOLEAN DEFAULT false, two_factor_secret VARCHAR(255),
 permissions JSONB DEFAULT '{}', metadata JSONB DEFAULT '{}',
 created_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL,
 updated_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL
);
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS username TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key ON admin_users (lower(username)) WHERE username IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_admin_users_status ON admin_users(status);
CREATE INDEX IF NOT EXISTS idx_admin_users_role ON admin_users(role);

CREATE TABLE IF NOT EXISTS domain_restrictions (
 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
 domain VARCHAR(255) NOT NULL, installation_id UUID REFERENCES installations(id) ON DELETE SET NULL,
 status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active','blocked','flagged','warning')),
 reason_for_status TEXT, max_domains_allowed INTEGER DEFAULT 1, current_domain_count INTEGER DEFAULT 0,
 monthly_api_calls_limit INTEGER DEFAULT 100000, current_monthly_api_calls INTEGER DEFAULT 0,
 monthly_reset_date DATE, blocked_at TIMESTAMPTZ, blocked_by_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
 metadata JSONB DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL,
 updated_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_domain_restrictions_business_id ON domain_restrictions(business_id);
CREATE INDEX IF NOT EXISTS idx_domain_restrictions_status ON domain_restrictions(status);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), admin_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
 action VARCHAR(100) NOT NULL, resource_type VARCHAR(50), resource_id VARCHAR(255), business_id UUID REFERENCES businesses(id) ON DELETE SET NULL,
 details JSONB DEFAULT '{}', ip_address INET, user_agent TEXT, created_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_logs (id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, domain VARCHAR(255), endpoint VARCHAR(255), method VARCHAR(10), status_code INTEGER, response_time_ms INTEGER, tokens_used INTEGER DEFAULT 0, cost_usd DECIMAL(10,4) DEFAULT 0, user_agent TEXT, ip_address INET, created_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL);
CREATE TABLE IF NOT EXISTS abuse_reports (id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, domain VARCHAR(255), report_type VARCHAR(50) NOT NULL, severity VARCHAR(50) DEFAULT 'medium', description TEXT NOT NULL, evidence JSONB DEFAULT '{}', status VARCHAR(50) DEFAULT 'open', assigned_to_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL, resolution_notes TEXT, resolved_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL, updated_at TIMESTAMPTZ DEFAULT timezone('utc',now()) NOT NULL);
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE domain_restrictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE abuse_reports ENABLE ROW LEVEL SECURITY;
