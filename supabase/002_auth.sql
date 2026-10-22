-- App-level auth (JWT + OTP) on top of Supabase Postgres.
-- Keeps Supabase Auth optional; backend owns sessions via JWT_SECRET.

create table if not exists public.app_users (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete set null,
  email text not null unique,
  password_hash text,
  full_name text not null default '',
  role text not null default 'admin'
    check (role in ('platform','admin','finance','am','legal','vendor','consultant')),
  scope text not null default 'All',
  created_at timestamptz default now()
);
create index if not exists app_users_tenant_idx on public.app_users(tenant_id);
alter table public.app_users enable row level security;

create table if not exists public.otp_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  code text not null,
  expires_at timestamptz not null,
  consumed boolean default false,
  created_at timestamptz default now()
);
create index if not exists otp_email_idx on public.otp_codes(email);
alter table public.otp_codes enable row level security;
