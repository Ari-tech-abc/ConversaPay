-- Run after database/add_admin_management.sql. Safe to run repeatedly.
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS username TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key ON admin_users (LOWER(username)) WHERE username IS NOT NULL;
