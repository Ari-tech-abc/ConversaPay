-- ============================================
-- Team Management Tables
-- Allows business owners to invite team members
-- ============================================

-- Create team_members table
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(user_id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'manager', 'viewer')),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'inactive', 'removed')),
    invitation_token VARCHAR(255) UNIQUE,
    invitation_expires_at TIMESTAMP WITH TIME ZONE,
    joined_at TIMESTAMP WITH TIME ZONE,
    permissions JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE(business_id, email)
);

-- Create indexes
CREATE INDEX idx_team_members_business_id ON team_members(business_id);
CREATE INDEX idx_team_members_user_id ON team_members(user_id);
CREATE INDEX idx_team_members_email ON team_members(email);
CREATE INDEX idx_team_members_status ON team_members(status);
CREATE INDEX idx_team_members_invitation_token ON team_members(invitation_token);

-- Create trigger for updated_at
CREATE TRIGGER update_team_members_updated_at BEFORE UPDATE ON team_members FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS for team_members
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;

-- Business owners can view their team members
CREATE POLICY "Owners can view their team members"
ON team_members FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Team members can view other team members in their business
CREATE POLICY "Team members can view other team members"
ON team_members FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM team_members tm
        JOIN businesses b ON b.id = tm.business_id
        WHERE tm.business_id = team_members.business_id
        AND tm.user_id = auth.uid()
        AND tm.status = 'active'
    )
);

-- Owners can create team members
CREATE POLICY "Owners can create team members"
ON team_members FOR INSERT
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Owners can update team members
CREATE POLICY "Owners can update team members"
ON team_members FOR UPDATE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
        AND businesses.owner_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Owners can delete team members
CREATE POLICY "Owners can delete team members"
ON team_members FOR DELETE
USING (
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = team_members.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- Update businesses table to track team size
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS team_size INTEGER DEFAULT 1;

-- Create activity_logs table for tracking who accessed what
CREATE TABLE IF NOT EXISTS activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(user_id) ON DELETE SET NULL,
    team_member_id UUID REFERENCES team_members(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Create indexes for activity_logs
CREATE INDEX idx_activity_logs_business_id ON activity_logs(business_id);
CREATE INDEX idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX idx_activity_logs_created_at ON activity_logs(created_at);

-- Enable RLS for activity_logs
ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

-- Team members can view activity logs for their business
CREATE POLICY "Team members can view activity logs"
ON activity_logs FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM team_members
        WHERE team_members.business_id = activity_logs.business_id
        AND team_members.user_id = auth.uid()
        AND team_members.status = 'active'
    )
    OR
    EXISTS (
        SELECT 1 FROM businesses
        WHERE businesses.id = activity_logs.business_id
        AND businesses.owner_id = auth.uid()
    )
);

-- System can create activity logs
CREATE POLICY "System can create activity logs"
ON activity_logs FOR INSERT
WITH CHECK (true);
