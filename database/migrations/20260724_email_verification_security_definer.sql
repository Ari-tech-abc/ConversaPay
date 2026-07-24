-- Email verification hardening
--
-- The /api/v1/auth/verify endpoint is unauthenticated (it only carries a
-- verification token in the URL) and updates the profiles row using the
-- backend service client. If the deployed SUPABASE_SERVICE_ROLE_KEY is not the
-- real service_role secret (e.g. the anon key was pasted instead), the UPDATE
-- silently matches 0 rows under RLS: PostgREST returns 200 but email_verified
-- stays false, and the endpoint raises "Failed to verify email" (HTTP 500).
--
-- This SECURITY DEFINER function runs as its owner, so it marks the row
-- verified regardless of the caller's role/RLS. It is idempotent and only
-- touches the single profile matched by user_id.

CREATE OR REPLACE FUNCTION public.mark_email_verified(p_user_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_verified boolean;
BEGIN
    UPDATE profiles
    SET email_verified = true,
        email_verification_token = NULL,
        email_verification_expires_at = NULL
    WHERE user_id = p_user_id
    RETURNING email_verified INTO v_verified;

    RETURN COALESCE(v_verified, false);
END;
$$;

GRANT EXECUTE ON FUNCTION public.mark_email_verified(uuid) TO anon, authenticated, service_role;
