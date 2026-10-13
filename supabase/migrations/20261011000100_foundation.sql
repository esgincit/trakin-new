-- =============================================================================
-- myTrakIn · 0100 · Foundation
--
-- All business data lives in the `mytrakin` schema, which is NOT exposed through
-- Supabase's auto-generated Data API. Browsers never read these tables directly;
-- every request goes through the FastAPI service, which opens a transaction,
-- switches to the `mytrakin_api` role and sets the request context with
-- mytrakin.begin_request(). Row-level security then scopes every query to the
-- caller's tenant and role.
-- =============================================================================

-- citext: case-insensitive e-mail columns. Supabase keeps extensions in the `extensions` schema.
do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'extensions') then
    create extension if not exists citext with schema extensions;
  else
    create extension if not exists citext;
  end if;
end $$;

create schema if not exists mytrakin;
comment on schema mytrakin is 'myTrakIn application data (not exposed via the Supabase Data API)';

-- The API role. NOLOGIN: the API connects with the project credentials and
-- switches to this role per transaction, so RLS always applies (no BYPASSRLS).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'mytrakin_api') then
    create role mytrakin_api nologin noinherit;
  end if;
end $$;

grant mytrakin_api to current_user;
grant usage on schema mytrakin to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Request context helpers (read the settings made by begin_request)
-- -----------------------------------------------------------------------------
create or replace function mytrakin.ctx_user() returns uuid
language sql stable as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

create or replace function mytrakin.ctx_tenant() returns uuid
language sql stable as $$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

create or replace function mytrakin.ctx_role() returns text
language sql stable as $$ select coalesce(nullif(current_setting('app.role', true), ''), 'anonymous') $$;

create or replace function mytrakin.ctx_company() returns uuid
language sql stable as $$ select nullif(current_setting('app.company_id', true), '')::uuid $$;

create or replace function mytrakin.ctx_consultant() returns uuid
language sql stable as $$ select nullif(current_setting('app.consultant_id', true), '')::uuid $$;

create or replace function mytrakin.ctx_signer() returns uuid
language sql stable as $$ select nullif(current_setting('app.signer_id', true), '')::uuid $$;

-- Roles that work for the tenant itself (as opposed to vendors, clients and consultants).
create or replace function mytrakin.is_internal() returns boolean
language sql stable as $$
  select mytrakin.ctx_role() in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr', 'approver', 'viewer', 'system')
$$;

-- True when the caller has one of the given roles. Tenant admins and the
-- system (cron) context can do everything inside their tenant.
create or replace function mytrakin.can(variadic roles text[]) returns boolean
language sql stable as $$
  select mytrakin.ctx_role() = any (roles) or mytrakin.ctx_role() in ('tenant_admin', 'system')
$$;

create or replace function mytrakin.is_platform_admin() returns boolean
language sql stable as $$ select mytrakin.ctx_role() = 'platform_admin' $$;

-- Called once at the start of every API transaction.
create or replace function mytrakin.begin_request(
  p_user uuid,
  p_tenant uuid,
  p_role text,
  p_company uuid default null,
  p_consultant uuid default null,
  p_ip text default null,
  p_user_agent text default null,
  p_signer uuid default null
) returns void
language plpgsql as $$
begin
  perform set_config('role', 'mytrakin_api', true);
  perform set_config('search_path', 'mytrakin, public, extensions', true);
  perform set_config('app.user_id', coalesce(p_user::text, ''), true);
  perform set_config('app.tenant_id', coalesce(p_tenant::text, ''), true);
  perform set_config('app.role', coalesce(p_role, 'anonymous'), true);
  perform set_config('app.company_id', coalesce(p_company::text, ''), true);
  perform set_config('app.consultant_id', coalesce(p_consultant::text, ''), true);
  perform set_config('app.signer_id', coalesce(p_signer::text, ''), true);
  perform set_config('app.ip', coalesce(p_ip, ''), true);
  perform set_config('app.user_agent', left(coalesce(p_user_agent, ''), 300), true);
end $$;

grant execute on all functions in schema mytrakin to mytrakin_api;

-- updated_at maintenance
create or replace function mytrakin.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- -----------------------------------------------------------------------------
-- Tenants (each staffing company using myTrakIn)
-- -----------------------------------------------------------------------------
create table mytrakin.tenants (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  legal_name       text,
  ein              text,
  state            text,
  plan             text not null default 'growth' check (plan in ('starter', 'growth', 'enterprise')),
  status           text not null default 'onboarding' check (status in ('onboarding', 'active', 'suspended', 'closed')),
  trial_ends_on    date,
  onboarding_step  smallint not null default 1 check (onboarding_step between 1 and 8),
  live_on          date,
  last_active_at   timestamptz,
  settings         jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create trigger tenants_touch before update on mytrakin.tenants for each row execute function mytrakin.touch_updated_at();

-- Public sign-up requests from staffing companies that want their own workspace.
create table mytrakin.tenant_signups (
  id           uuid primary key default gen_random_uuid(),
  company      text not null,
  contact_name text not null,
  email        citext not null,
  phone        text,
  state        text,
  ein          text,
  plan         text not null default 'growth',
  seats        int not null default 5,
  checks       jsonb not null default '{}'::jsonb,
  documents    jsonb not null default '[]'::jsonb,
  status       text not null default 'pending' check (status in ('pending', 'needs_info', 'approved', 'rejected')),
  flag         text,
  decided_by   uuid,
  decided_at   timestamptz,
  tenant_id    uuid references mytrakin.tenants (id),
  created_at   timestamptz not null default now()
);

create table mytrakin.platform_admins (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- People: profiles (one per auth user, shared across tenants) and memberships
-- -----------------------------------------------------------------------------
create table mytrakin.profiles (
  id             uuid primary key references auth.users (id) on delete cascade,
  email          citext,
  full_name      text,
  headline       text,
  location       text,
  about          text,
  phone          text,
  website        text,
  avatar_path    text,
  cover_path     text,
  open_to_work   boolean not null default false,
  visibility     text not null default 'network' check (visibility in ('network', 'company_and_connections', 'company')),
  show_contact   boolean not null default true,
  skills         jsonb not null default '[]'::jsonb,
  experience     jsonb not null default '[]'::jsonb,
  certifications jsonb not null default '[]'::jsonb,
  education      jsonb not null default '[]'::jsonb,
  preferences    jsonb not null default '{}'::jsonb,
  notifications  jsonb not null default '{}'::jsonb,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create trigger profiles_touch before update on mytrakin.profiles for each row execute function mytrakin.touch_updated_at();
create index profiles_email_idx on mytrakin.profiles (email);

-- A user's role inside a tenant. Invitations exist before the person signs in
-- (user_id null, invited_email set); they are claimed automatically at first sign-in.
create table mytrakin.memberships (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references mytrakin.tenants (id) on delete cascade,
  user_id        uuid references auth.users (id) on delete cascade,
  invited_email  citext,
  role           text not null check (role in (
                   'tenant_admin', 'finance', 'account_manager', 'legal', 'hr', 'approver', 'viewer',
                   'vendor_admin', 'client_user', 'consultant')),
  company_id     uuid,          -- vendor_admin / client_user: which company they represent
  consultant_id  uuid,          -- consultant: which consultant record is theirs
  title          text,
  manager_id     uuid references mytrakin.memberships (id) on delete set null,
  signing_limit  numeric(14, 2),
  status         text not null default 'invited' check (status in ('invited', 'active', 'locked', 'deactivated')),
  last_active_at timestamptz,
  created_at     timestamptz not null default now(),
  constraint memberships_identity check (user_id is not null or invited_email is not null)
);
create unique index memberships_user_tenant_uq on mytrakin.memberships (tenant_id, user_id) where user_id is not null;
create unique index memberships_invite_uq on mytrakin.memberships (tenant_id, invited_email) where user_id is null;
create index memberships_user_idx on mytrakin.memberships (user_id);

-- Sequential, human-readable numbers per tenant (invoice numbers, envelope numbers ...).
create table mytrakin.counters (
  tenant_id uuid not null references mytrakin.tenants (id) on delete cascade,
  key       text not null,
  value     bigint not null default 0,
  primary key (tenant_id, key)
);

create or replace function mytrakin.next_number(p_tenant uuid, p_key text) returns bigint
language sql set search_path = mytrakin, public, extensions as $$
  insert into mytrakin.counters (tenant_id, key, value) values (p_tenant, p_key, 1)
  on conflict (tenant_id, key) do update set value = mytrakin.counters.value + 1
  returning value
$$;

-- -----------------------------------------------------------------------------
-- Auth hooks: create a profile for every new user and claim pending invitations.
-- SECURITY DEFINER because it runs in Supabase's auth context.
-- -----------------------------------------------------------------------------
create or replace function mytrakin.handle_new_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  insert into mytrakin.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'full_name', split_part(coalesce(new.email, ''), '@', 1)))
  on conflict (id) do nothing;

  if new.email is not null then
    update mytrakin.memberships
       set user_id = new.id, status = 'active'
     where user_id is null and invited_email = new.email::citext;
  end if;
  return new;
end $$;

drop trigger if exists on_auth_user_created_mytrakin on auth.users;
create trigger on_auth_user_created_mytrakin
  after insert on auth.users
  for each row execute function mytrakin.handle_new_user();
