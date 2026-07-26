create table if not exists public.site_builder_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token_id uuid references public.site_builder_tokens(id) on delete set null,
  project_name text not null default 'ConversaPay site',
  html text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists site_builder_projects_user_id_idx on public.site_builder_projects(user_id);
create index if not exists site_builder_projects_updated_at_idx on public.site_builder_projects(updated_at desc);

alter table public.site_builder_projects enable row level security;

create or replace function public.touch_site_builder_projects_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists site_builder_projects_updated_at on public.site_builder_projects;
create trigger site_builder_projects_updated_at
before update on public.site_builder_projects
for each row execute function public.touch_site_builder_projects_updated_at();
