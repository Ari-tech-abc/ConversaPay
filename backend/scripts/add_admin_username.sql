-- Add a username column to admin_users so administrators can log in
-- with a fixed username instead of (or in addition to) their email.
-- Safe to run multiple times.

ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS username TEXT;

-- Case-insensitive uniqueness on username (ignores NULLs).
CREATE UNIQUE INDEX IF NOT EXISTS admin_users_username_lower_key
    ON admin_users (LOWER(username))
    WHERE username IS NOT NULL;
