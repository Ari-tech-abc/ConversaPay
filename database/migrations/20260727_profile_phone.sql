-- Optional phone field used by the partial profile settings update.
alter table public.profiles add column if not exists phone text;
