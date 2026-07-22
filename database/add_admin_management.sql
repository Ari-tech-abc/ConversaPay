-- ============================================
-- Admin Management Tables
-- For ConversaPay administrators only
-- ============================================

-- Create admin_users table (separate from regular users)
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL CHECK (role IN ('super_admin', 'admin', 'moderator')),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    last_login TIMESTAMP WITH TIME ZONE,
    login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    two_factor_enabled BOOLEAN DEFAULT false,
    two_factor_secret VARCHAR(255),
    permissions JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes
CREATE INDEX idx_admin_users_email ON admin_users(email);
CREATE INDEX idx_admin_users_status ON admin_users(status);
CREATE INDEX idx_admin_users_role ON admin_users(role);

-- Create trigger for updated_at
CREATE TRIGGER update_admin_users_updated_at BEFORE UPDATE ON admin_users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create domain_restrictions table
CREATE TABLE IF NOT EXISTS domain_restrictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    installation_id UUID REFERENCES installations(id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'flagged', 'warning')),
    reason_for_status TEXT,
    max_domains_allowed INTEGER DEFAULT 1,
    current_domain_count INTEGER DEFAULT 0,
    monthly_api_calls_limit INTEGER DEFAULT 100000,
    current_monthly_api_calls INTEGER DEFAULT 0,
    monthly_reset_date DATE,
    blocked_at TIMESTAMP WITH TIME ZONE,
    blocked_by_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes
CREATE INDEX idx_domain_restrictions_business_id ON domain_restrictions(business_id);
CREATE INDEX idx_domain_restrictions_domain ON domain_restrictions(domain);
CREATE INDEX idx_domain_restrictions_status ON domain_restrictions(status);
CREATE INDEX idx_domain_restrictions_created_at ON domain_restrictions(created_at);

-- Create trigger
CREATE TRIGGER update_domain_restrictions_updated_at BEFORE UPDATE ON domain_restrictions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create usage_logs table (track API calls per business)
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER,
    tokens_used INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 4) DEFAULT 0,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes for usage_logs
CREATE INDEX idx_usage_logs_business_id ON usage_logs(business_id);
CREATE INDEX idx_usage_logs_domain ON usage_logs(domain);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at);

-- Create admin_audit_logs table (track admin actions)
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    business_id UUID REFERENCES businesses(id) ON DELETE SET NULL,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes
CREATE INDEX idx_admin_audit_logs_admin_id ON admin_audit_logs(admin_id);
CREATE INDEX idx_admin_audit_logs_action ON admin_audit_logs(action);
CREATE INDEX idx_admin_audit_logs_business_id ON admin_audit_logs(business_id);
CREATE INDEX idx_admin_audit_logs_created_at ON admin_audit_logs(created_at);

-- Create abuse_reports table
CREATE TABLE IF NOT EXISTS abuse_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    domain VARCHAR(255),
    report_type VARCHAR(50) NOT NULL CHECK (report_type IN ('domain_abuse', 'api_abuse', 'payment_fraud', 'other')),
    severity VARCHAR(50) DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description TEXT NOT NULL,
    evidence JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'dismissed')),
    assigned_to_admin_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    resolution_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes
CREATE INDEX idx_abuse_reports_business_id ON abuse_reports(business_id);
CREATE INDEX idx_abuse_reports_status ON abuse_reports(status);
CREATE INDEX idx_abuse_reports_severity ON abuse_reports(severity);
CREATE INDEX idx_abuse_reports_created_at ON abuse_reports(created_at);

-- Create trigger
CREATE TRIGGER update_abuse_reports_updated_at BEFORE UPDATE ON abuse_reports FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS for admin_users (no RLS - only backend access)
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;

-- Only admins can view admin_users (enforced in backend)
CREATE POLICY "Only admins can view admin users"
ON admin_users FOR SELECT
USING (false);

-- Enable RLS for domain_restrictions
ALTER TABLE domain_restrictions ENABLE ROW LEVEL SECURITY;

-- Only admins can view domain restrictions
CREATE POLICY "Only admins can view domain restrictions"
ON domain_restrictions FOR SELECT
USING (false);

-- Enable RLS for usage_logs
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;

-- Only admins can view usage logs
CREATE POLICY "Only admins can view usage logs"
ON usage_logs FOR SELECT
USING (false);

-- Enable RLS for admin_audit_logs
ALTER TABLE admin_audit_logs ENABLE ROW LEVEL SECURITY;

-- Only admins can view audit logs
CREATE POLICY "Only admins can view audit logs"
ON admin_audit_logs FOR SELECT
USING (false);

-- Enable RLS for abuse_reports
ALTER TABLE abuse_reports ENABLE ROW LEVEL SECURITY;

-- Only admins can view abuse reports
CREATE POLICY "Only admins can view abuse reports"
ON abuse_reports FOR SELECT
USING (false);
