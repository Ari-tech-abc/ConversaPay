-- Application data is accessed through the authenticated FastAPI endpoints.
-- Supabase Auth remains public; its public API key is not a data-access grant.
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'profiles','businesses','products','customers','conversations','messages',
        'orders','payments','api_keys','webhooks','logs','usage_logs','usage_events',
        'admin_users','admin_audit_logs','domain_restrictions','abuse_reports',
        'refund_requests','billing_dunning_attempts','webhook_events',
        'payment_webhook_events','payment_accounts','site_builder_tokens',
        'site_builder_projects','lead_submissions','site_lead_rate_limits',
        'schema_migrations'
    ] LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', table_name);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO service_role', table_name);
        END IF;
    END LOOP;
END $$;

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_access_token_encrypted TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_verify_token_encrypted TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_verify_token_hash TEXT;

CREATE OR REPLACE FUNCTION public.mark_email_verified(p_user_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_user_id AND email_confirmed_at IS NOT NULL) THEN
        RETURN FALSE;
    END IF;
    UPDATE public.profiles SET email_verified = TRUE,
        email_verification_token = NULL, email_verification_expires_at = NULL
        WHERE user_id = p_user_id;
    RETURN FOUND;
END;
$$;
REVOKE ALL ON FUNCTION public.mark_email_verified(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.mark_email_verified(UUID) TO service_role;

-- A token is consumed exactly once, before the server confirms Supabase Auth.
-- If the provider call fails, the user can request a fresh verification code.
CREATE OR REPLACE FUNCTION public.consume_email_verification(p_user_id UUID, p_token TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF p_token IS NULL OR length(p_token) < 16 THEN RETURN FALSE; END IF;
    UPDATE public.profiles SET email_verification_token = NULL,
        email_verification_expires_at = NULL
        WHERE user_id = p_user_id
          AND email_verification_token = p_token
          AND email_verification_expires_at > now();
    RETURN FOUND;
END;
$$;
REVOKE ALL ON FUNCTION public.consume_email_verification(UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_email_verification(UUID, TEXT) TO service_role;

-- This field previously represented a UI toggle, not an enrolled MFA factor.
UPDATE public.profiles SET two_factor_enabled = FALSE WHERE two_factor_enabled = TRUE;

NOTIFY pgrst, 'reload schema';
