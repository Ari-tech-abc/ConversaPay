-- Required by PATCH /api/v1/profile and the profile settings form.
alter table public.profiles add column if not exists avatar_url text;
