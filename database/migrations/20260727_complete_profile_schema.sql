-- Complete, additive profile schema migration for Supabase/PostgREST.
-- Safe to run repeatedly. Existing profile data is preserved.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE,
    email TEXT,
    full_name TEXT,
    phone TEXT,
    avatar_url TEXT,
    timezone TEXT DEFAULT 'UTC',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS id UUID;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS user_id UUID;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS email TEXT;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS full_name TEXT;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS phone TEXT;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

ALTER TABLE public.profiles
    ALTER COLUMN id SET DEFAULT gen_random_uuid(),
    ALTER COLUMN timezone SET DEFAULT 'UTC',
    ALTER COLUMN updated_at SET DEFAULT NOW();

UPDATE public.profiles
SET id = gen_random_uuid()
WHERE id IS NULL;

UPDATE public.profiles
SET timezone = 'UTC'
WHERE timezone IS NULL OR BTRIM(timezone) = '';

UPDATE public.profiles
SET updated_at = NOW()
WHERE updated_at IS NULL;

ALTER TABLE public.profiles
    ALTER COLUMN id SET NOT NULL;

-- Keep identifiers stable on both fresh installs and older profiles tables
-- that used user_id as their original primary key.
DO $$
DECLARE
    existing_pk TEXT;
    id_is_primary_key BOOLEAN;
BEGIN
    SELECT conname
      INTO existing_pk
      FROM pg_constraint
     WHERE conrelid = 'public.profiles'::regclass
       AND contype = 'p'
     LIMIT 1;

    SELECT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid
           AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = 'public.profiles'::regclass
           AND c.contype = 'p'
           AND a.attname = 'id'
    ) INTO id_is_primary_key;

    IF existing_pk IS NULL THEN
        ALTER TABLE public.profiles
            ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);
    ELSIF NOT id_is_primary_key THEN
        -- The legacy profiles schema used user_id as its primary key. Move
        -- the primary key to id while retaining user_id uniqueness below.
        EXECUTE format(
            'ALTER TABLE public.profiles DROP CONSTRAINT %I',
            existing_pk
        );
        ALTER TABLE public.profiles
            ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS profiles_user_id_key
    ON public.profiles (user_id)
    WHERE user_id IS NOT NULL;

NOTIFY pgrst, 'reload schema';
