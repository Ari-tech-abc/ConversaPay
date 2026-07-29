-- Store WhatsApp credentials encrypted at rest. Legacy columns are retained only for lazy migration.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_access_token_encrypted TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_verify_token_encrypted TEXT;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS whatsapp_verify_token_hash TEXT;
CREATE INDEX IF NOT EXISTS profiles_whatsapp_verify_token_hash_idx ON public.profiles(whatsapp_verify_token_hash) WHERE whatsapp_verify_token_hash IS NOT NULL;
COMMENT ON COLUMN public.profiles.whatsapp_access_token_encrypted IS 'Fernet ciphertext; key is held by the application secret manager.';
COMMENT ON COLUMN public.profiles.whatsapp_verify_token_encrypted IS 'Fernet ciphertext; key is held by the application secret manager.';
COMMENT ON COLUMN public.profiles.whatsapp_verify_token_hash IS 'HMAC lookup digest; plaintext verify token is never returned by the API.';
