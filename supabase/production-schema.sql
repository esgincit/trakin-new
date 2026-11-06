-- myTrakIn production database bootstrap
-- Run once in the SQL Editor of a fresh Supabase project as its postgres role.
-- Supabase provides the auth and storage schemas used by these migrations.
-- Application data lives in mytrakin and is accessed through the FastAPI server.
-- Keep mytrakin out of the Supabase Data API's exposed schemas.
-- This file includes required reference data and bucket definitions.
-- The legacy schema, demo seed, and plain-Postgres test bootstrap are excluded.
-- Manual execution does not record versions in Supabase CLI migration history.
-- Before running supabase db push against this project, mark the included
-- versions as applied in the CLI migration history.

begin;
set local search_path = public, extensions;

-- Source: migrations/20261011000100_foundation.sql
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

-- Source: migrations/20261011000200_business.sql
-- =============================================================================
-- myTrakIn · 0200 · Business data
--
-- Money rule: the tenant only ever stores its OWN two links of a vendor chain —
-- what it bills its customer (AR) and what it pays its vendor or contractor (AP).
-- Rates between other parties (end client -> prime, vendor -> consultant) are
-- never stored, so they can never leak.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Clients, primes, vendors and end clients the tenant works with.
create table companies (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  name              text not null,
  kind              text not null check (kind in ('client', 'prime_vendor', 'vendor', 'end_client')),
  ein               text,
  state             text,
  address           text,
  contact_name      text,
  contact_email     citext,
  contact_phone     text,
  default_terms     text not null default 'Net 30',
  status            text not null default 'onboarding' check (status in ('onboarding', 'active', 'inactive')),
  onboarding_stage  smallint not null default 1 check (onboarding_stage between 0 and 8),
  inactive_since    date,
  inactive_reason   text,
  bank_verified     boolean not null default false,
  notes             text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (tenant_id, name)
);
create trigger companies_touch before update on companies for each row execute function touch_updated_at();
create index companies_tenant_kind_idx on companies (tenant_id, kind, status);

-- Everyone who does the work: W-2 employees, C2C consultants and 1099 contractors.
create table consultants (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenants (id) on delete cascade,
  user_id             uuid references auth.users (id) on delete set null,
  full_name           text not null,
  email               citext,
  phone               text,
  engagement          text not null check (engagement in ('w2_fulltime', 'w2_contract', 'c2c', '1099')),
  employer_company_id uuid references companies (id),            -- C2C only
  title               text,
  location            text,
  status              text not null default 'onboarding' check (status in ('onboarding', 'active', 'former')),
  start_date          date,
  end_date            date,
  leave_reason        text,
  rehire_eligible     boolean,
  work_auth_type      text,
  work_auth_expires   date,
  i9_status           text,
  everify_status      text,
  onboarding_checklist jsonb not null default '[]'::jsonb,
  skills              text[] not null default '{}',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint consultants_c2c_employer check (engagement <> 'c2c' or employer_company_id is not null)
);
create trigger consultants_touch before update on consultants for each row execute function touch_updated_at();
create index consultants_tenant_status_idx on consultants (tenant_id, status);
create index consultants_employer_idx on consultants (employer_company_id);
create index consultants_user_idx on consultants (user_id);

-- MSAs, subcontractor agreements, 1099 contractor agreements, NDAs and offer letters.
create table agreements (
  id                      uuid primary key default gen_random_uuid(),
  tenant_id               uuid not null references tenants (id) on delete cascade,
  code                    text not null,
  kind                    text not null check (kind in ('msa', 'subcontract', 'ica', 'nda', 'offer_letter')),
  company_id              uuid references companies (id),
  consultant_id           uuid references consultants (id),
  tenant_side             text not null check (tenant_side in ('supplier', 'buyer', 'employer')),
  effective_on            date,
  expires_on              date,
  payment_terms           text,
  renewal                 text,
  notice_period           text,
  insurance_required      text,
  status                  text not null default 'draft' check (status in ('draft', 'out_for_signature', 'active', 'expired', 'terminated')),
  signed_by               text,
  signed_file_path        text,
  source                  text not null default 'myTrakIn' check (source in ('myTrakIn', 'imported', 'manual')),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (tenant_id, code),
  constraint agreements_party check (company_id is not null or consultant_id is not null)
);
create trigger agreements_touch before update on agreements for each row execute function touch_updated_at();
create index agreements_expiry_idx on agreements (tenant_id, expires_on);

-- SOWs / work orders: what the tenant bills (we_bill) or pays (we_pay) under an agreement.
create table sows (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants (id) on delete cascade,
  code               text not null,
  agreement_id       uuid not null references agreements (id),
  side               text not null check (side in ('we_bill', 'we_pay')),
  company_id         uuid references companies (id),
  consultant_id      uuid references consultants (id),   -- 1099 work orders
  title              text not null,
  start_date         date not null,
  end_date           date not null,
  value_cap          numeric(14, 2),
  prior_invoiced     numeric(14, 2) not null default 0,  -- invoiced before myTrakIn (imports)
  prior_paid         numeric(14, 2) not null default 0,
  flows_from_sow_id  uuid references sows (id),          -- vendor SOW supporting a client SOW
  status             text not null default 'active' check (status in ('draft', 'out_for_signature', 'active', 'ended', 'terminated')),
  signed_file_path   text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code),
  constraint sows_dates check (end_date >= start_date)
);
create trigger sows_touch before update on sows for each row execute function touch_updated_at();
create index sows_tenant_end_idx on sows (tenant_id, end_date);

create table sow_amendments (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  sow_id        uuid not null references sows (id) on delete cascade,
  code          text not null,
  summary       text not null,
  new_end_date  date,
  value_change  numeric(14, 2),
  status        text not null default 'draft' check (status in ('draft', 'out_for_signature', 'signed', 'void')),
  created_at    timestamptz not null default now(),
  unique (tenant_id, code)
);

create table projects (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants (id) on delete cascade,
  code               text not null,
  name               text not null,
  client_company_id  uuid references companies (id),
  prime_company_id   uuid references companies (id),
  description        text,
  start_date         date,
  end_date           date,
  manager_id         uuid references memberships (id) on delete set null,
  client_approver    text,
  status             text not null default 'active' check (status in ('planned', 'active', 'completed', 'internal')),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code)
);
create trigger projects_touch before update on projects for each row execute function touch_updated_at();

-- One consultant on one project. A consultant can have any number of placements.
create table placements (
  id                     uuid primary key default gen_random_uuid(),
  tenant_id              uuid not null references tenants (id) on delete cascade,
  consultant_id          uuid not null references consultants (id),
  project_id             uuid not null references projects (id),
  role_title             text,
  start_date             date not null,
  end_date               date,
  hours_per_week         numeric(5, 2) not null default 40,
  status                 text not null default 'active' check (status in ('onboarding', 'active', 'ending', 'completed', 'ended')),
  end_client_company_id  uuid references companies (id),   -- name only; never a rate
  -- AR: who the tenant bills, and at what rate
  ar_company_id          uuid references companies (id),
  ar_sow_id              uuid references sows (id),
  bill_rate              numeric(10, 2),
  ar_terms               text,
  -- AP: who the tenant pays (vendor company or 1099 consultant). Null for W-2.
  ap_company_id          uuid references companies (id),
  ap_consultant_id       uuid references consultants (id),
  ap_sow_id              uuid references sows (id),
  pay_rate               numeric(10, 2),
  ap_terms               text,
  pay_when_paid          boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint placements_one_payee check (ap_company_id is null or ap_consultant_id is null),
  constraint placements_rates check (coalesce(bill_rate, 0) >= 0 and coalesce(pay_rate, 0) >= 0)
);
create trigger placements_touch before update on placements for each row execute function touch_updated_at();
create index placements_consultant_idx on placements (consultant_id);
create index placements_tenant_status_idx on placements (tenant_id, status);
create index placements_ap_company_idx on placements (ap_company_id);

-- -----------------------------------------------------------------------------
-- Timesheets: one per consultant per week; one entry per placement per day.
-- -----------------------------------------------------------------------------
create table timesheets (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  week_start     date not null check (extract(isodow from week_start) = 7),   -- Sunday
  status         text not null default 'draft' check (status in ('draft', 'submitted', 'approved', 'rejected')),
  note           text,
  submitted_at   timestamptz,
  decided_by     uuid,
  decided_at     timestamptz,
  reject_reason  text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (consultant_id, week_start)
);
create trigger timesheets_touch before update on timesheets for each row execute function touch_updated_at();
create index timesheets_tenant_week_idx on timesheets (tenant_id, week_start, status);

create table timesheet_entries (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  timesheet_id  uuid not null references timesheets (id) on delete cascade,
  placement_id  uuid references placements (id),     -- null = internal / non-billable
  work_date     date not null,
  hours         numeric(4, 2) not null check (hours >= 0 and hours <= 24),
  rate_type     text not null default 'regular' check (rate_type in ('regular', 'overtime', 'holiday', 'on_call')),
  unique (timesheet_id, placement_id, work_date, rate_type)
);
create index timesheet_entries_ts_idx on timesheet_entries (timesheet_id);
create index timesheet_entries_placement_idx on timesheet_entries (placement_id, work_date);

-- -----------------------------------------------------------------------------
-- Invoices (AR = we bill, AP = we are billed) and payments
-- -----------------------------------------------------------------------------
create table invoices (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  number            text not null,
  direction         text not null check (direction in ('ar', 'ap')),
  placement_id      uuid references placements (id),
  company_id        uuid references companies (id),     -- AR customer or AP vendor
  consultant_id     uuid references consultants (id),   -- AP 1099 payee
  sow_id            uuid references sows (id),
  period_start      date,
  period_end        date,
  hours             numeric(8, 2) not null default 0,
  approved_hours    numeric(8, 2),                      -- AP three-way match
  rate              numeric(10, 2) not null default 0,
  amount            numeric(14, 2) not null,
  issued_on         date not null default current_date,
  due_on            date,
  terms             text,
  pay_when_paid_of  uuid references invoices (id),      -- AP waits for this AR invoice
  status            text not null default 'sent' check (status in ('draft', 'sent', 'received', 'exception', 'scheduled', 'paid', 'void')),
  scheduled_on      date,
  po_number         text,
  memo              text,
  created_by        uuid,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (tenant_id, number),
  constraint invoices_payee check (direction = 'ar' or company_id is not null or consultant_id is not null)
);
create trigger invoices_touch before update on invoices for each row execute function touch_updated_at();
create index invoices_tenant_dir_status_idx on invoices (tenant_id, direction, status);
create index invoices_due_idx on invoices (tenant_id, due_on);
create index invoices_placement_idx on invoices (placement_id);
create index invoices_pwp_idx on invoices (pay_when_paid_of);

create table payments (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  invoice_id  uuid not null references invoices (id) on delete cascade,
  amount      numeric(14, 2) not null check (amount > 0),
  paid_on     date not null,
  method      text not null check (method in ('ACH', 'Wire', 'Check', 'Card', 'Other')),
  reference   text,
  created_by  uuid,
  created_at  timestamptz not null default now()
);
create index payments_invoice_idx on payments (invoice_id);
create index payments_tenant_date_idx on payments (tenant_id, paid_on);

create table collection_notes (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  invoice_id  uuid not null references invoices (id) on delete cascade,
  body        text not null,
  author_id   uuid,
  author_name text,
  created_at  timestamptz not null default now()
);

-- Invoice balance and live status in one place (used by every money screen).
create view invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                              as paid,
  i.amount - coalesce(p.paid, 0)                   as balance,
  greatest(0, current_date - i.due_on)             as days_late,
  case
    when i.status = 'void'                                      then 'void'
    when i.amount - coalesce(p.paid, 0) <= 0                     then 'paid'
    when i.status = 'exception'                                  then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and exists (select 1 from invoices ar
                      left join (select invoice_id, sum(amount) s from payments group by invoice_id) arp on arp.invoice_id = ar.id
                      where ar.id = i.pay_when_paid_of and ar.amount - coalesce(arp.s, 0) > 0)
                                                                 then 'held'
    when i.status = 'scheduled'                                  then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0     then 'overdue_part_paid'
    when i.due_on < current_date                                 then 'overdue'
    when coalesce(p.paid, 0) > 0                                 then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null   then 'ready_to_pay'
    else 'open'
  end                                              as live_status
from invoices i
left join (select invoice_id, sum(amount) as paid from payments group by invoice_id) p on p.invoice_id = i.id;

-- SOW value used and remaining.
create view sow_burn with (security_invoker = true) as
select
  s.id as sow_id,
  s.tenant_id,
  s.value_cap,
  s.prior_invoiced + coalesce(sum(b.amount) filter (where b.status <> 'void'), 0) as invoiced,
  s.prior_paid + coalesce(sum(b.paid), 0)                                         as collected_or_paid,
  case when coalesce(s.value_cap, 0) > 0
       then round(100 * (s.prior_invoiced + coalesce(sum(b.amount) filter (where b.status <> 'void'), 0)) / s.value_cap)
  end                                                                             as burn_pct
from sows s
left join invoice_balances b on b.sow_id = s.id
group by s.id;

-- -----------------------------------------------------------------------------
-- Expenses and time off
-- -----------------------------------------------------------------------------
create table expenses (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  placement_id   uuid references placements (id),
  spent_on       date not null,
  category       text not null,
  amount         numeric(10, 2) not null check (amount > 0),
  billable       boolean not null default true,
  receipt_path   text,
  status         text not null default 'submitted' check (status in ('submitted', 'approved', 'rejected', 'reimbursed')),
  decided_by     uuid,
  created_at     timestamptz not null default now()
);

create table time_off (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  starts_on      date not null,
  ends_on        date not null,
  kind           text not null check (kind in ('pto', 'sick', 'unpaid', 'holiday')),
  note           text,
  status         text not null default 'requested' check (status in ('requested', 'approved', 'declined', 'holiday')),
  created_at     timestamptz not null default now(),
  constraint time_off_dates check (ends_on >= starts_on)
);

-- W-2 payroll register imported from the payroll provider (cost tracking only).
create table payroll_lines (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants (id) on delete cascade,
  consultant_id   uuid not null references consultants (id),
  period_start    date not null,
  period_end      date not null,
  pay_date        date not null,
  hours           numeric(6, 2),
  gross           numeric(12, 2) not null,
  employer_taxes  numeric(12, 2) not null default 0,
  benefits        numeric(12, 2) not null default 0,
  net             numeric(12, 2),
  source          text not null default 'import',
  created_at      timestamptz not null default now()
);

create table referral_agreements (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  referrer_name    text not null,
  referrer_type    text not null check (referrer_type in ('individual_1099', 'company', 'employee')),
  consultant_id    uuid not null references consultants (id),
  basis            text not null check (basis in ('hourly', 'one_time')),
  rate_per_hour    numeric(8, 2),
  hour_cap         numeric(8, 2),
  one_time_amount  numeric(10, 2),
  eligible_on      date,
  w9_on_file       boolean not null default false,
  created_at       timestamptz not null default now()
);

create table referral_payments (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants (id) on delete cascade,
  agreement_id uuid not null references referral_agreements (id) on delete cascade,
  amount       numeric(10, 2) not null check (amount > 0),
  paid_on      date not null,
  reference    text
);

-- Source: migrations/20261011000300_compliance_esign_network.sql
-- =============================================================================
-- myTrakIn · 0300 · Documents, compliance, e-signatures, reminders, network, audit
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Any uploaded file. Bytes live in Supabase Storage; this row is the index.
create table documents (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  owner_type    text not null check (owner_type in ('company', 'consultant', 'project', 'agreement', 'sow', 'invoice', 'envelope', 'registration', 'policy', 'expense')),
  owner_id      uuid not null,
  name          text not null,
  storage_path  text not null,
  mime_type     text,
  size_bytes    bigint,
  sha256        text,
  uploaded_by   uuid,
  deleted_at    timestamptz,          -- soft delete, purged after 30 days
  created_at    timestamptz not null default now()
);
create index documents_owner_idx on documents (tenant_id, owner_type, owner_id) where deleted_at is null;

-- Things that expire: I-9 reverification, passports, EAD, I-94, COI, W-9 ...
create table tracked_documents (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  consultant_id    uuid references consultants (id) on delete cascade,
  company_id       uuid references companies (id) on delete cascade,
  doc_type         text not null check (doc_type in ('i9_reverification', 'passport', 'ead', 'i94', 'visa_notice', 'coi', 'w9',
                                                      'background_check', 'certification', 'drivers_license', 'agreement', 'other')),
  label            text not null,
  expires_on       date,
  status           text not null default 'valid' check (status in ('valid', 'missing', 'pending', 'expired', 'renewed')),
  blocks           text,                -- what is held while missing/expired, e.g. 'payouts'
  recipients       text[] not null default '{}',
  last_notified_on date,
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  constraint tracked_documents_owner check (consultant_id is not null or company_id is not null)
);
create index tracked_documents_expiry_idx on tracked_documents (tenant_id, expires_on) where active;

create table policies (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  name          text not null,
  version       text not null,
  effective_on  date not null,
  applies_to    text[] not null default '{w2_fulltime,w2_contract,c2c,1099}',
  file_path     text,
  active        boolean not null default true,
  created_at    timestamptz not null default now(),
  unique (tenant_id, name, version)
);

create table policy_acceptances (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  policy_id     uuid not null references policies (id) on delete cascade,
  consultant_id uuid not null references consultants (id) on delete cascade,
  accepted_at   timestamptz not null default now(),
  ip            text,
  user_agent    text,
  unique (policy_id, consultant_id)
);

-- Vendors, clients and contractors who registered through the public page.
create table registrations (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  kind        text not null check (kind in ('client', 'vendor', '1099', 'consultant')),
  name        text not null,
  contact     text not null,
  email       citext not null,
  phone       text,
  state       text,
  ein         text,
  checks      jsonb not null default '{}'::jsonb,
  documents   jsonb not null default '[]'::jsonb,
  status      text not null default 'pending' check (status in ('pending', 'needs_info', 'approved', 'rejected')),
  decided_by  uuid,
  decided_at  timestamptz,
  created_at  timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- E-signatures
-- -----------------------------------------------------------------------------
create table envelopes (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  number            text not null,
  title             text not null,
  agreement_id      uuid references agreements (id),
  sow_id            uuid references sows (id),
  amendment_id      uuid references sow_amendments (id),
  consultant_id     uuid references consultants (id),     -- NDAs / offers / ICAs
  document_path     text,                                  -- original PDF in storage
  document_sha256   text,
  signed_path       text,                                  -- sealed PDF incl. certificate
  signed_sha256     text,
  message           text,
  sequential        boolean not null default true,
  remind_every_days int not null default 3,
  status            text not null default 'draft' check (status in ('draft', 'sent', 'completed', 'declined', 'voided', 'expired')),
  sent_by           uuid,
  sent_by_name      text,
  sent_at           timestamptz,
  expires_at        timestamptz,
  completed_at      timestamptz,
  created_at        timestamptz not null default now(),
  unique (tenant_id, number)
);
create index envelopes_tenant_status_idx on envelopes (tenant_id, status);

create table envelope_signers (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  envelope_id      uuid not null references envelopes (id) on delete cascade,
  position         smallint not null,
  name             text not null,
  email            citext not null,
  company          text,
  company_id       uuid references companies (id),
  status           text not null default 'waiting' check (status in ('waiting', 'sent', 'viewed', 'signed', 'declined')),
  token_hash       text unique,          -- sha256 of the signing link token (the token itself is only emailed)
  otp_hash         text,
  otp_expires_at   timestamptz,
  otp_attempts     smallint not null default 0,
  verified_at      timestamptz,
  consented_at     timestamptz,
  signed_at        timestamptz,
  signature_type   text check (signature_type in ('typed', 'drawn')),
  signature_data   text,                 -- typed name or PNG data URL
  signed_ip        text,
  signed_user_agent text,
  signed_location  text,
  declined_reason  text,
  last_reminded_at timestamptz,
  unique (envelope_id, position)
);

-- Append-only evidence for the certificate of completion.
create table signature_events (
  id           bigserial primary key,
  tenant_id    uuid not null references tenants (id) on delete cascade,
  envelope_id  uuid not null references envelopes (id) on delete cascade,
  signer_id    uuid references envelope_signers (id) on delete cascade,
  event        text not null check (event in ('created', 'sent', 'email_delivered', 'viewed', 'verified', 'consented',
                                              'signed', 'declined', 'reminded', 'voided', 'completed', 'expired')),
  at           timestamptz not null default now(),
  ip           text,
  user_agent   text,
  location     text,
  detail       jsonb not null default '{}'::jsonb
);
create index signature_events_env_idx on signature_events (envelope_id, at);

-- Finds the signer behind a signing link without a tenant context.
create or replace function esign_lookup(p_token_hash text)
returns table (signer_id uuid, envelope_id uuid, tenant_id uuid)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select s.id, s.envelope_id, s.tenant_id from envelope_signers s where s.token_hash = p_token_hash
$$;
revoke all on function esign_lookup(text) from public;
grant execute on function esign_lookup(text) to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Reminders and outbound notifications
-- -----------------------------------------------------------------------------
create table reminder_rules (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants (id) on delete cascade,
  key        text not null,
  area       text not null,
  description text not null,
  offsets    int[] not null default '{}',     -- days relative to the due/expiry date (negative = before)
  channels   text[] not null default '{email}',
  enabled    boolean not null default true,
  unique (tenant_id, key)
);

create table notifications (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid references tenants (id) on delete cascade,
  to_address  text not null,
  subject     text not null,
  kind        text not null,
  ref_type    text,
  ref_id      uuid,
  channel     text not null default 'email',
  status      text not null default 'sent' check (status in ('queued', 'sent', 'failed', 'skipped')),
  dedupe_key  text,
  sent_at     timestamptz not null default now()
);
create unique index notifications_dedupe_uq on notifications (tenant_id, dedupe_key) where dedupe_key is not null;
create index notifications_tenant_sent_idx on notifications (tenant_id, sent_at desc);

-- Logging an e-mail goes through these two SECURITY DEFINER functions so that signers and
-- visitors (who may send a notice but must not read the log) can use them, and so the
-- dedupe check (ON CONFLICT) doesn't need read access to other rows.
create or replace function log_notification(p_tenant uuid, p_to text, p_subject text, p_kind text, p_ref_type text,
                                            p_ref_id uuid, p_dedupe text) returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare v_id uuid;
begin
  if ctx_role() = 'anonymous' or p_tenant is distinct from ctx_tenant() then
    raise exception 'not allowed' using errcode = '42501';
  end if;
  insert into notifications (tenant_id, to_address, subject, kind, ref_type, ref_id, dedupe_key, status)
  values (p_tenant, p_to, left(p_subject, 250), p_kind, p_ref_type, p_ref_id, p_dedupe, 'queued')
  on conflict (tenant_id, dedupe_key) where dedupe_key is not null do nothing
  returning id into v_id;
  return v_id;     -- null = already sent (duplicate)
end $$;

create or replace function mark_notification(p_id uuid, p_status text) returns void
language sql security definer set search_path = mytrakin, public, extensions as $$
  update notifications set status = p_status, sent_at = now()
   where id = p_id and status = 'queued' and p_status in ('sent', 'failed', 'skipped')
$$;
revoke all on function log_notification(uuid, text, text, text, text, uuid, text), mark_notification(uuid, text) from public;
grant execute on function log_notification(uuid, text, text, text, text, uuid, text), mark_notification(uuid, text) to mytrakin_api;

create table import_jobs (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  entity         text not null,
  filename       text,
  total_rows     int not null default 0,
  imported_rows  int not null default 0,
  updated_rows   int not null default 0,
  errors         jsonb not null default '[]'::jsonb,
  created_by     uuid,
  created_at     timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- Network (LinkedIn-style): connections, posts and direct messages across tenants
-- -----------------------------------------------------------------------------
create table connections (
  requester_id uuid not null references auth.users (id) on delete cascade,
  addressee_id uuid not null references auth.users (id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  created_at   timestamptz not null default now(),
  primary key (requester_id, addressee_id),
  constraint connections_not_self check (requester_id <> addressee_id)
);

create table posts (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid references tenants (id) on delete cascade,   -- null = visible to the whole network
  author_id   uuid not null references auth.users (id) on delete cascade,
  kind        text not null default 'update' check (kind in ('update', 'kudos', 'announcement', 'opening')),
  body        text not null check (length(body) <= 3000),
  likes       int not null default 0,
  created_at  timestamptz not null default now()
);
create index posts_tenant_created_idx on posts (tenant_id, created_at desc);

create table messages (
  id          uuid primary key default gen_random_uuid(),
  sender_id   uuid not null references auth.users (id) on delete cascade,
  recipient_id uuid not null references auth.users (id) on delete cascade,
  body        text not null check (length(body) <= 5000),
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);
create index messages_pair_idx on messages (least(sender_id, recipient_id), greatest(sender_id, recipient_id), created_at);

-- -----------------------------------------------------------------------------
-- Audit log: every insert, update and delete on business tables, append-only
-- -----------------------------------------------------------------------------
create table audit_log (
  id          bigserial primary key,
  tenant_id   uuid,
  actor_id    uuid,
  actor_role  text,
  action      text not null,
  entity      text not null,
  entity_id   text,
  changes     jsonb,
  ip          text,
  user_agent  text,
  at          timestamptz not null default now()
);
create index audit_log_tenant_at_idx on audit_log (tenant_id, at desc);
create index audit_log_entity_idx on audit_log (tenant_id, entity, entity_id);

create or replace function audit_row() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare
  v_old jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  v_new jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
  v_changes jsonb;
  v_key text;
begin
  if tg_op = 'UPDATE' then
    v_changes := '{}'::jsonb;
    for v_key in select jsonb_object_keys(v_new) loop
      if v_key not in ('updated_at', 'last_active_at', 'last_notified_on', 'last_reminded_at') and v_new -> v_key is distinct from v_old -> v_key then
        v_changes := v_changes || jsonb_build_object(v_key, jsonb_build_object('from', v_old -> v_key, 'to', v_new -> v_key));
      end if;
    end loop;
    if v_changes = '{}'::jsonb then return new; end if;
  elsif tg_op = 'INSERT' then
    v_changes := v_new;
  else
    v_changes := v_old;
  end if;

  -- Never copy secrets into the audit trail.
  v_changes := v_changes - 'token_hash' - 'otp_hash' - 'signature_data';

  insert into audit_log (tenant_id, actor_id, actor_role, action, entity, entity_id, changes, ip, user_agent)
  values (
    coalesce((v_new ->> 'tenant_id')::uuid, (v_old ->> 'tenant_id')::uuid, ctx_tenant()),
    ctx_user(), ctx_role(), lower(tg_op), tg_table_name,
    coalesce(v_new ->> 'id', v_old ->> 'id'),
    v_changes,
    nullif(current_setting('app.ip', true), ''), nullif(current_setting('app.user_agent', true), '')
  );
  return coalesce(new, old);
end $$;

do $$
declare t text;
begin
  foreach t in array array['tenants', 'memberships', 'companies', 'consultants', 'agreements', 'sows', 'sow_amendments',
                           'projects', 'placements', 'timesheets', 'invoices', 'payments', 'expenses', 'time_off',
                           'documents', 'tracked_documents', 'policies', 'policy_acceptances', 'registrations',
                           'envelopes', 'envelope_signers', 'reminder_rules', 'referral_agreements', 'referral_payments',
                           'payroll_lines', 'collection_notes']
  loop
    execute format('create trigger %I after insert or update or delete on mytrakin.%I for each row execute function mytrakin.audit_row()',
                   t || '_audit', t);
  end loop;
end $$;

-- Source: migrations/20261011000400_security.sql
-- =============================================================================
-- myTrakIn · 0400 · Grants and row-level security
--
-- Layers of protection:
--   1. Supabase client roles (anon, authenticated) get NO access to this schema.
--   2. The API switches to mytrakin_api, which has table grants but no BYPASSRLS.
--   3. A RESTRICTIVE policy on every tenant table pins rows to app.tenant_id.
--   4. PERMISSIVE policies decide what each role may read or change.
--   5. The API additionally hides columns a role must not see (e.g. rates).
-- =============================================================================

set search_path = mytrakin, public, extensions;

revoke all on all tables in schema mytrakin from public;
revoke all on schema mytrakin from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on all tables in schema mytrakin from anon, authenticated';
    execute 'revoke all on schema mytrakin from anon, authenticated';
  end if;
end $$;

grant select, insert, update, delete on all tables in schema mytrakin to mytrakin_api;
grant usage, select on all sequences in schema mytrakin to mytrakin_api;
revoke insert, update, delete on mytrakin.audit_log from mytrakin_api;
revoke update, delete on mytrakin.signature_events from mytrakin_api;

-- -----------------------------------------------------------------------------
-- Session start: resolve the caller's role for a tenant (runs before the role
-- switch, so it may read memberships without a tenant context).
-- -----------------------------------------------------------------------------
create or replace function resolve_access(p_user uuid, p_tenant uuid)
returns table (tenant_id uuid, role text, company_id uuid, consultant_id uuid, membership_id uuid, is_platform_admin boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select m.tenant_id, m.role, m.company_id, m.consultant_id, m.id,
         exists (select 1 from platform_admins pa where pa.user_id = p_user)
    from memberships m
    join tenants t on t.id = m.tenant_id
   where m.user_id = p_user
     and m.status = 'active'
     and t.status <> 'closed'
     and (p_tenant is null or m.tenant_id = p_tenant)
   order by m.created_at
   limit 1
$$;

create or replace function my_tenants(p_user uuid)
returns table (tenant_id uuid, tenant_name text, role text, tenant_status text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, m.role, t.status
    from memberships m join tenants t on t.id = m.tenant_id
   where m.user_id = p_user and m.status = 'active'
   order by t.name
$$;

create or replace function is_platform_admin_user(p_user uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from platform_admins where user_id = p_user)
$$;

-- Lists active tenants for scheduled jobs (cron runs one tenant at a time).
create or replace function active_tenant_ids() returns setof uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select id from tenants where status in ('onboarding', 'active')
$$;

revoke all on function resolve_access(uuid, uuid), my_tenants(uuid), is_platform_admin_user(uuid), active_tenant_ids() from public;
grant execute on function resolve_access(uuid, uuid), my_tenants(uuid), is_platform_admin_user(uuid), active_tenant_ids() to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Turn RLS on everywhere and pin tenant tables to the request's tenant.
-- -----------------------------------------------------------------------------
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'mytrakin' loop
    execute format('alter table mytrakin.%I enable row level security', t);
  end loop;

  foreach t in array array['memberships', 'counters', 'companies', 'consultants', 'agreements', 'sows', 'sow_amendments',
                           'projects', 'placements', 'timesheets', 'timesheet_entries', 'invoices', 'payments',
                           'collection_notes', 'expenses', 'time_off', 'payroll_lines', 'referral_agreements',
                           'referral_payments', 'documents', 'tracked_documents', 'policies', 'policy_acceptances',
                           'registrations', 'envelopes', 'envelope_signers', 'signature_events', 'reminder_rules',
                           'notifications', 'import_jobs', 'audit_log']
  loop
    execute format(
      'create policy tenant_isolation on mytrakin.%I as restrictive to mytrakin_api
         using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant())', t);
  end loop;
end $$;

-- Shorthand used below:
--   internal()  = tenant staff     can(...) = staff with one of the roles (admins always pass)

-- Tenants and platform -----------------------------------------------------------
create policy tenants_read on tenants for select to mytrakin_api
  using (id = ctx_tenant() or is_platform_admin());
create policy tenants_admin on tenants for update to mytrakin_api
  using (is_platform_admin() or (id = ctx_tenant() and can('tenant_admin')))
  with check (is_platform_admin() or (id = ctx_tenant() and can('tenant_admin')));
create policy tenants_create on tenants for insert to mytrakin_api with check (is_platform_admin());

create policy signups_platform on tenant_signups for all to mytrakin_api
  using (is_platform_admin()) with check (is_platform_admin());
create policy signups_public_insert on tenant_signups for insert to mytrakin_api
  with check (ctx_role() = 'public' and status = 'pending');

create policy platform_admins_self on platform_admins for select to mytrakin_api
  using (user_id = ctx_user() or is_platform_admin());

-- People ----------------------------------------------------------------------
create policy profiles_read on profiles for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));
create policy profiles_self on profiles for update to mytrakin_api
  using (id = ctx_user()) with check (id = ctx_user());

create policy memberships_read on memberships for select to mytrakin_api
  using (is_internal() or user_id = ctx_user());
create policy memberships_admin on memberships for all to mytrakin_api
  using (can('tenant_admin')) with check (can('tenant_admin'));

create policy counters_all on counters for all to mytrakin_api using (true) with check (true);

-- Companies ---------------------------------------------------------------------
create policy companies_internal on companies for select to mytrakin_api using (is_internal());
create policy companies_own on companies for select to mytrakin_api
  using (ctx_role() in ('vendor_admin', 'client_user') and id = ctx_company());
create policy companies_consultant on companies for select to mytrakin_api
  using (ctx_role() = 'consultant' and (
         exists (select 1 from consultants c where c.id = ctx_consultant() and c.employer_company_id = companies.id)
      or exists (select 1 from placements p where p.consultant_id = ctx_consultant()
                  and companies.id in (p.ar_company_id, p.end_client_company_id, p.ap_company_id))));
create policy companies_write on companies for all to mytrakin_api
  using (can('account_manager', 'finance', 'legal')) with check (can('account_manager', 'finance', 'legal'));

-- Consultants -------------------------------------------------------------------
create policy consultants_internal on consultants for select to mytrakin_api using (is_internal());
create policy consultants_vendor on consultants for select to mytrakin_api
  using (ctx_role() = 'vendor_admin' and employer_company_id = ctx_company());
create policy consultants_self on consultants for select to mytrakin_api
  using (ctx_role() = 'consultant' and id = ctx_consultant());
create policy consultants_write on consultants for all to mytrakin_api
  using (can('hr', 'account_manager', 'legal')) with check (can('hr', 'account_manager', 'legal'));

-- Agreements, SOWs, amendments ------------------------------------------------------
create policy agreements_internal on agreements for select to mytrakin_api using (is_internal());
create policy agreements_party on agreements for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user') and company_id = ctx_company())
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy agreements_write on agreements for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));

create policy sows_internal on sows for select to mytrakin_api using (is_internal());
create policy sows_party on sows for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user') and company_id = ctx_company())
      or (ctx_role() = 'consultant' and exists (
            select 1 from placements p where p.consultant_id = ctx_consultant() and sows.id in (p.ar_sow_id, p.ap_sow_id))));
create policy sows_write on sows for all to mytrakin_api
  using (can('legal', 'account_manager')) with check (can('legal', 'account_manager'));

create policy amendments_read on sow_amendments for select to mytrakin_api
  using (is_internal() or exists (select 1 from sows s where s.id = sow_amendments.sow_id));
create policy amendments_write on sow_amendments for all to mytrakin_api
  using (can('legal', 'account_manager')) with check (can('legal', 'account_manager'));

-- Projects and placements -------------------------------------------------------------
create policy projects_internal on projects for select to mytrakin_api using (is_internal());
create policy projects_party on projects for select to mytrakin_api
  using ((ctx_role() = 'consultant' and exists (select 1 from placements p where p.project_id = projects.id and p.consultant_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and exists (select 1 from placements p where p.project_id = projects.id and p.ap_company_id = ctx_company()))
      or (ctx_role() = 'client_user' and ctx_company() in (client_company_id, prime_company_id)));
create policy projects_write on projects for all to mytrakin_api
  using (can('account_manager')) with check (can('account_manager'));

create policy placements_internal on placements for select to mytrakin_api using (is_internal());
create policy placements_party on placements for select to mytrakin_api
  using ((ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and ap_company_id = ctx_company())
      or (ctx_role() = 'client_user' and ar_company_id = ctx_company()));
create policy placements_write on placements for all to mytrakin_api
  using (can('account_manager', 'finance')) with check (can('account_manager', 'finance'));

-- Timesheets ----------------------------------------------------------------------
create policy timesheets_internal on timesheets for select to mytrakin_api using (is_internal());
create policy timesheets_party on timesheets for select to mytrakin_api
  using ((ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and exists (
            select 1 from consultants c where c.id = timesheets.consultant_id and c.employer_company_id = ctx_company())));
create policy timesheets_consultant_insert on timesheets for insert to mytrakin_api
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'submitted'));
create policy timesheets_consultant_update on timesheets for update to mytrakin_api
  using (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'rejected'))
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'submitted'));
create policy timesheets_staff_write on timesheets for all to mytrakin_api
  using (can('approver', 'account_manager', 'hr', 'finance')) with check (can('approver', 'account_manager', 'hr', 'finance'));

create policy entries_read on timesheet_entries for select to mytrakin_api
  using (exists (select 1 from timesheets t where t.id = timesheet_entries.timesheet_id));
create policy entries_consultant_write on timesheet_entries for all to mytrakin_api
  using (ctx_role() = 'consultant' and exists (
           select 1 from timesheets t where t.id = timesheet_entries.timesheet_id
              and t.consultant_id = ctx_consultant() and t.status in ('draft', 'rejected')))
  with check (ctx_role() = 'consultant' and exists (
           select 1 from timesheets t where t.id = timesheet_entries.timesheet_id
              and t.consultant_id = ctx_consultant() and t.status in ('draft', 'rejected')));
create policy entries_staff_write on timesheet_entries for all to mytrakin_api
  using (can('approver', 'account_manager', 'hr', 'finance')) with check (can('approver', 'account_manager', 'hr', 'finance'));

-- Money -----------------------------------------------------------------------------
create policy invoices_internal on invoices for select to mytrakin_api using (is_internal());
create policy invoices_party on invoices for select to mytrakin_api
  using ((ctx_role() = 'vendor_admin' and direction = 'ap' and company_id = ctx_company())
      or (ctx_role() = 'client_user' and direction = 'ar' and company_id = ctx_company())
      or (ctx_role() = 'consultant' and (consultant_id = ctx_consultant()
            or exists (select 1 from placements p where p.id = invoices.placement_id and p.consultant_id = ctx_consultant()))));
create policy invoices_finance on invoices for all to mytrakin_api
  using (can('finance')) with check (can('finance'));
create policy invoices_vendor_submit on invoices for insert to mytrakin_api
  with check (ctx_role() = 'vendor_admin' and direction = 'ap' and company_id = ctx_company() and status = 'received');

create policy payments_read on payments for select to mytrakin_api
  using (is_internal() or exists (select 1 from invoices i where i.id = payments.invoice_id));
create policy payments_finance on payments for all to mytrakin_api
  using (can('finance')) with check (can('finance'));

create policy notes_read on collection_notes for select to mytrakin_api using (is_internal());
create policy notes_write on collection_notes for insert to mytrakin_api with check (can('finance', 'account_manager'));

create policy expenses_read on expenses for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy expenses_submit on expenses for insert to mytrakin_api
  with check ((ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status = 'submitted') or can('finance', 'hr'));
create policy expenses_decide on expenses for update to mytrakin_api
  using (can('finance', 'hr', 'approver')) with check (can('finance', 'hr', 'approver'));

create policy time_off_read on time_off for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy time_off_request on time_off for insert to mytrakin_api
  with check ((ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status = 'requested') or can('hr', 'approver'));
create policy time_off_decide on time_off for update to mytrakin_api
  using (can('hr', 'approver', 'account_manager')) with check (can('hr', 'approver', 'account_manager'));

create policy payroll_finance on payroll_lines for all to mytrakin_api using (can('finance')) with check (can('finance'));
create policy referrals_finance on referral_agreements for all to mytrakin_api using (can('finance', 'hr')) with check (can('finance', 'hr'));
create policy referral_payments_finance on referral_payments for all to mytrakin_api using (can('finance')) with check (can('finance'));

-- Documents and compliance ---------------------------------------------------------------
-- (Soft-deleted rows stay readable to RLS so the delete itself can be written; queries filter deleted_at.)
create policy documents_read on documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())));
create policy documents_upload on documents for insert to mytrakin_api
  with check (is_internal()
      or (ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (ctx_role() = 'public' and owner_type = 'registration'));
create policy documents_manage on documents for update to mytrakin_api
  using (uploaded_by = ctx_user() or can('hr', 'legal', 'finance'))
  with check (uploaded_by = ctx_user() or can('hr', 'legal', 'finance'));

create policy tracked_read on tracked_documents for select to mytrakin_api
  using (is_internal()
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and (company_id = ctx_company() or exists (
            select 1 from consultants c where c.id = tracked_documents.consultant_id and c.employer_company_id = ctx_company()))));
create policy tracked_write on tracked_documents for all to mytrakin_api
  using (can('hr', 'legal')) with check (can('hr', 'legal'));

create policy policies_read on policies for select to mytrakin_api using (ctx_role() not in ('anonymous', 'public', 'signer'));
create policy policies_write on policies for all to mytrakin_api using (can('hr', 'legal')) with check (can('hr', 'legal'));

create policy acceptances_read on policy_acceptances for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy acceptances_accept on policy_acceptances for insert to mytrakin_api
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant());

create policy registrations_staff on registrations for all to mytrakin_api
  using (can('legal', 'hr', 'account_manager')) with check (can('legal', 'hr', 'account_manager'));
create policy registrations_public on registrations for insert to mytrakin_api
  with check (ctx_role() = 'public' and status = 'pending');

-- E-signatures ------------------------------------------------------------------------
create or replace function signer_envelope() returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select envelope_id from envelope_signers where id = ctx_signer()
$$;
grant execute on function signer_envelope() to mytrakin_api;

create policy envelopes_internal on envelopes for select to mytrakin_api using (is_internal());
-- Envelopes and their signers refer to each other, so the party rule lives in one
-- SECURITY DEFINER function (policies that query each other would recurse).
create or replace function envelope_visible(p_envelope uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from envelopes e
     where e.id = p_envelope and e.tenant_id = ctx_tenant()
       and (is_internal()
         or (ctx_role() = 'consultant' and e.consultant_id = ctx_consultant())
         or (ctx_role() in ('vendor_admin', 'client_user')
             and exists (select 1 from envelope_signers s where s.envelope_id = e.id and s.company_id = ctx_company()))
         or (ctx_role() = 'signer' and e.id = signer_envelope())))
$$;
grant execute on function envelope_visible(uuid) to mytrakin_api;

create policy envelopes_party on envelopes for select to mytrakin_api using (envelope_visible(id));
create policy envelopes_write on envelopes for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));
create policy envelopes_signer_complete on envelopes for update to mytrakin_api
  using (ctx_role() = 'signer' and id = signer_envelope()) with check (ctx_role() = 'signer' and id = signer_envelope());

create policy signers_read on envelope_signers for select to mytrakin_api
  using (is_internal() or envelope_visible(envelope_id));
create policy signers_write on envelope_signers for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));
create policy signers_signer_update on envelope_signers for update to mytrakin_api
  using (ctx_role() = 'signer' and envelope_id = signer_envelope())
  with check (ctx_role() = 'signer' and envelope_id = signer_envelope());

create policy sigevents_read on signature_events for select to mytrakin_api
  using (is_internal() or envelope_visible(envelope_id));
create policy sigevents_insert on signature_events for insert to mytrakin_api
  with check (can('legal', 'account_manager', 'finance', 'hr')
      or (ctx_role() = 'signer' and envelope_id = signer_envelope()));

-- Reminders, notifications, imports, audit ---------------------------------------------------
create policy reminder_rules_read on reminder_rules for select to mytrakin_api using (is_internal());
create policy reminder_rules_admin on reminder_rules for all to mytrakin_api using (can('tenant_admin')) with check (can('tenant_admin'));

create policy notifications_read on notifications for select to mytrakin_api using (is_internal());
-- Notifications are written only through log_notification() / mark_notification().

create policy imports_rw on import_jobs for all to mytrakin_api
  using (can('finance', 'hr', 'legal')) with check (can('finance', 'hr', 'legal'));

create policy audit_read on audit_log for select to mytrakin_api using (can('legal', 'finance'));

-- Network (cross-tenant, scoped to the person) ------------------------------------------------
create policy connections_mine on connections for select to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id));
create policy connections_request on connections for insert to mytrakin_api
  with check (requester_id = ctx_user());
create policy connections_respond on connections for update to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id)) with check (ctx_user() in (requester_id, addressee_id));
create policy connections_remove on connections for delete to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id));

create policy posts_read on posts for select to mytrakin_api
  using (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()));
create policy posts_write on posts for insert to mytrakin_api with check (author_id = ctx_user());
create policy posts_own on posts for delete to mytrakin_api using (author_id = ctx_user());
create policy posts_like on posts for update to mytrakin_api
  using (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()))
  with check (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()));

create policy messages_mine on messages for select to mytrakin_api using (ctx_user() in (sender_id, recipient_id));
create policy messages_send on messages for insert to mytrakin_api with check (sender_id = ctx_user());
create policy messages_read_receipt on messages for update to mytrakin_api
  using (recipient_id = ctx_user()) with check (recipient_id = ctx_user());

grant select on invoice_balances, sow_burn to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Cross-tenant helpers. SECURITY DEFINER, so each checks the caller itself.
-- -----------------------------------------------------------------------------

-- Platform console: usage per tenant (seats are billable active users).
create or replace function platform_tenant_stats()
returns table (tenant_id uuid, active_users bigint, invited_users bigint, consultants bigint, active_placements bigint,
               last_user_activity timestamptz)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id,
         (select count(*) from memberships m where m.tenant_id = t.id and m.status = 'active'),
         (select count(*) from memberships m where m.tenant_id = t.id and m.status = 'invited'),
         (select count(*) from consultants c where c.tenant_id = t.id and c.status <> 'former'),
         (select count(*) from placements p where p.tenant_id = t.id and p.status in ('active', 'ending')),
         (select max(m.last_active_at) from memberships m where m.tenant_id = t.id)
    from tenants t
   where is_platform_admin()
$$;

-- Network: may the caller see this person's profile? 'network' = anyone signed in;
-- 'company' = people who share a workspace; 'company_and_connections' adds accepted connections.
create or replace function visible_profile(p_profile uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select ctx_user() is not null and (
         p_profile = ctx_user()
      or exists (select 1 from profiles p where p.id = p_profile and p.visibility = 'network')
      or exists (select 1 from memberships a join memberships b on b.tenant_id = a.tenant_id
                  where a.user_id = ctx_user() and b.user_id = p_profile and a.status = 'active' and b.status = 'active')
      or exists (select 1 from profiles p join connections c
                   on c.status = 'accepted' and ((c.requester_id = ctx_user() and c.addressee_id = p.id)
                                              or (c.addressee_id = ctx_user() and c.requester_id = p.id))
                  where p.id = p_profile and p.visibility = 'company_and_connections'))
$$;

-- Workspaces two people share (shown on profiles as "Also at ...").
create or replace function shared_workspaces(p_profile uuid) returns setof text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.name from memberships a join memberships b on b.tenant_id = a.tenant_id join tenants t on t.id = a.tenant_id
   where a.user_id = ctx_user() and b.user_id = p_profile and a.status = 'active' and b.status = 'active'
$$;

revoke all on function platform_tenant_stats(), visible_profile(uuid), shared_workspaces(uuid) from public;
grant execute on function platform_tenant_stats(), visible_profile(uuid), shared_workspaces(uuid) to mytrakin_api;

-- Source: migrations/20261011000500_storage_and_defaults.sql
-- =============================================================================
-- myTrakIn · 0500 · Storage buckets and per-tenant defaults
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Storage buckets (only when running on Supabase).
--   documents : private. Files are read through short-lived signed URLs the API issues.
--   esign     : private. Original and sealed signed PDFs.
--   avatars   : public read. Profile photos and cover images under unguessable paths.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values
      ('documents', 'documents', false, 26214400, null),
      ('esign', 'esign', false, 26214400, array['application/pdf']),
      ('avatars', 'avatars', true, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
    on conflict (id) do nothing;
  end if;
end $$;

-- Default reminder rules for a new tenant.
create or replace function seed_tenant_defaults(p_tenant uuid) returns void
language sql set search_path = mytrakin, public, extensions as $$
  insert into mytrakin.reminder_rules (tenant_id, key, area, description, offsets, channels, enabled) values
    (p_tenant, 'timesheet_due',      'Timesheets',  'Remind consultants who have not submitted: Friday 3 PM, Monday 9 AM; escalate Tuesday', '{0,3,4}', '{email,sms}', true),
    (p_tenant, 'ar_courtesy',        'Client invoices', 'Courtesy notice before the due date', '{-7}', '{email}', true),
    (p_tenant, 'ar_overdue',         'Client invoices', 'Overdue reminders; day 15 copies the account manager, day 30 escalates to finance', '{1,7,15,30}', '{email}', true),
    (p_tenant, 'ap_status',          'Vendor & 1099 invoices', 'Tell payees when an invoice is matched, held, scheduled and paid', '{}', '{email}', true),
    (p_tenant, 'esign_reminder',     'E-signatures', 'Remind the current signer every 3 days; expire after 30 days', '{3}', '{email}', true),
    (p_tenant, 'contract_expiry',    'Contracts', 'MSA and SOW expiry alerts', '{-90,-60,-30}', '{email}', true),
    (p_tenant, 'work_auth_expiry',   'Compliance', 'Work authorization and I-9 reverification', '{-120,-90,-60,-30,-14,-7,0}', '{email}', true),
    (p_tenant, 'document_expiry',    'Compliance', 'Passports, EAD, I-94, insurance certificates, certifications', '{-120,-90,-60,-30,-14,-7,0}', '{email}', true),
    (p_tenant, 'policy_acceptance',  'Policies', 'Ask people to accept new policy versions within 14 days', '{0,7,14}', '{email}', true)
  on conflict (tenant_id, key) do nothing;
$$;
grant execute on function seed_tenant_defaults(uuid) to mytrakin_api;

-- Source: migrations/20261011000600_user_ids.sql
-- =============================================================================
-- myTrakIn · 0600 · System-wide user IDs
--
-- Every person in the system gets one stable, human-readable ID (U000001,
-- U000002, …) in `mytrakin.user_codes`, no matter how many workspaces they
-- belong to. The code is assigned by the signup trigger, so application code
-- can always join on it. Backfills everyone who signed up before this change.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- The counter. A sequence (not max+1) keeps codes unique under concurrency.
create sequence if not exists mytrakin.user_id_seq;

create or replace function mytrakin.next_user_code() returns text
language sql set search_path = mytrakin, public, extensions as $$
  select 'U' || lpad(nextval('mytrakin.user_id_seq')::text, 6, '0')
$$;
grant execute on function mytrakin.next_user_code() to mytrakin_api;

-- One row per login. The code is the system-wide ID; user_id ties it to Auth.
create table if not exists mytrakin.user_codes (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  code       text not null unique,
  created_at timestamptz not null default now()
);
comment on table mytrakin.user_codes is 'System-wide user IDs (U000001, …): one row per auth.users row.';
comment on column mytrakin.user_codes.code is 'Stable public ID shown in the app and API. Never reused, may have gaps.';

-- Indexing: the primary key covers user_id lookups and the unique constraint
-- covers code lookups (both are btree). Newest-first listing for admin screens.
create index if not exists user_codes_created_idx on mytrakin.user_codes (created_at desc);

grant select, insert, update, delete on mytrakin.user_codes to mytrakin_api;
grant usage, select on mytrakin.user_id_seq to mytrakin_api;

alter table mytrakin.user_codes enable row level security;
drop policy if exists user_codes_read on mytrakin.user_codes;
create policy user_codes_read on mytrakin.user_codes for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));

-- Backfill: everyone who signed up before this migration, oldest first.
insert into mytrakin.user_codes (user_id, code)
select u.id, mytrakin.next_user_code()
  from auth.users u
 where not exists (select 1 from mytrakin.user_codes c where c.user_id = u.id)
 order by u.created_at, u.id
on conflict (user_id) do nothing;

-- Assign a code to every future signup, alongside the profile + invite claim.
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

  insert into mytrakin.user_codes (user_id, code)
  values (new.id, mytrakin.next_user_code())
  on conflict (user_id) do nothing;

  return new;
end $$;

-- Source: migrations/20261011000700_company_onboarding.sql
-- =============================================================================
-- myTrakIn · 0700 · Company onboarding (Business IDs, W-9, verification, members)
--
-- Companies grow from staff-typed counterparties into verified businesses:
--   business_code      unique public ID per tenant (C-0001, C-0002, …)
--   domain/logo/business_type/dba/contact fields for the company profile
--   tax_classification/tin/tax_address + w9_* columns for W-9 and tax data
--   verification       per-check results (domain, TIN match, W-9, owner)
--   company_members    owner/admin/member roles scoped to one company
--   my_businesses()    every business a user created or belongs to, any role
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- ---------------------------------------------------------------- business profile + tax columns
alter table mytrakin.companies
  add column if not exists business_code      text,
  add column if not exists domain             text,
  add column if not exists logo_path          text,
  add column if not exists business_type      text,
  add column if not exists dba                text,
  add column if not exists tax_classification text,
  add column if not exists tin                text,
  add column if not exists tax_address        text,
  add column if not exists w9_status          text not null default 'draft'
    check (w9_status in ('draft', 'submitted', 'under_review', 'verified', 'rejected')),
  add column if not exists w9_data            jsonb not null default '{}'::jsonb,
  add column if not exists w9_document_id     uuid,
  add column if not exists w9_decided_at      timestamptz,
  add column if not exists w9_decided_by      uuid,
  add column if not exists w9_note            text,
  add column if not exists verification      jsonb not null default '{}'::jsonb,
  add column if not exists verified_at        timestamptz,
  add column if not exists created_by         uuid;

-- Backfill Business IDs for existing companies, oldest first.
do $$
declare r record;
begin
  for r in select id, tenant_id from mytrakin.companies where business_code is null order by created_at, id loop
    update mytrakin.companies
       set business_code = 'C-' || lpad(mytrakin.next_number(r.tenant_id, 'company')::text, 4, '0')
     where id = r.id;
  end loop;
end $$;

alter table mytrakin.companies alter column business_code set not null;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'companies_business_code_uq') then
    alter table mytrakin.companies add constraint companies_business_code_uq unique (tenant_id, business_code);
  end if;
end $$;
create index if not exists companies_business_code_idx on mytrakin.companies (tenant_id, business_code);
create index if not exists companies_domain_idx on mytrakin.companies (tenant_id, domain);

-- ---------------------------------------------------------------- company members
create table if not exists mytrakin.company_members (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references mytrakin.tenants (id) on delete cascade,
  company_id     uuid not null references mytrakin.companies (id) on delete cascade,
  user_id        uuid references auth.users (id) on delete cascade,
  invited_email  citext,
  company_role   text not null check (company_role in ('owner', 'admin', 'member')),
  title          text,
  status         text not null default 'invited' check (status in ('invited', 'active', 'removed')),
  created_at     timestamptz not null default now(),
  constraint company_members_identity check (user_id is not null or invited_email is not null)
);
create unique index if not exists company_members_user_uq on mytrakin.company_members (company_id, user_id) where user_id is not null;
create unique index if not exists company_members_invite_uq on mytrakin.company_members (company_id, invited_email) where user_id is null;
create index if not exists company_members_user_idx on mytrakin.company_members (user_id);

-- Claim company invitations at first sign-in (mirrors memberships).
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

    update mytrakin.company_members
       set user_id = new.id, status = 'active'
     where user_id is null and invited_email = new.email::citext;
  end if;

  insert into mytrakin.user_codes (user_id, code)
  values (new.id, mytrakin.next_user_code())
  on conflict (user_id) do nothing;

  return new;
end $$;

grant select, insert, update, delete on mytrakin.company_members to mytrakin_api;
alter table mytrakin.company_members enable row level security;

-- Company role of the caller (null when they don't belong to the company).
create or replace function mytrakin.company_role(p_company uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select cm.company_role from mytrakin.company_members cm
   where cm.company_id = p_company and cm.user_id = mytrakin.ctx_user() and cm.status = 'active'
   order by case cm.company_role when 'owner' then 0 when 'admin' then 1 else 2 end
   limit 1
$$;
grant execute on function mytrakin.company_role(uuid) to mytrakin_api;

drop policy if exists company_members_isolation on mytrakin.company_members;
create policy company_members_isolation on mytrakin.company_members as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists company_members_read on mytrakin.company_members;
create policy company_members_read on mytrakin.company_members for select to mytrakin_api
  using (mytrakin.is_internal()
         or user_id = mytrakin.ctx_user()
         or mytrakin.company_role(company_id) is not null);
drop policy if exists company_members_write on mytrakin.company_members;
create policy company_members_write on mytrakin.company_members for all to mytrakin_api
  using (mytrakin.can('tenant_admin')
         or mytrakin.company_role(company_id) in ('owner', 'admin'))
  with check (mytrakin.can('tenant_admin')
              or mytrakin.company_role(company_id) in ('owner', 'admin'));

-- ---------------------------------------------------------------- associated businesses
create or replace function mytrakin.my_businesses(p_user uuid)
returns table (tenant_id uuid, tenant_name text, company_id uuid, business_code text,
               company_name text, kind text, company_role text, tenant_role text, status text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         cm.company_role,
         (select m.role from mytrakin.memberships m
           where m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
           order by m.created_at limit 1),
         c.status
    from mytrakin.company_members cm
    join mytrakin.companies c on c.id = cm.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where cm.user_id = p_user and cm.status = 'active' and c.status <> 'inactive'
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         null::text, m.role, c.status
    from mytrakin.memberships m
    join mytrakin.companies c on c.id = m.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where m.user_id = p_user and m.status = 'active' and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         null::text, m.role, c.status
    from mytrakin.consultants k
    join auth.users u on u.id = p_user
    join mytrakin.companies c on c.id = k.employer_company_id
    join mytrakin.tenants t on t.id = c.tenant_id
    join mytrakin.memberships m on m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
   where k.email = u.email and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
     and not exists (select 1 from mytrakin.memberships m2
                      where m2.user_id = p_user and m2.company_id = c.id and m2.status = 'active')
   order by company_name
$$;
grant execute on function mytrakin.my_businesses(uuid) to mytrakin_api;

-- Source: migrations/20261011000710_company_code_trigger.sql
-- =============================================================================
-- myTrakIn · 0710 · Business IDs for every insert
--
-- 0700 backfilled existing companies, but seed.sql (and any direct SQL insert)
-- omits business_code — and the column is NOT NULL. This trigger assigns the
-- next C-0001-style code whenever an insert leaves it blank, so seeds, imports
-- and future code paths can never fail on it. Explicit codes pass through.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.assign_business_code() returns trigger
language plpgsql set search_path = mytrakin, public, extensions as $$
begin
  if NEW.business_code is null or NEW.business_code = '' then
    NEW.business_code := 'C-' || lpad(mytrakin.next_number(NEW.tenant_id, 'company')::text, 4, '0');
  end if;
  return NEW;
end $$;

drop trigger if exists companies_business_code on mytrakin.companies;
create trigger companies_business_code
  before insert on mytrakin.companies
  for each row execute function mytrakin.assign_business_code();

-- Source: migrations/20261011000720_company_member_read.sql
-- =============================================================================
-- myTrakIn · 0720 · Company members read their own company
--
-- Anyone with a company membership (owner/admin/member) can open that company's
-- profile, whatever their workspace role — otherwise a consultant who creates a
-- business could never see it. Money and tax shielding still happens in the API.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_member on mytrakin.companies;
create policy companies_member on mytrakin.companies for select to mytrakin_api
  using (mytrakin.company_role(id) is not null);

-- Source: migrations/20261011000730_company_owner_write.sql
-- =============================================================================
-- myTrakIn · 0730 · Company owners can drive onboarding, whatever their workspace role
--
-- Creating is open to members, so writing must be too — scoped to companies the
-- caller owns or admins (activation and money rules stay staff-only in the API):
--   companies   : any signed-in member may insert drafts (status onboarding);
--                 owners/admins may update their own company's onboarding data
--                 (which columns is enforced per-endpoint in the API);
--                 deletes stay with staff
--   documents / tracked_documents: company owners/admins may manage their own
--                 company's files (W-9 uploads, logos)
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_write on mytrakin.companies;
drop policy if exists companies_insert on mytrakin.companies;
drop policy if exists companies_staff_update on mytrakin.companies;
drop policy if exists companies_staff_delete on mytrakin.companies;
drop policy if exists companies_creator on mytrakin.companies;
drop policy if exists companies_owner_update on mytrakin.companies;
create policy companies_insert on mytrakin.companies for insert to mytrakin_api
  with check (mytrakin.ctx_role() not in ('anonymous', 'public', 'signer') and status = 'onboarding');
create policy companies_staff_update on mytrakin.companies for update to mytrakin_api
  using (mytrakin.can('account_manager', 'finance', 'legal'))
  with check (mytrakin.can('account_manager', 'finance', 'legal'));
create policy companies_staff_delete on mytrakin.companies for delete to mytrakin_api
  using (mytrakin.can('account_manager', 'finance', 'legal'));

-- The creator can read their draft back (INSERT ... RETURNING checks SELECT
-- policies too, and no membership exists yet at insert time).
create policy companies_creator on mytrakin.companies for select to mytrakin_api
  using (created_by is not null and created_by = mytrakin.ctx_user());

-- Owners/admins keep their company's onboarding data moving (tax, logo, W-9,
-- verification). Which columns each role may touch is enforced in the API;
-- activation itself stays staff-only there.
create policy companies_owner_update on mytrakin.companies for update to mytrakin_api
  using (mytrakin.company_role(id) in ('owner', 'admin'))
  with check (mytrakin.company_role(id) in ('owner', 'admin'));

drop policy if exists documents_upload on mytrakin.documents;
drop policy if exists documents_read on mytrakin.documents;
create policy documents_upload on mytrakin.documents for insert to mytrakin_api
  with check (is_internal()
      or (ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) in ('owner', 'admin'))
      or (ctx_role() = 'public' and owner_type = 'registration'));

drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)));

drop policy if exists tracked_write on mytrakin.tracked_documents;
create policy tracked_write on mytrakin.tracked_documents for all to mytrakin_api
  using (mytrakin.can('hr', 'legal')
         or (company_id is not null and mytrakin.company_role(company_id) in ('owner', 'admin')))
  with check (mytrakin.can('hr', 'legal')
              or (company_id is not null and mytrakin.company_role(company_id) in ('owner', 'admin')));

drop policy if exists tracked_read on mytrakin.tracked_documents;
create policy tracked_read on mytrakin.tracked_documents for select to mytrakin_api
  using (is_internal()
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and (company_id = ctx_company() or exists (
            select 1 from consultants c where c.id = tracked_documents.consultant_id and c.employer_company_id = ctx_company())))
      or (company_id is not null and mytrakin.company_role(company_id) is not null));

-- Source: migrations/20261011000740_company_owner_trigger.sql
-- =============================================================================
-- myTrakIn · 0740 · The company creator automatically becomes its owner
--
-- The API cannot insert the owner's membership row itself: company_members_write
-- is checked against existing rows, and WITH CHECK subqueries never see the row
-- being inserted. A SECURITY DEFINER trigger does it instead — it also covers
-- seeds and direct SQL inserts that set created_by.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.assign_company_owner() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if NEW.created_by is not null then
    insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
    values (NEW.tenant_id, NEW.id, NEW.created_by, 'owner', 'active')
    on conflict do nothing;
  end if;
  return NEW;
end $$;

drop trigger if exists companies_owner on mytrakin.companies;
create trigger companies_owner
  after insert on mytrakin.companies
  for each row execute function mytrakin.assign_company_owner();

-- Source: migrations/20261011000750_country_onboarding.sql
-- =============================================================================
-- myTrakIn · 0750 · Country-first business creation (US W-9 / India MOA+CIN)
--
--   companies.country ('US'|'IN', default US) and companies.cin (India CIN,
--     unique per tenant). Existing rows are US businesses.
--   company_members.company_role gains 'super_admin' — the business creator.
--     Role order everywhere: super_admin > owner > admin > member.
--   Session documents: documents.owner_type gains 'session' (files attached to an
--     onboarding session before its company exists); tracked doc_type gains 'moa'.
--   onboarding_sessions: the gated creation flow. W-9 parse → details → e-mail OTP
--     → authorization checkbox → company. Nothing is created before every gate.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- ---------------------------------------------------------------- companies: country + CIN
alter table mytrakin.companies
  add column if not exists country text not null default 'US' check (country in ('US', 'IN')),
  add column if not exists cin     text;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'companies_cin_uq') then
    alter table mytrakin.companies add constraint companies_cin_uq unique (tenant_id, cin);
  end if;
end $$;
create index if not exists companies_cin_idx on mytrakin.companies (tenant_id, cin);

-- ---------------------------------------------------------------- onboarding sessions
-- (created before the policies: documents_upload references this table)
create table if not exists mytrakin.onboarding_sessions (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references mytrakin.tenants (id) on delete cascade,
  country            text not null check (country in ('US', 'IN')),
  created_by         uuid not null references auth.users (id) on delete cascade,
  payload            jsonb not null default '{}'::jsonb,
  company_email      citext,
  email_otp_hash     text,
  email_otp_expires  timestamptz,
  email_otp_attempts int not null default 0,
  email_otp_sent_at  timestamptz,
  email_verified_at  timestamptz,
  email_verified_for citext,
  authorized_at      timestamptz,
  auth_ip            text,
  status             text not null default 'draft'
    check (status in ('draft', 'email_verified', 'complete', 'expired')),
  company_id         uuid references mytrakin.companies (id) on delete set null,
  created_at         timestamptz not null default now(),
  expires_at         timestamptz not null default now() + interval '24 hours'
);
create index if not exists onboarding_sessions_owner_idx on mytrakin.onboarding_sessions (tenant_id, created_by, status);
create index if not exists onboarding_sessions_expiry_idx on mytrakin.onboarding_sessions (expires_at) where status <> 'complete';

grant select, insert, update, delete on mytrakin.onboarding_sessions to mytrakin_api;
alter table mytrakin.onboarding_sessions enable row level security;
drop policy if exists onboarding_isolation on mytrakin.onboarding_sessions;
create policy onboarding_isolation on mytrakin.onboarding_sessions as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists onboarding_owner on mytrakin.onboarding_sessions;
create policy onboarding_owner on mytrakin.onboarding_sessions for all to mytrakin_api
  using (created_by = mytrakin.ctx_user() or mytrakin.is_internal())
  with check (created_by = mytrakin.ctx_user() or mytrakin.is_internal());

-- ---------------------------------------------------------------- super_admin role
alter table mytrakin.company_members drop constraint if exists company_members_company_role_check;
alter table mytrakin.company_members
  add constraint company_members_company_role_check
  check (company_role in ('super_admin', 'owner', 'admin', 'member'));

create or replace function mytrakin.company_role(p_company uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select cm.company_role from mytrakin.company_members cm
   where cm.company_id = p_company and cm.user_id = mytrakin.ctx_user() and cm.status = 'active'
   order by case cm.company_role when 'super_admin' then 0 when 'owner' then 1 when 'admin' then 2 else 3 end
   limit 1
$$;

-- The creator is the company's Super Admin.
create or replace function mytrakin.assign_company_owner() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if NEW.created_by is not null then
    insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
    values (NEW.tenant_id, NEW.id, NEW.created_by, 'super_admin', 'active')
    on conflict do nothing;
  end if;
  return NEW;
end $$;

drop policy if exists company_members_write on mytrakin.company_members;
create policy company_members_write on mytrakin.company_members for all to mytrakin_api
  using (mytrakin.can('tenant_admin')
         or mytrakin.company_role(company_id) in ('super_admin', 'owner', 'admin'))
  with check (mytrakin.can('tenant_admin')
              or mytrakin.company_role(company_id) in ('super_admin', 'owner', 'admin'));

drop policy if exists companies_owner_update on mytrakin.companies;
create policy companies_owner_update on mytrakin.companies for update to mytrakin_api
  using (mytrakin.company_role(id) in ('super_admin', 'owner', 'admin'))
  with check (mytrakin.company_role(id) in ('super_admin', 'owner', 'admin'));

drop policy if exists documents_upload on mytrakin.documents;
create policy documents_upload on mytrakin.documents for insert to mytrakin_api
  with check (is_internal()
      or (ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) in ('super_admin', 'owner', 'admin'))
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
                                             where s.id = owner_id and s.created_by = mytrakin.ctx_user()))
      or (ctx_role() = 'public' and owner_type = 'registration'));

drop policy if exists tracked_write on mytrakin.tracked_documents;
create policy tracked_write on mytrakin.tracked_documents for all to mytrakin_api
  using (mytrakin.can('hr', 'legal')
         or (company_id is not null and mytrakin.company_role(company_id) in ('super_admin', 'owner', 'admin')))
  with check (mytrakin.can('hr', 'legal')
              or (company_id is not null and mytrakin.company_role(company_id) in ('super_admin', 'owner', 'admin')));

-- ---------------------------------------------------------------- session documents + MOA
alter table mytrakin.documents drop constraint if exists documents_owner_type_check;
alter table mytrakin.documents
  add constraint documents_owner_type_check
  check (owner_type in ('company', 'consultant', 'project', 'agreement', 'sow', 'invoice',
                        'envelope', 'registration', 'policy', 'expense', 'session'));

alter table mytrakin.tracked_documents drop constraint if exists tracked_documents_doc_type_check;
alter table mytrakin.tracked_documents
  add constraint tracked_documents_doc_type_check
  check (doc_type in ('i9_reverification', 'passport', 'ead', 'i94', 'visa_notice', 'coi', 'w9',
                      'background_check', 'certification', 'drivers_license', 'agreement', 'moa', 'other'));

-- Source: migrations/20261011000760_company_otp_plaintext.sql
-- =============================================================================
-- myTrakIn · 0760 · Readable company-email OTPs
--
-- Owner's call: the 6-digit company-verification code is stored readable
-- (email_otp_code) so support can see/resend it from the database while mail
-- delivery is being fixed. Mitigations: cleared on verify and on every resend,
-- never returned by any API (except the existing test-only debug field), and
-- legacy hashes keep working until they expire.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.onboarding_sessions
  add column if not exists email_otp_code text;

-- Source: migrations/20261011000770_session_docs_read.sql
-- =============================================================================
-- myTrakIn · 0770 · Session documents are readable by their uploader
--
-- INSERT ... RETURNING checks SELECT policies too. The 0730 uploader clause let
-- creators store session files (W-9/MOA) but nothing let them read the row back,
-- so uploads 403'd for non-staff. Staff already see everything via is_internal().
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
                                             where s.id = owner_id and s.created_by = mytrakin.ctx_user()))));

-- Source: migrations/20261011000780_company_msa_directory.sql
-- =============================================================================
-- myTrakIn · 0780 · MSAs as connections between two companies
--
-- A company admin picks the counterparty from a searchable directory and
-- records (or requests) an MSA. Supporting schema:
--   agreements.initiator_company_id  the company that started it (null = staff record)
--   companies_directory             every non-inactive company, readable by any
--                                   signed-in tenant member (names only downstream)
--   agreements_party                either side's company users can read their MSAs
--   agreements_write                owners/admins of the initiating company may
--                                   *create* (updates/deletes stay staff-only)
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.agreements
  add column if not exists initiator_company_id uuid references mytrakin.companies (id) on delete set null;
create index if not exists agreements_initiator_idx on mytrakin.agreements (tenant_id, initiator_company_id);

drop policy if exists agreements_party on mytrakin.agreements;
create policy agreements_party on mytrakin.agreements for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user')
          and (company_id = ctx_company() or initiator_company_id = ctx_company()))
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (mytrakin.company_role(company_id) is not null)
      or (initiator_company_id is not null and mytrakin.company_role(initiator_company_id) is not null));

drop policy if exists agreements_write on mytrakin.agreements;
create policy agreements_write on mytrakin.agreements for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr')
      or (initiator_company_id is not null
          and mytrakin.company_role(initiator_company_id) in ('super_admin', 'owner', 'admin')));
create policy agreements_staff_write on mytrakin.agreements for update to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'))
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
create policy agreements_staff_delete on mytrakin.agreements for delete to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop policy if exists companies_directory on mytrakin.companies;
create policy companies_directory on mytrakin.companies for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));

-- Source: migrations/20261011000790_company_agreement_visibility.sql
-- =============================================================================
-- myTrakIn · 0790 · Company-side agreement visibility + NDA gate that can see
--
-- A company member (owner/admin/member/vendor) must see agreements their company
-- is party to — on either side of the link — and the Verify → NDA → MSA gate
-- must be able to check for an NDA without reading the whole row (RLS would hide
-- counterparties' agreements from the check itself).
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists agreements_member on mytrakin.agreements;
create policy agreements_member on mytrakin.agreements for select to mytrakin_api
  using (mytrakin.company_role(company_id) is not null
      or (initiator_company_id is not null and mytrakin.company_role(initiator_company_id) is not null));

create or replace function mytrakin.has_company_agreement(p_tenant uuid, p_kinds text[], p_company uuid, p_on date default current_date)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from mytrakin.agreements
                  where tenant_id = p_tenant and kind = any (p_kinds) and company_id = p_company
                    and status = 'active'
                    and coalesce(effective_on, p_on) <= p_on and coalesce(expires_on, p_on) >= p_on)
$$;
grant execute on function mytrakin.has_company_agreement(uuid, text[], uuid, date) to mytrakin_api;

-- Source: migrations/20261011000800_company_agreement_insert.sql
-- =============================================================================
-- myTrakIn · 0800 · Let membership-linked company admins create agreements
--
-- 0780's agreements_write INSERT policy only accepted staff roles or a
-- company_members row (super_admin/owner/admin) on the initiating company.
-- A vendor_admin / client_admin / client_user has NO company_members row —
-- their authority comes from memberships (role + membership.company_id, surfaced
-- as app.company_id by begin_request). The API gate (_can_manage_company)
-- already allows them, so the INSERT died with 42501 → HTTP 403.
-- Accept initiator_company_id = ctx_company() for those membership roles.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists agreements_write on mytrakin.agreements;
create policy agreements_write on mytrakin.agreements for insert to mytrakin_api
  with check (tenant_id = mytrakin.ctx_tenant()
      and (mytrakin.can('legal', 'account_manager', 'finance', 'hr')
          or mytrakin.company_role(initiator_company_id) in ('super_admin', 'owner', 'admin')
          or (initiator_company_id is not null
              and initiator_company_id = mytrakin.ctx_company()
              and mytrakin.ctx_role() in ('vendor_admin', 'client_admin', 'client_user'))));

-- Source: migrations/20261015000100_engagement_types.sql
-- =============================================================================
-- myTrakIn · 20261015 0100 · Engagement types as a lookup table (PLAN WF-07)
--
--   Owner e-mail 2026-10-15: support C2C, E2E (employer-to-employer) and 1099, and add
--   future types without a schema redesign. pay_model drives behaviour:
--     payroll = W-2 (paid through payroll, no AP payee)
--     vendor  = a vendor company employs the consultant (C2C, E2E) — AP to the vendor
--     self    = 1099 contractor paid directly
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.engagement_types (
  code       text primary key,
  name       text not null,
  pay_model  text not null check (pay_model in ('payroll', 'vendor', 'self')),
  is_active  boolean not null default true,
  sort       int not null default 0
);
insert into mytrakin.engagement_types (code, name, pay_model, sort) values
  ('w2_fulltime', 'W-2 full-time', 'payroll', 1),
  ('w2_contract', 'W-2 contract', 'payroll', 2),
  ('c2c', 'C2C (corp-to-corp)', 'vendor', 3),
  ('e2e', 'E2E (employer-to-employer)', 'vendor', 4),
  ('1099', '1099 contractor', 'self', 5)
on conflict (code) do nothing;

-- Global, read-only reference data (no tenant_id).
grant select on mytrakin.engagement_types to mytrakin_api;
alter table mytrakin.engagement_types enable row level security;
drop policy if exists engagement_types_read on mytrakin.engagement_types;
create policy engagement_types_read on mytrakin.engagement_types for select to mytrakin_api using (true);

alter table mytrakin.consultants drop constraint if exists consultants_engagement_check;
alter table mytrakin.consultants drop constraint if exists consultants_engagement_fk;
alter table mytrakin.consultants add constraint consultants_engagement_fk
  foreign key (engagement) references mytrakin.engagement_types (code);

-- Vendor-employed consultants need their employer company.
-- ponytail: lists the vendor codes; a trigger reading pay_model is the upgrade if more vendor types appear.
alter table mytrakin.consultants drop constraint if exists consultants_c2c_employer;
alter table mytrakin.consultants drop constraint if exists consultants_vendor_employer;
alter table mytrakin.consultants add constraint consultants_vendor_employer
  check (engagement not in ('c2c', 'e2e') or employer_company_id is not null);

-- Policies that apply to C2C consultants apply to E2E ones too.
alter table mytrakin.policies alter column applies_to set default '{w2_fulltime,w2_contract,c2c,e2e,1099}';
update mytrakin.policies set applies_to = applies_to || '{e2e}'::text[]
 where 'c2c' = any (applies_to) and not ('e2e' = any (applies_to));

-- Source: migrations/20261015000200_sow_project.sql
-- =============================================================================
-- myTrakIn · 20261015 0200 · SOWs belong to projects (PLAN WF-04)
--
--   Project → SOW → resources (placements). A SOW (client side) or work order (vendor /
--   1099 side) now records its project. Nullable on purpose: SOWs imported or recorded
--   without a project stay valid. Existing SOWs get the project of the placements using them.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.sows add column if not exists project_id uuid references mytrakin.projects (id);
create index if not exists sows_project_idx on mytrakin.sows (project_id);

update mytrakin.sows s set project_id = sub.project_id
  from (select distinct on (sow_id) sow_id, project_id
          from (select ar_sow_id as sow_id, project_id, start_date from mytrakin.placements where ar_sow_id is not null
                union all
                select ap_sow_id, project_id, start_date from mytrakin.placements where ap_sow_id is not null) x
         order by sow_id, start_date) sub
 where sub.sow_id = s.id and s.project_id is null;

-- Source: migrations/20261015000300_acceptances.sql
-- =============================================================================
-- myTrakIn · 20261015 0300 · Acceptance records (PLAN WF-05, WF-06)
--
--   Who accepted an NDA / MSA / SOW / amendment / resource contract, when and how
--   (e-signature or recorded by staff for paper / e-mail acceptance). E-sign completion
--   writes one automatically. The full history stays here and in the audit log.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.acceptances (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references mytrakin.tenants (id) on delete cascade,
  entity_type  text not null check (entity_type in ('agreement', 'sow', 'amendment')),
  entity_id    uuid not null,
  accepted_by  text not null,
  accepted_at  timestamptz not null default now(),
  method       text not null check (method in ('esign', 'manual')),
  envelope_id  uuid references mytrakin.envelopes (id) on delete set null,
  note         text,
  created_by   uuid
);
create index if not exists acceptances_entity_idx on mytrakin.acceptances (tenant_id, entity_type, entity_id);

grant select, insert on mytrakin.acceptances to mytrakin_api;
alter table mytrakin.acceptances enable row level security;
drop policy if exists tenant_isolation on mytrakin.acceptances;
create policy tenant_isolation on mytrakin.acceptances as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists acceptances_read on mytrakin.acceptances;
create policy acceptances_read on mytrakin.acceptances for select to mytrakin_api using (mytrakin.is_internal());
drop policy if exists acceptances_write on mytrakin.acceptances;
create policy acceptances_write on mytrakin.acceptances for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop trigger if exists acceptances_audit on mytrakin.acceptances;
create trigger acceptances_audit after insert or update or delete on mytrakin.acceptances
  for each row execute function mytrakin.audit_row();

-- Source: migrations/20261015000400_payment_confirmation.sql
-- =============================================================================
-- myTrakIn · 20261015 0400 · Payment status and payment confirmation (PLAN WF-09)
--
--   Invoice → Payment → Payment confirmation. A payment moves pending → processing →
--   completed (money moved) → confirmed (the receiving side confirmed it arrived), which
--   closes the financial lifecycle. Existing payments were recorded as done: completed.
--   Only completed / confirmed payments reduce an invoice's balance.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.payments
  add column if not exists status text not null default 'completed'
    check (status in ('pending', 'processing', 'completed', 'confirmed')),
  add column if not exists confirmed_by uuid,
  add column if not exists confirmed_by_name text,
  add column if not exists confirmed_at timestamptz;

-- Same columns as before; payments still in flight don't count yet.
create or replace view mytrakin.invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                              as paid,
  i.amount - coalesce(p.paid, 0)                   as balance,
  greatest(0, current_date - i.due_on)             as days_late,
  case
    when i.status = 'void'                                      then 'void'
    when i.amount - coalesce(p.paid, 0) <= 0                     then 'paid'
    when i.status = 'exception'                                  then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and exists (select 1 from mytrakin.invoices ar
                      left join (select invoice_id, sum(amount) s from mytrakin.payments
                                  where status in ('completed', 'confirmed') group by invoice_id) arp on arp.invoice_id = ar.id
                      where ar.id = i.pay_when_paid_of and ar.amount - coalesce(arp.s, 0) > 0)
                                                                 then 'held'
    when i.status = 'scheduled'                                  then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0     then 'overdue_part_paid'
    when i.due_on < current_date                                 then 'overdue'
    when coalesce(p.paid, 0) > 0                                 then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null   then 'ready_to_pay'
    else 'open'
  end                                              as live_status
from mytrakin.invoices i
left join (select invoice_id, sum(amount) as paid from mytrakin.payments
            where status in ('completed', 'confirmed') group by invoice_id) p on p.invoice_id = i.id;

-- The payee (vendor admin, or the 1099 contractor) confirms a payment made to them.
drop policy if exists payments_payee_confirm on mytrakin.payments;
create policy payments_payee_confirm on mytrakin.payments for update to mytrakin_api
  using (exists (select 1 from mytrakin.invoices i where i.id = payments.invoice_id and i.direction = 'ap'
                  and ((mytrakin.ctx_role() = 'vendor_admin' and i.company_id = mytrakin.ctx_company())
                    or (mytrakin.ctx_role() = 'consultant' and i.consultant_id = mytrakin.ctx_consultant()))))
  with check (status = 'confirmed');

-- Source: migrations/20261016000100_company_accounts.sql
-- =============================================================================
-- myTrakIn · P · 0100 · One company = one account (tenant). No workspaces in the product.
--   tenants.owner_membership_id  exactly one owner per company (transferable)
--   tenants.company_id           the company's own profile record (W-9, domain, members)
--   tenants.activated_*          platform activation (status onboarding → active)
--   start_company_account()      any signed-in user opens a new company (pending activation)
--   purge_abandoned_accounts()   drafts never finished within 7 days are removed
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table tenants
  add column if not exists owner_membership_id uuid references memberships (id) on delete set null,
  add column if not exists company_id          uuid references companies (id) on delete set null,
  add column if not exists activated_at        timestamptz,
  add column if not exists activated_by        uuid,
  add column if not exists decision_note       text;

-- Existing companies: the earliest active admin is the owner.
update tenants t
   set owner_membership_id = (select m.id from memberships m
                               where m.tenant_id = t.id and m.role = 'tenant_admin' and m.status = 'active'
                               order by m.created_at limit 1)
 where owner_membership_id is null;
update tenants set activated_at = created_at where status = 'active' and activated_at is null;

-- A company without an owner (older data, seeds, invites claimed later) gets its first active admin.
create or replace function claim_company_owner() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if NEW.role = 'tenant_admin' and NEW.status = 'active' and NEW.user_id is not null then
    update tenants set owner_membership_id = NEW.id where id = NEW.tenant_id and owner_membership_id is null;
  end if;
  return NEW;
end $$;
drop trigger if exists memberships_claim_owner on memberships;
create trigger memberships_claim_owner after insert or update of role, status, user_id on memberships
  for each row execute function claim_company_owner();

-- Is the caller the owner of the current company?
create or replace function is_account_owner() returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from tenants t join memberships m on m.id = t.owner_membership_id
                  where t.id = ctx_tenant() and m.user_id = ctx_user() and m.status = 'active')
$$;

-- Opens a new company for a signed-in user. Runs before any tenant context exists,
-- hence security definer. At most 3 unfinished/pending companies per person.
create or replace function start_company_account(p_user uuid) returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare t uuid; m uuid; pending int;
begin
  select count(*) into pending
    from tenants tt join memberships mm on mm.id = tt.owner_membership_id
   where mm.user_id = p_user and tt.status = 'onboarding';
  if pending >= 3 then
    raise exception 'too_many_pending' using errcode = 'P0001';
  end if;
  insert into tenants (name, status) values ('New company', 'onboarding') returning id into t;
  insert into memberships (tenant_id, user_id, role, title, status)
       values (t, p_user, 'tenant_admin', 'Owner', 'active') returning id into m;
  update tenants set owner_membership_id = m where id = t;
  perform seed_tenant_defaults(t);
  return t;
end $$;

create or replace function purge_abandoned_accounts() returns int
language sql security definer set search_path = mytrakin, public, extensions as $$
  with gone as (delete from tenants where status = 'onboarding' and company_id is null
                                      and created_at < now() - interval '7 days' returning 1)
  select count(*)::int from gone
$$;

revoke all on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() from public;
grant execute on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() to mytrakin_api;

-- Source: migrations/20261016000200_roles_permissions.sql
-- =============================================================================
-- myTrakIn · P · 0200 · Owner-configurable roles & permissions
--   custom_roles: a named role built on a base role + a module → none/read/write map
--   memberships.custom_role_id / permission_overrides: per-user assignment and exceptions
--   Only the company owner writes; members of the company can read role names.
-- =============================================================================
set search_path = mytrakin, public, extensions;

create table if not exists custom_roles (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  name        text not null check (length(name) between 2 and 60),
  base_role   text not null check (base_role in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr',
                                                 'approver', 'viewer', 'vendor_admin', 'client_user', 'consultant')),
  permissions jsonb not null default '{}'::jsonb,
  created_by  uuid,
  created_at  timestamptz not null default now()
);
create unique index if not exists custom_roles_name_uq on custom_roles (tenant_id, lower(name));

alter table memberships
  add column if not exists custom_role_id       uuid references custom_roles (id) on delete set null,
  add column if not exists permission_overrides jsonb not null default '{}'::jsonb;

alter table custom_roles enable row level security;
drop policy if exists custom_roles_read on custom_roles;
create policy custom_roles_read on custom_roles for select to mytrakin_api using (tenant_id = ctx_tenant());
drop policy if exists custom_roles_write on custom_roles;
create policy custom_roles_write on custom_roles for all to mytrakin_api
  using (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'))
  with check (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'));
grant select, insert, update, delete on custom_roles to mytrakin_api;

drop trigger if exists custom_roles_audit on custom_roles;
create trigger custom_roles_audit after insert or update or delete on custom_roles
  for each row execute function audit_row();

-- Source: migrations/20261016000300_user_mfa.sql
-- =============================================================================
-- myTrakIn · P · 0300 · Two-step verification is the user's choice (owner decision 2026-10-15)
--   memberships.mfa_allowed   the owner offers (true) or withholds (false) the option per user
--   user_has_mfa(uid)         did this person turn MFA on? (verified factor in Supabase Auth)
--   mfa_allowed_for(uid)      may they turn it on? (any active membership allows, or none yet)
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table memberships add column if not exists mfa_allowed boolean not null default true;

create or replace function user_has_mfa(p_user uuid) returns boolean
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare found boolean := false;
begin
  if p_user is not null and to_regclass('auth.mfa_factors') is not null then
    execute 'select exists (select 1 from auth.mfa_factors where user_id = $1 and status::text = ''verified'')'
       into found using p_user;
  end if;
  return found;
end $$;

create or replace function mfa_allowed_for(p_user uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(bool_or(mfa_allowed), true) from memberships where user_id = p_user and status = 'active'
$$;

revoke all on function user_has_mfa(uuid), mfa_allowed_for(uuid) from public;
grant execute on function user_has_mfa(uuid), mfa_allowed_for(uuid) to mytrakin_api;

-- Source: migrations/20261016000400_platform_analytics.sql
-- =============================================================================
-- myTrakIn · P · 0400 · Platform admin: company list / activation queue, platform admins,
-- and platform analytics. Aggregates only (RULE-05 as amended 2026-10-15): every function
-- returns nothing unless the caller is a platform admin.
-- =============================================================================
set search_path = mytrakin, public, extensions;

-- Platform admins manage the list of platform admins.
drop policy if exists platform_admins_manage on platform_admins;
create policy platform_admins_manage on platform_admins for all to mytrakin_api
  using (is_platform_admin()) with check (is_platform_admin());

-- Every company with its owner and onboarding state (the activation queue reads this).
create or replace function platform_companies()
returns table (tenant_id uuid, company_id uuid, name text, kind text, country text, state text, domain text,
               status text, plan text, created_at timestamptz, activated_at timestamptz, decision_note text,
               owner_name text, owner_email text, w9_status text, onboarding_stage smallint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, c.id, coalesce(c.name, t.name), c.kind, c.country, coalesce(c.state, t.state), c.domain,
         t.status, t.plan, t.created_at, t.activated_at, t.decision_note,
         p.full_name, coalesce(p.email, m.invited_email::text), c.w9_status, c.onboarding_stage
    from tenants t
    left join companies c on c.id = t.company_id
    left join memberships m on m.id = t.owner_membership_id
    left join profiles p on p.id = m.user_id
   where is_platform_admin()
$$;

-- Money moving through each company: totals only, never rows.
create or replace function platform_money_stats()
returns table (tenant_id uuid, ar_invoiced numeric, ar_collected numeric, ap_billed numeric, ap_paid numeric,
               invoiced_30d numeric, collected_30d numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with inv as (
    select i.tenant_id, i.direction, sum(i.amount) as total,
           sum(i.amount) filter (where i.issued_on > current_date - 30) as last30
      from invoices i where i.status not in ('draft', 'void') group by 1, 2),
  pay as (
    select p.tenant_id, i.direction, sum(p.amount) as total,
           sum(p.amount) filter (where p.paid_on > current_date - 30) as last30
      from payments p join invoices i on i.id = p.invoice_id
     where p.status in ('completed', 'confirmed') group by 1, 2)
  select t.id,
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select last30 from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select last30 from pay where pay.tenant_id = t.id and direction = 'ar'), 0)
    from tenants t
   where is_platform_admin()
$$;

-- Client invoicing and collections across the platform, last 12 months.
create or replace function platform_money_trend()
returns table (month text, invoiced numeric, collected numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with months as (select to_char(d, 'YYYY-MM') as month
                    from generate_series(date_trunc('month', now()) - interval '11 months',
                                         date_trunc('month', now()), interval '1 month') d)
  select m.month,
         coalesce((select sum(i.amount) from invoices i where i.direction = 'ar' and i.status not in ('draft', 'void')
                    and to_char(i.issued_on, 'YYYY-MM') = m.month), 0),
         coalesce((select sum(p.amount) from payments p join invoices i on i.id = p.invoice_id
                    where i.direction = 'ar' and p.status in ('completed', 'confirmed')
                      and to_char(p.paid_on, 'YYYY-MM') = m.month), 0)
    from months m
   where is_platform_admin()
   order by m.month
$$;

-- People and the onboarding funnel.
create or replace function platform_overview()
returns table (total_users bigint, new_users_30d bigint, active_users_30d bigint,
               wizards_in_progress bigint, wizards_completed_30d bigint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (select count(*) from profiles),
         (select count(*) from profiles where created_at > now() - interval '30 days'),
         (select count(distinct user_id) from memberships where last_active_at > now() - interval '30 days'),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.status = 'onboarding' and s.status in ('draft', 'email_verified') and s.expires_at > now()),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.company_id = s.company_id and s.status = 'complete' and s.created_at > now() - interval '30 days')
   where is_platform_admin()
$$;

revoke all on function platform_companies(), platform_money_stats(), platform_money_trend(), platform_overview() from public;
grant execute on function platform_companies(), platform_money_stats(), platform_money_trend(), platform_overview() to mytrakin_api;

-- Source: migrations/20261016000500_timesheet_resubmit.sql
-- A consultant could not fix a week their approver returned: saving keeps the status at 'rejected',
-- but the update policy's WITH CHECK only allowed 'draft' or 'submitted' for the new row, so every
-- save of a returned week failed with 403. Allow the row to stay 'rejected' while it is being fixed.
drop policy if exists timesheets_consultant_update on mytrakin.timesheets;
create policy timesheets_consultant_update on mytrakin.timesheets for update to mytrakin_api
  using (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant() and status in ('draft', 'rejected'))
  with check (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
              and status in ('draft', 'rejected', 'submitted'));

-- Source: migrations/20261016000600_held_status_for_payees.sql
-- =============================================================================
-- myTrakIn · 20261016 0600 · Pay-when-paid "held" status for vendors and 1099 payees
--
--   invoice_balances runs with the caller's rights (security_invoker). A vendor admin can't
--   read the client (AR) invoice an AP invoice waits for, so the "is the client invoice still
--   unpaid?" check found nothing and a held invoice showed the vendor "ready to pay".
--   client_invoice_unpaid() answers only that yes/no question (same tenant only), so the
--   payee sees "held" correctly while every AR amount stays hidden (RULE-01 / masking).
--   The view is otherwise unchanged.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.client_invoice_unpaid(p_invoice uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from invoices ar
     where ar.id = p_invoice and ar.tenant_id = ctx_tenant() and ar.direction = 'ar'
       and ar.amount - coalesce((select sum(p.amount) from payments p
                                  where p.invoice_id = ar.id and p.status in ('completed', 'confirmed')), 0) > 0)
$$;

revoke all on function mytrakin.client_invoice_unpaid(uuid) from public;
grant execute on function mytrakin.client_invoice_unpaid(uuid) to mytrakin_api;

create or replace view mytrakin.invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                              as paid,
  i.amount - coalesce(p.paid, 0)                   as balance,
  greatest(0, current_date - i.due_on)             as days_late,
  case
    when i.status = 'void'                                      then 'void'
    when i.amount - coalesce(p.paid, 0) <= 0                     then 'paid'
    when i.status = 'exception'                                  then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and mytrakin.client_invoice_unpaid(i.pay_when_paid_of)
                                                                 then 'held'
    when i.status = 'scheduled'                                  then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0     then 'overdue_part_paid'
    when i.due_on < current_date                                 then 'overdue'
    when coalesce(p.paid, 0) > 0                                 then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null   then 'ready_to_pay'
    else 'open'
  end                                              as live_status
from mytrakin.invoices i
left join (select invoice_id, sum(amount) as paid from mytrakin.payments
            where status in ('completed', 'confirmed') group by invoice_id) p on p.invoice_id = i.id;

-- Source: migrations/20261016000700_consultant_user_link.sql
-- =============================================================================
-- myTrakIn · 20261016 0700 · Link consultants to their login (U-ID shown in list/profile)
--
--   consultants.user_id was only set when the person already had a login at onboarding.
--   In the usual path (HR adds the consultant → invite → first sign-in) the sign-up trigger
--   claims the membership but never set consultants.user_id, so the consultant's U-ID
--   showed "—" for good. Keep the two in step whenever a consultant membership gets a
--   user, and backfill everyone already signed in.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.link_consultant_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if new.consultant_id is not null and new.user_id is not null then
    update consultants set user_id = new.user_id
     where id = new.consultant_id and user_id is distinct from new.user_id;
  end if;
  return new;
end
$$;

revoke all on function mytrakin.link_consultant_user() from public;

drop trigger if exists memberships_link_consultant_user on mytrakin.memberships;
create trigger memberships_link_consultant_user
  after insert or update of user_id, consultant_id on mytrakin.memberships
  for each row execute function mytrakin.link_consultant_user();

update mytrakin.consultants c set user_id = m.user_id
  from mytrakin.memberships m
 where m.consultant_id = c.id and m.user_id is not null and c.user_id is null;

-- Source: migrations/20261016000800_company_draft_discard.sql
-- =============================================================================
-- myTrakIn · 20261016 0800 · Discardable company drafts
--
--   Opening the "create your company" wizard immediately opens a tenant
--   (pending activation), so closing it early leaves an invisible draft that
--   still counts toward the 3-pending cap — and drafts never appear anywhere
--   (My companies and the platform queue both join through companies).
--   - discard_company_account() lets the owner delete their own unfinished
--     draft (onboarding, no company profile yet). Everything tenant-scoped is
--     ON DELETE CASCADE, so one delete cleans the whole draft.
--   - my_businesses() gains those drafts (kind/status 'draft' + the latest
--     open session), so My companies can show Resume / Discard.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Discard my own unfinished company draft. Returns false when there is
-- nothing discardable (already submitted, someone else's, gone).
create or replace function mytrakin.discard_company_account(p_user uuid, p_tenant uuid) returns boolean
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare gone int;
begin
  delete from mytrakin.tenants t
   where t.id = p_tenant
     and t.status = 'onboarding'
     and t.company_id is null
     and exists (select 1 from mytrakin.memberships m
                  where m.id = t.owner_membership_id
                    and m.user_id = p_user
                    and m.status = 'active');
  get diagnostics gone = row_count;
  return gone > 0;
end $$;

revoke all on function mytrakin.discard_company_account(uuid, uuid) from public;
grant execute on function mytrakin.discard_company_account(uuid, uuid) to mytrakin_api;

-- My companies, now including my own unfinished drafts (no company profile
-- yet): kind/status 'draft' with the latest open session for Resume.
-- (DROP first: the new session_id column changes the return type.)
drop function if exists mytrakin.my_businesses(uuid);
create or replace function mytrakin.my_businesses(p_user uuid)
returns table (tenant_id uuid, tenant_name text, company_id uuid, business_code text,
               company_name text, kind text, company_role text, tenant_role text, status text,
               session_id uuid)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         cm.company_role,
         (select m.role from mytrakin.memberships m
           where m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
           order by m.created_at limit 1),
         c.status, null::uuid
    from mytrakin.company_members cm
    join mytrakin.companies c on c.id = cm.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where cm.user_id = p_user and cm.status = 'active' and c.status <> 'inactive'
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         null::text, m.role, c.status, null::uuid
    from mytrakin.memberships m
    join mytrakin.companies c on c.id = m.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where m.user_id = p_user and m.status = 'active' and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind,
         null::text, m.role, c.status, null::uuid
    from mytrakin.consultants k
    join auth.users u on u.id = p_user
    join mytrakin.companies c on c.id = k.employer_company_id
    join mytrakin.tenants t on t.id = c.tenant_id
    join mytrakin.memberships m on m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
   where k.email = u.email and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
     and not exists (select 1 from mytrakin.memberships m2
                      where m2.user_id = p_user and m2.company_id = c.id and m2.status = 'active')
  union
  select t.id, t.name, null::uuid, null::text, t.name, 'draft'::text,
         null::text, m.role, 'draft'::text,
         (select s.id from mytrakin.onboarding_sessions s
           where s.tenant_id = t.id and s.created_by = p_user and s.status <> 'complete'
           order by s.created_at desc limit 1)
    from mytrakin.tenants t
    join mytrakin.memberships m on m.id = t.owner_membership_id
   where m.user_id = p_user and m.status = 'active'
     and t.status = 'onboarding' and t.company_id is null
   order by company_name
$$;
grant execute on function mytrakin.my_businesses(uuid) to mytrakin_api;

-- Source: migrations/20261016000900_company_roles.sql
-- =============================================================================
-- myTrakIn · 20261016 0900 · A company can play several roles
--
--   "What does your company do?" is now multi-select: a business can be a
--   vendor on one engagement and a client on another. companies.kinds holds
--   every role; kind stays as the primary role (first selected) so existing
--   filters, labels, imports and exports keep working.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.companies add column if not exists kinds text[];
update mytrakin.companies set kinds = array[kind] where kinds is null;
alter table mytrakin.companies alter column kinds set not null;
alter table mytrakin.companies
  add constraint companies_kinds_check
  check (kinds <> '{}' and kinds <@ array['client', 'prime_vendor', 'vendor', 'end_client']);

-- My companies also reports every role (DROP first: the return type changes).
drop function if exists mytrakin.my_businesses(uuid);
create or replace function mytrakin.my_businesses(p_user uuid)
returns table (tenant_id uuid, tenant_name text, company_id uuid, business_code text,
               company_name text, kind text, kinds text[], company_role text, tenant_role text,
               status text, session_id uuid)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         cm.company_role,
         (select m.role from mytrakin.memberships m
           where m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
           order by m.created_at limit 1),
         c.status, null::uuid
    from mytrakin.company_members cm
    join mytrakin.companies c on c.id = cm.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where cm.user_id = p_user and cm.status = 'active' and c.status <> 'inactive'
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         null::text, m.role, c.status, null::uuid
    from mytrakin.memberships m
    join mytrakin.companies c on c.id = m.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where m.user_id = p_user and m.status = 'active' and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         null::text, m.role, c.status, null::uuid
    from mytrakin.consultants k
    join auth.users u on u.id = p_user
    join mytrakin.companies c on c.id = k.employer_company_id
    join mytrakin.tenants t on t.id = c.tenant_id
    join mytrakin.memberships m on m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
   where k.email = u.email and c.status <> 'inactive'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
     and not exists (select 1 from mytrakin.memberships m2
                      where m2.user_id = p_user and m2.company_id = c.id and m2.status = 'active')
  union
  select t.id, t.name, null::uuid, null::text, t.name, 'draft'::text, array['draft']::text[],
         null::text, m.role, 'draft'::text,
         (select s.id from mytrakin.onboarding_sessions s
           where s.tenant_id = t.id and s.created_by = p_user and s.status <> 'complete'
           order by s.created_at desc limit 1)
    from mytrakin.tenants t
    join mytrakin.memberships m on m.id = t.owner_membership_id
   where m.user_id = p_user and m.status = 'active'
     and t.status = 'onboarding' and t.company_id is null
   order by company_name
$$;
grant execute on function mytrakin.my_businesses(uuid) to mytrakin_api;

-- Source: migrations/20261016001000_company_directory_all.sql
-- =============================================================================
-- myTrakIn · 20261016 1000 · Cross-tenant company directory
--
--   The company picker showed only the current tenant's companies, but an MSA
--   counterparty can be any registered business. These helpers expose ONLY
--   directory columns (id, Business ID, name, roles) for active companies in
--   every tenant — no money, no contacts, no full profiles (those stay behind
--   tenant RLS). Agreements store tenant_id + company_id, so AR/AP stays
--   strictly per-tenant (RULE-01).
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Every active company, any tenant: for pickers and suggestions.
create or replace function mytrakin.company_directory_all(p_q text default null)
returns table (id uuid, business_code text, name text, kind text, kinds text[], status text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select c.id, c.business_code, c.name, c.kind, c.kinds, c.status
    from mytrakin.companies c
   where c.status <> 'inactive'
     and (p_q is null or c.name ilike '%' || p_q || '%' or coalesce(c.business_code, '') ilike '%' || p_q || '%')
   order by c.name
$$;

-- One active company, any tenant: id + name + contact for MSA e-mails.
create or replace function mytrakin.company_counterparty(p_id uuid)
returns table (id uuid, name text, contact_email text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select c.id, c.name, c.contact_email
    from mytrakin.companies c
   where c.id = p_id and c.status <> 'inactive'
$$;

-- Just the name, any tenant: for agreement/SOW lists whose RLS join would
-- otherwise blank a cross-tenant counterparty.
create or replace function mytrakin.company_public_name(p_id uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select c.name from mytrakin.companies c where c.id = p_id and c.status <> 'inactive'
$$;

revoke all on function mytrakin.company_directory_all(text), mytrakin.company_counterparty(uuid),
  mytrakin.company_public_name(uuid) from public;
grant execute on function mytrakin.company_directory_all(text), mytrakin.company_counterparty(uuid),
  mytrakin.company_public_name(uuid) to mytrakin_api;

-- Source: migrations/20261016001100_company_codes_global.sql
-- =============================================================================
-- myTrakIn · 20261016 1100 · Company IDs are unique across the whole platform
--
--   Business IDs (C-0001 …) were numbered per tenant with a per-tenant
--   uniqueness rule, so two companies in two workspaces could both be C-0001.
--   They are now drawn from one platform-wide sequence and must be unique
--   across all companies. Every ID keeps the "C-" prefix.
--
--   Existing data: the earliest company keeps its ID; every later company that
--   shares an ID gets a fresh one. Nothing else changes.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create sequence if not exists mytrakin.company_code_seq;

-- Continue after the highest ID already issued.
select setval('mytrakin.company_code_seq',
              greatest((select coalesce(max(substring(business_code from 3)::int), 0)
                          from mytrakin.companies where business_code ~ '^C-[0-9]+$'), 1));

-- Drop the per-tenant uniqueness while colliding IDs are reassigned.
alter table mytrakin.companies drop constraint if exists companies_business_code_uq;
drop index if exists mytrakin.companies_business_code_idx;

update mytrakin.companies c
   set business_code = 'C-' || lpad(nextval('mytrakin.company_code_seq')::text, 4, '0')
  from (select id, row_number() over (partition by business_code order by created_at, id) as rn
          from mytrakin.companies) d
 where d.id = c.id and d.rn > 1;

-- One issuing function for every path (API, CSV import, seeds, triggers).
create or replace function mytrakin.next_business_code() returns text
language sql security definer set search_path = mytrakin, public, extensions as $$
  select 'C-' || lpad(nextval('mytrakin.company_code_seq')::text, 4, '0')
$$;
revoke all on function mytrakin.next_business_code() from public;
grant execute on function mytrakin.next_business_code() to mytrakin_api;

create or replace function mytrakin.assign_business_code() returns trigger
language plpgsql set search_path = mytrakin, public, extensions as $$
begin
  if NEW.business_code is null or NEW.business_code = '' then
    NEW.business_code := mytrakin.next_business_code();
  end if;
  return NEW;
end $$;

alter table mytrakin.companies drop constraint if exists companies_business_code_format;
alter table mytrakin.companies
  add constraint companies_business_code_format check (business_code ~ '^C-[0-9]{4,}$');
alter table mytrakin.companies drop constraint if exists companies_business_code_global_uq;
alter table mytrakin.companies
  add constraint companies_business_code_global_uq unique (business_code);

-- Source: migrations/20261016001200_shared_agreements.sql
-- =============================================================================
-- myTrakIn · 20261016 1200 · Agreements shared with the company they are with
--
--   An MSA is recorded in the sender's workspace. Until now only that workspace
--   could read it (tenant isolation), so the counterparty company never saw it.
--   These functions let a company's workspace read — and only read — the
--   agreements where its company is a party, and the files attached to them.
--
--   - my_company_ids():           companies the signed-in user acts for (their
--                                 workspace's company, their company membership)
--   - shared_agreements():        agreements of OTHER workspaces where one of those
--                                 companies is the counterparty or the sender.
--                                 Shown from the counterparty's side (supplier and
--                                 buyer swapped). No money: agreements carry no rates.
--   - shared_agreement_files():   files attached to a shared agreement
--   - shared_document():          one such file, for download
--
--   Nothing here lets a counterparty edit, sign for the sender, or see SOWs,
--   invoices or payments of the sender.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.my_company_ids() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct s.cid) filter (where s.cid is not null), '{}'::uuid[])
    from (
      select t.company_id as cid from mytrakin.tenants t where t.id = mytrakin.ctx_tenant()
      union all
      select mytrakin.ctx_company()
      union all
      select cm.company_id from mytrakin.company_members cm
       where cm.user_id = mytrakin.ctx_user() and cm.status = 'active'
    ) s
$$;

create or replace function mytrakin.shared_agreements()
returns table (
  id uuid, tenant_id uuid, code text, kind text, company_id uuid, initiator_company_id uuid,
  tenant_side text, effective_on date, expires_on date, payment_terms text, renewal text,
  notice_period text, insurance_required text, status text, signed_by text, source text,
  created_at timestamptz, counterparty text, sent_by_company text, shared boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with mine as (select mytrakin.my_company_ids() as ids)
  select a.id, a.tenant_id, a.code, a.kind, a.company_id, a.initiator_company_id,
         case when a.company_id = any (m.ids) and not coalesce(a.initiator_company_id = any (m.ids), false)
              then case a.tenant_side when 'supplier' then 'buyer' when 'buyer' then 'supplier' else a.tenant_side end
              else a.tenant_side end,
         a.effective_on, a.expires_on, a.payment_terms, a.renewal, a.notice_period, a.insurance_required,
         a.status, a.signed_by, a.source, a.created_at,
         case when a.company_id = any (m.ids) then sc.name else rc.name end,
         sc.name, true
    from mytrakin.agreements a
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
   where a.tenant_id is distinct from mytrakin.ctx_tenant()
     and (a.company_id = any (m.ids) or a.initiator_company_id = any (m.ids))
$$;

create or replace function mytrakin.shared_agreement_files(p_agreement uuid)
returns setof mytrakin.documents
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select d.* from mytrakin.documents d
   where d.owner_type = 'agreement' and d.owner_id = p_agreement and d.deleted_at is null
     and exists (select 1 from mytrakin.shared_agreements() s where s.id = p_agreement)
$$;

create or replace function mytrakin.shared_document(p_id uuid)
returns setof mytrakin.documents
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select d.* from mytrakin.documents d
   where d.id = p_id and d.owner_type = 'agreement' and d.deleted_at is null
     and exists (select 1 from mytrakin.shared_agreements() s where s.id = d.owner_id)
$$;

revoke all on function mytrakin.my_company_ids(), mytrakin.shared_agreements(),
  mytrakin.shared_agreement_files(uuid), mytrakin.shared_document(uuid) from public;
grant execute on function mytrakin.my_company_ids(), mytrakin.shared_agreements(),
  mytrakin.shared_agreement_files(uuid), mytrakin.shared_document(uuid) to mytrakin_api;

-- Source: migrations/20261016001300_company_directory_rls.sql
-- =============================================================================
-- myTrakIn · 20261016 1300 · Close the cross-tenant company read hole
--
--   Migration 0780 added `companies_directory`: "every non-inactive company,
--   readable by any signed-in member". Written as a bare
--   `ctx_role() not in ('anonymous','public','signer')` it grants far more
--   than a directory — it lets ANY signed-in person SELECT every row of
--   `companies` in EVERY tenant: contact e-mail, address, EIN, W-9 status and
--   data, notes, bank_verified. That is a RULE-05 / SEC-13 breach (tenant
--   isolation) and it made GET /companies/{id} answer 200 for another
--   workspace's company.
--
--   Migration 1000 already replaced the picker's need with narrow
--   security-definer functions (`company_directory_all`,
--   `company_public_name`, `company_counterparty`) that expose directory
--   columns only. So the broad policy is now redundant as well as unsafe:
--   drop it. Legitimate reads are all covered by the remaining policies —
--   `tenant_isolation` (own workspace), `companies_internal` (staff),
--   `companies_member` (a company member), `companies_own` (vendor/client
--   admin's own company) and `companies_consultant` (a consultant's chain).
--
--   Nothing is lost: the MSA counterparty picker, agreement counterparty
--   names and counterparty e-mails all go through the 1000 helpers.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_directory on mytrakin.companies;

-- Source: migrations/20261016001400_esign_documents_and_signers.sql
-- =============================================================================
-- myTrakIn · 20261017 1400 · E-signatures: several documents per envelope,
--                       signers chosen from the companies' own admins
--                       (PLAN ESG-02, AGR-07, NOT-02)
--
--   Two gaps in the "send for signature" flow:
--
--   1. An envelope carried exactly one PDF (envelopes.document_path). A packet is
--      normal in staffing — an MSA plus its SOW, or a contract and its exhibits —
--      so an envelope now holds several documents. Each one is kept in
--      `envelope_documents` (so it can be listed and removed while the envelope is
--      still a draft) and the signed copy is the documents in order, followed by
--      the certificate of completion. `document_path` / `document_sha256` stay as
--      "the merged original", so the signing link, the download and the sealing
--      code are unchanged.
--
--   2. Signers were typed in by hand, so the company that has to sign was not
--      checked against anyone, and the counterparty's admins were never told.
--      `company_signing_admins()` returns the people who may sign for a company:
--      its active owners/admins and its membership-linked vendor/client admins —
--      the same set `_can_manage_company()` accepts. It is a security definer so
--      it works for a company in another workspace (an MSA counterparty), and it
--      returns ONLY those admins' name, e-mail and role — never the rest of that
--      company, which stays behind tenant RLS (RULE-01, migration 20261016001300).
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- -----------------------------------------------------------------------------
-- Several documents per envelope
-- -----------------------------------------------------------------------------
create table if not exists mytrakin.envelope_documents (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references mytrakin.tenants (id) on delete cascade,
  envelope_id  uuid not null references mytrakin.envelopes (id) on delete cascade,
  position     smallint not null,
  name         text not null,
  storage_path text not null,
  sha256       text not null,
  size_bytes   integer,          -- null for envelopes recorded before this migration
  created_at   timestamptz not null default now()
);
create index if not exists envelope_documents_envelope_idx on mytrakin.envelope_documents (envelope_id, position);
create unique index if not exists envelope_documents_position_uq
  on mytrakin.envelope_documents (envelope_id, position);

grant select, insert, update, delete on mytrakin.envelope_documents to mytrakin_api;
alter table mytrakin.envelope_documents enable row level security;
-- Tenant isolation is the restrictive floor; the permissive policies below are what
-- actually grant access (a table with only restrictive policies allows nothing).
drop policy if exists envelope_documents_isolation on mytrakin.envelope_documents;
create policy envelope_documents_isolation on mytrakin.envelope_documents as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists envelope_documents_read on mytrakin.envelope_documents;
create policy envelope_documents_read on mytrakin.envelope_documents for select to mytrakin_api
  using (mytrakin.is_internal());
drop policy if exists envelope_documents_write on mytrakin.envelope_documents;
create policy envelope_documents_write on mytrakin.envelope_documents for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
drop policy if exists envelope_documents_change on mytrakin.envelope_documents;
create policy envelope_documents_change on mytrakin.envelope_documents for update to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'))
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
drop policy if exists envelope_documents_remove on mytrakin.envelope_documents;
create policy envelope_documents_remove on mytrakin.envelope_documents for delete to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop trigger if exists envelope_documents_audit on mytrakin.envelope_documents;
create trigger envelope_documents_audit after insert or update or delete on mytrakin.envelope_documents
  for each row execute function mytrakin.audit_row();

comment on table mytrakin.envelope_documents is
  'The PDFs one envelope asks to be signed, in order. envelopes.document_path holds the merged copy.';

-- Envelopes sent before this migration have their single PDF in
-- envelopes.document_path only. Record it, so the document list is right for them
-- and they can still be added to (the rest of a packet) while they are drafts.
insert into mytrakin.envelope_documents (tenant_id, envelope_id, position, name, storage_path, sha256)
select e.tenant_id, e.id, 1, 'document.pdf', e.document_path, e.document_sha256
  from mytrakin.envelopes e
 where e.document_path is not null
   and not exists (select 1 from mytrakin.envelope_documents d where d.envelope_id = e.id);

-- Announcing the request to the other company's admins is a step of its own in the
-- envelope's timeline.
alter table mytrakin.signature_events drop constraint if exists signature_events_event_check;
alter table mytrakin.signature_events add constraint signature_events_event_check
  check (event = any (array['created', 'sent', 'email_delivered', 'viewed', 'verified', 'consented', 'signed',
                         'declined', 'reminded', 'voided', 'completed', 'expired', 'counterparty_notified']));

-- -----------------------------------------------------------------------------
-- Who may sign for a company (read-only, cross-workspace, minimal)
-- -----------------------------------------------------------------------------
create or replace function mytrakin.company_signing_admins(p_company_id uuid)
returns table (user_id uuid, name text, email text, company_role text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  -- Company members who hold an administrative role, and the admins whose login is
  -- tied to the company. 'member' is not a signer. Ordered so the strongest role
  -- comes first: that is who the picker offers as the default.
  with admins as (
    select cm.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, cm.invited_email::text) as name,
           coalesce(p.email::text, cm.invited_email::text) as email,
           cm.company_role as company_role,
           case cm.company_role when 'super_admin' then 0 when 'owner' then 1 else 2 end as rank,
           cm.created_at
      from mytrakin.company_members cm
      left join mytrakin.profiles p on p.id = cm.user_id
     where cm.company_id = p_company_id
       and cm.status = 'active'
       and cm.company_role in ('super_admin', 'owner', 'admin')
       and (cm.user_id is not null or cm.invited_email is not null)
    union all
    select m.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, m.invited_email::text),
           coalesce(p.email::text, m.invited_email::text),
           m.role,
           3,
           m.created_at
      from mytrakin.memberships m
      left join mytrakin.profiles p on p.id = m.user_id
     where m.company_id = p_company_id
       and m.status = 'active'
       and m.role in ('vendor_admin', 'client_user')
       and (m.user_id is not null or m.invited_email is not null)
    union all
    -- The workspace that IS this company: its tenant admins (the owner above all)
    -- administer it even though a tenant_admin carries no company_id.
    select m.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, m.invited_email::text),
           coalesce(p.email::text, m.invited_email::text),
           case when m.id = t.owner_membership_id then 'owner' else m.role end,
           4,
           m.created_at
      from mytrakin.tenants t
      join mytrakin.memberships m on m.tenant_id = t.id
      left join mytrakin.profiles p on p.id = m.user_id
     where t.company_id = p_company_id
       and m.status = 'active'
       and m.role in ('tenant_admin', 'legal')
       and (m.user_id is not null or m.invited_email is not null)
  )
  select d.user_id, d.name, d.email, d.company_role
    from (
      -- One row per person (keyed on the e-mail they sign with), keeping their
      -- strongest role when they hold more than one.
      select distinct on (lower(a.email)) a.user_id, a.name, a.email, a.company_role, a.rank
        from admins a
       where a.email is not null
       order by lower(a.email), a.rank, a.name
    ) d
   order by d.rank, d.name
$$;

comment on function mytrakin.company_signing_admins(uuid) is
  'Admins of one company who may sign for it: name, e-mail and role only. Cross-workspace by design.';

revoke all on function mytrakin.company_signing_admins(uuid) from public;
grant execute on function mytrakin.company_signing_admins(uuid) to mytrakin_api;

-- Source: migrations/20261016001500_master_agreement_lifecycle.sql
-- =============================================================================
-- myTrakIn · 20261016 1300 · MSA lifecycle between two companies
--
--   pending   sent by company A, waiting for company B
--   accepted  B accepted: the MSA is in force
--   rejected  B rejected it, with a note
--   expired   past its end date (set by expire_master_agreements, run daily)
--   Only one live MSA (pending, accepted or legacy active) may exist between two
--   companies, whichever way round it was sent. A renewal is a separate request
--   on the MSA: the other company accepts it (the end date moves) or declines
--   it with a note.
--   Cross-company writes go through security-definer functions: company B can't
--   update rows in company A's workspace.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- 1. Statuses ----------------------------------------------------------------
do $$ declare c record; begin
  for c in select conname from pg_constraint
            where conrelid = 'mytrakin.agreements'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) ilike '%status%' loop
    execute format('alter table mytrakin.agreements drop constraint %I', c.conname);
  end loop;
end $$;
alter table mytrakin.agreements add constraint agreements_status_check
  check (status in ('draft', 'out_for_signature', 'pending', 'accepted', 'rejected', 'active', 'expired', 'terminated'));

alter table mytrakin.agreements
  add column if not exists decided_on    timestamptz,
  add column if not exists decided_by    uuid,
  add column if not exists decision_note text;

-- 2. Who a row is between ------------------------------------------------------
-- The company that sent an agreement: the company the workspace represents, or
-- the company it was initiated from. Falls back to the workspace itself.
create or replace function mytrakin.agreement_sender_key(p_tenant uuid, p_initiator uuid) returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(p_initiator, (select t.company_id from mytrakin.tenants t where t.id = p_tenant), p_tenant)
$$;

-- Which side of an agreement the signed-in user acts for: 'counterparty', 'sender' or null.
create or replace function mytrakin.my_side(p_agreement uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select case
           when a.company_id = any (mytrakin.my_company_ids()) then 'counterparty'
           when a.tenant_id = mytrakin.ctx_tenant()
             or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = any (mytrakin.my_company_ids()) then 'sender'
         end
    from mytrakin.agreements a where a.id = p_agreement
$$;

-- 3. One live MSA between two companies ----------------------------------------
create or replace function mytrakin.enforce_one_live_master() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare me uuid; other record; key text;
begin
  if NEW.kind in ('msa', 'subcontract') and NEW.company_id is not null
     and NEW.status in ('pending', 'accepted', 'active') then
    me := mytrakin.agreement_sender_key(NEW.tenant_id, NEW.initiator_company_id);
    key := least(me, NEW.company_id)::text || ':' || greatest(me, NEW.company_id)::text;
    perform pg_advisory_xact_lock(hashtextextended(key, 0));
    select o.id, o.code into other from mytrakin.agreements o
     where o.id <> NEW.id and o.kind in ('msa', 'subcontract') and o.company_id is not null
       and o.status in ('pending', 'accepted', 'active')
       and ((o.company_id = NEW.company_id
             and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = me)
         or (o.company_id = me
             and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = NEW.company_id))
     limit 1;
    if other.id is not null then
      raise exception 'There is already an active MSA between these two companies (%). End or expire it first.', other.code
        using errcode = 'MT409';
    end if;
  end if;
  return NEW;
end $$;

drop trigger if exists agreements_one_live_master on mytrakin.agreements;
create trigger agreements_one_live_master
  before insert or update of status, kind, company_id, initiator_company_id, tenant_id on mytrakin.agreements
  for each row execute function mytrakin.enforce_one_live_master();

-- 4. Renewal requests ----------------------------------------------------------
create table if not exists mytrakin.agreement_renewals (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references mytrakin.tenants (id) on delete cascade,
  agreement_id         uuid not null references mytrakin.agreements (id) on delete cascade,
  requested_side       text not null check (requested_side in ('sender', 'counterparty')),
  requested_by         uuid,
  requested_by_name    text,
  requested_on         timestamptz not null default now(),
  proposed_expires_on  date not null,
  note                 text,
  status               text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  decided_by           uuid,
  decided_on           timestamptz,
  decision_note        text
);
create unique index if not exists agreement_renewals_one_pending
  on mytrakin.agreement_renewals (agreement_id) where status = 'pending';
create index if not exists agreement_renewals_agreement_idx on mytrakin.agreement_renewals (agreement_id, requested_on desc);

grant select, insert, update on mytrakin.agreement_renewals to mytrakin_api;
alter table mytrakin.agreement_renewals enable row level security;
drop policy if exists agreement_renewals_tenant on mytrakin.agreement_renewals;
create policy agreement_renewals_tenant on mytrakin.agreement_renewals for all to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());

-- 5. Actions by a party ----------------------------------------------------------
-- The counterparty accepts or rejects a pending MSA.
create or replace function mytrakin.respond_to_agreement(p_agreement uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'reject') then
    raise exception 'The decision must be accept or reject' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = p_agreement for update;
  if not found then raise exception 'Agreement not found' using errcode = 'MT404'; end if;
  if a.company_id is null or not (a.company_id = any (mytrakin.my_company_ids())) then
    raise exception 'Only the company this MSA was sent to can accept or reject it' using errcode = 'MT403';
  end if;
  if a.status <> 'pending' then
    raise exception 'This MSA is no longer waiting for an answer' using errcode = 'MT409';
  end if;
  if p_decision = 'reject' and note is null then
    raise exception 'Say why you are rejecting it' using errcode = 'MT422';
  end if;
  update mytrakin.agreements
     set status = case p_decision when 'accept' then 'accepted' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = note
   where id = p_agreement;
end $$;

-- Either party asks to renew an MSA that is in force (or expired).
create or replace function mytrakin.request_renewal(p_agreement uuid, p_expires date, p_note text default null)
returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; side text; who text; rid uuid;
begin
  select * into a from mytrakin.agreements where id = p_agreement;
  if not found then raise exception 'Agreement not found' using errcode = 'MT404'; end if;
  side := mytrakin.my_side(p_agreement);
  if side is null then raise exception 'You are not a party to this agreement' using errcode = 'MT403'; end if;
  if a.kind not in ('msa', 'subcontract') then
    raise exception 'Only MSAs and subcontracts are renewed this way' using errcode = 'MT422';
  end if;
  if a.status not in ('accepted', 'active', 'expired') then
    raise exception 'Only an accepted MSA can be renewed' using errcode = 'MT409';
  end if;
  if p_expires is null or p_expires <= current_date then
    raise exception 'The new end date must be in the future' using errcode = 'MT422';
  end if;
  if a.status <> 'expired' and a.expires_on is not null and p_expires <= a.expires_on then
    raise exception 'The renewal must end after the current end date' using errcode = 'MT422';
  end if;
  if side = 'counterparty' then
    who := (select name from mytrakin.companies where id = a.company_id);
  else
    who := coalesce(
      (select c.name from mytrakin.companies c where c.id = mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)),
      (select t.name from mytrakin.tenants t where t.id = a.tenant_id));
  end if;
  begin
    insert into mytrakin.agreement_renewals (tenant_id, agreement_id, requested_side, requested_by, requested_by_name,
                                             proposed_expires_on, note)
    values (a.tenant_id, p_agreement, side, mytrakin.ctx_user(), who, p_expires, nullif(trim(coalesce(p_note, '')), ''))
    returning id into rid;
  exception when unique_violation then
    raise exception 'A renewal request is already waiting for an answer' using errcode = 'MT409';
  end;
  return rid;
end $$;

-- The other party accepts a renewal (the end date moves) or declines it with a note.
create or replace function mytrakin.respond_to_renewal(p_renewal uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare r record; a record; side text; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'decline') then
    raise exception 'The decision must be accept or decline' using errcode = 'MT422';
  end if;
  select * into r from mytrakin.agreement_renewals where id = p_renewal for update;
  if not found then raise exception 'Renewal request not found' using errcode = 'MT404'; end if;
  if r.status <> 'pending' then raise exception 'This renewal was already answered' using errcode = 'MT409'; end if;
  side := mytrakin.my_side(r.agreement_id);
  if side is null or side = r.requested_side then
    raise exception 'Only the other company can answer this renewal request' using errcode = 'MT403';
  end if;
  if p_decision = 'decline' and note is null then
    raise exception 'Say why you are declining the renewal' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = r.agreement_id;
  if p_decision = 'accept' then
    update mytrakin.agreements
       set expires_on = r.proposed_expires_on,
           status = case when status = 'expired' then 'accepted' else status end
     where id = a.id;
  end if;
  update mytrakin.agreement_renewals
     set status = case p_decision when 'accept' then 'accepted' else 'declined' end,
         decided_by = mytrakin.ctx_user(), decided_on = now(), decision_note = note
   where id = r.id;
end $$;

-- Renewal history of an agreement, for either party.
create or replace function mytrakin.agreement_renewals_for(p_agreement uuid)
returns table (id uuid, requested_side text, requested_by_name text, requested_on timestamptz,
               proposed_expires_on date, note text, status text, decided_on timestamptz, decision_note text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select r.id, r.requested_side, r.requested_by_name, r.requested_on, r.proposed_expires_on, r.note,
         r.status, r.decided_on, r.decision_note
    from mytrakin.agreement_renewals r
   where r.agreement_id = p_agreement and mytrakin.my_side(p_agreement) is not null
   order by r.requested_on desc
$$;

-- 6. Expiry ----------------------------------------------------------------------
-- Run daily by the cron job: MSAs past their end date move to expired.
create or replace function mytrakin.expire_master_agreements() returns int
language sql security definer set search_path = mytrakin, public, extensions as $$
  with gone as (
    update mytrakin.agreements set status = 'expired'
     where kind in ('msa', 'subcontract') and status in ('accepted', 'active')
       and expires_on is not null and expires_on < current_date
    returning 1)
  select count(*)::int from gone
$$;

revoke all on function mytrakin.agreement_sender_key(uuid, uuid), mytrakin.my_side(uuid),
  mytrakin.respond_to_agreement(uuid, text, text), mytrakin.request_renewal(uuid, date, text),
  mytrakin.respond_to_renewal(uuid, text, text), mytrakin.agreement_renewals_for(uuid),
  mytrakin.expire_master_agreements() from public;
grant execute on function mytrakin.agreement_sender_key(uuid, uuid), mytrakin.my_side(uuid),
  mytrakin.respond_to_agreement(uuid, text, text), mytrakin.request_renewal(uuid, date, text),
  mytrakin.respond_to_renewal(uuid, text, text), mytrakin.agreement_renewals_for(uuid),
  mytrakin.expire_master_agreements() to mytrakin_api;

-- Source: migrations/20261016001501_fix_respond_variables.sql
-- =============================================================================
-- myTrakIn · 20261016 1301 · Fix: decide_renewal / respond_to_agreement variable names
--
--   In respond_to_renewal the PL/pgSQL variable `note` collided with the
--   agreement_renewals.note column, so declining a renewal with a note failed
--   with an ambiguous-column error. The variables are renamed. Behaviour is
--   unchanged otherwise.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.respond_to_agreement(p_agreement uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; v_note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'reject') then
    raise exception 'The decision must be accept or reject' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = p_agreement for update;
  if not found then raise exception 'Agreement not found' using errcode = 'MT404'; end if;
  if a.company_id is null or not (a.company_id = any (mytrakin.my_company_ids())) then
    raise exception 'Only the company this MSA was sent to can accept or reject it' using errcode = 'MT403';
  end if;
  if a.status <> 'pending' then
    raise exception 'This MSA is no longer waiting for an answer' using errcode = 'MT409';
  end if;
  if p_decision = 'reject' and v_note is null then
    raise exception 'Say why you are rejecting it' using errcode = 'MT422';
  end if;
  update mytrakin.agreements
     set status = case p_decision when 'accept' then 'accepted' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = v_note
   where id = p_agreement;
end $$;

create or replace function mytrakin.respond_to_renewal(p_renewal uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare r record; a record; side text; v_note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'decline') then
    raise exception 'The decision must be accept or decline' using errcode = 'MT422';
  end if;
  select * into r from mytrakin.agreement_renewals where id = p_renewal for update;
  if not found then raise exception 'Renewal request not found' using errcode = 'MT404'; end if;
  if r.status <> 'pending' then raise exception 'This renewal was already answered' using errcode = 'MT409'; end if;
  side := mytrakin.my_side(r.agreement_id);
  if side is null or side = r.requested_side then
    raise exception 'Only the other company can answer this renewal request' using errcode = 'MT403';
  end if;
  if p_decision = 'decline' and v_note is null then
    raise exception 'Say why you are declining the renewal' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = r.agreement_id;
  if p_decision = 'accept' then
    update mytrakin.agreements
       set expires_on = r.proposed_expires_on,
           status = case when status = 'expired' then 'accepted' else status end
     where id = a.id;
  end if;
  update mytrakin.agreement_renewals
     set status = case p_decision when 'accept' then 'accepted' else 'declined' end,
         decided_by = mytrakin.ctx_user(), decided_on = now(), decision_note = v_note
   where id = r.id;
end $$;

revoke all on function mytrakin.respond_to_agreement(uuid, text, text), mytrakin.respond_to_renewal(uuid, text, text) from public;
grant execute on function mytrakin.respond_to_agreement(uuid, text, text), mytrakin.respond_to_renewal(uuid, text, text) to mytrakin_api;

-- Source: migrations/20261016001600_consultant_directory_and_access.sql
-- =============================================================================
-- myTrakIn · 20261016 1600 · Onboard a consultant from anywhere on the platform
--
--   The consultant picker searches every registered myTrakIn user, not just the people
--   already linked to this workspace, so HR can onboard somebody who has never been in
--   this company. Two things follow from that:
--
--   1. The read side already worked: profiles and user_codes are readable by any
--      signed-in internal role, so no new policy is needed for the search itself.
--   2. The write side did not. `memberships_admin` is tenant_admin-only, so HR,
--      account managers and legal could not create the membership that gives a new
--      consultant access -- onboarding only ever worked for an owner doing it by hand.
--      grant_consultant_access() is a narrow SECURITY DEFINER entry point: it may only
--      create a *consultant* membership (or attach the consultant link to an existing
--      membership, keeping that person's role), never change anybody's role or status.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Gives one person access to this workspace as a consultant. Keeps the role they
-- already have if they are a member here in another capacity (a viewer, say) -- being
-- onboarded must not quietly demote somebody who is also staff.
create or replace function mytrakin.grant_consultant_access(
  p_tenant uuid, p_user uuid, p_consultant uuid, p_title text)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if p_tenant is distinct from mytrakin.ctx_tenant()
     or not mytrakin.can('hr', 'account_manager', 'legal') then
    raise exception 'not allowed' using errcode = '42501';
  end if;

  insert into mytrakin.memberships (tenant_id, user_id, role, consultant_id, title, status)
  values (p_tenant, p_user, 'consultant', p_consultant, p_title, 'active')
  on conflict (tenant_id, user_id) where user_id is not null
  do update set consultant_id = excluded.consultant_id,
                title = coalesce(memberships.title, excluded.title);
end
$$;

revoke all on function mytrakin.grant_consultant_access(uuid, uuid, uuid, text) from public;
grant execute on function mytrakin.grant_consultant_access(uuid, uuid, uuid, text) to mytrakin_api;

-- No read-side change is needed for the search: `profiles_read` and `user_codes_read`
-- already let any signed-in role read them, and the API only exposes id, U-ID, name,
-- e-mail and mobile -- the details onboarding needs and nothing more.

-- Source: migrations/20261016001700_sow_approval.sql
-- =============================================================================
-- myTrakIn · 20261016 1700 · SOWs run both ways under one MSA, with approval
--
--   An MSA between two companies is one agreement whichever workspace recorded it,
--   so work under it must be possible from either side. Two things were in the way:
--
--   1. Creating a SOW under the other workspace's MSA was impossible. POST /sows read
--      the agreement with a plain SELECT, and the restrictive tenant_isolation policy
--      hides another workspace's agreement rows, so the counterparty got a 404 for an
--      MSA they could plainly see in GET /agreements.
--   2. Even with the row visible, a SOW copied `company_id` from the agreement. Seen
--      from the counterparty's side that is *their own* company, so the SOW would have
--      pointed back at the wrong party. agreement_peer_company() resolves the other
--      company from wherever you are standing.
--
--   Approval, mirroring the MSA lifecycle (01500):
--     draft     created, not sent -- invisible to the other company
--     pending   sent to the other company for approval
--     active    approved by them, or recorded as already signed
--     rejected  turned down, with the reason kept on the row
--
--   A sent SOW is shared read-only and without money: the other company sees the
--   reference, title, term and status, never the value ceiling, invoiced or paid
--   amounts. Only the workspace that created it can see those, and only it can amend.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- 1. Statuses and the decision --------------------------------------------------
do $$ declare c record; begin
  for c in select conname from pg_constraint
            where conrelid = 'mytrakin.sows'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) ilike '%status%' loop
    execute format('alter table mytrakin.sows drop constraint %I', c.conname);
  end loop;
end $$;
alter table mytrakin.sows add constraint sows_status_check
  check (status in ('draft', 'pending', 'out_for_signature', 'active', 'rejected', 'ended', 'terminated'));

alter table mytrakin.sows
  add column if not exists decided_on    timestamptz,
  add column if not exists decided_by    uuid,
  add column if not exists decision_note text,
  add column if not exists sent_on       timestamptz;

-- 2. The other company, from where you stand -------------------------------------
-- I am the sender  -> the peer is the agreement's company_id.
-- I am the counterparty -> the peer is whoever sent it.
-- Null when the other side is not a company (1099 work orders have no company peer).
create or replace function mytrakin.agreement_peer_company(p_agreement uuid) returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select case when a.id is null then null
              when a.tenant_id = mytrakin.ctx_tenant()
                or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = any (mytrakin.my_company_ids())
                then a.company_id
              else mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)
         end
    from mytrakin.agreements a
   where a.id = p_agreement
     and exists (select 1 from mytrakin.companies c
                  where c.id = case when a.tenant_id = mytrakin.ctx_tenant()
                                      or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)
                                           = any (mytrakin.my_company_ids())
                                     then a.company_id
                                     else mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) end)
$$;

-- The SOWs another workspace created under an agreement we are a party to, and has
-- actually sent. A draft is the other company's work in progress, not ours to see.
create or replace function mytrakin.shared_sows()
returns table (
  id uuid, code text, title text, side text, status text, start_date date, end_date date,
  agreement_code text, agreement_id uuid, counterparty text, sent_by text,
  sent_on timestamptz, decided_on timestamptz, decision_note text, shared boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with mine as (select mytrakin.my_company_ids() as ids)
  select s.id, s.code, s.title,
         case when s.side = 'we_bill' then 'we_pay' else 'we_bill' end,
         s.status, s.start_date, s.end_date,
         a.code, a.id,
         -- the other company on the MSA, from where the reader stands
         case when a.company_id = any (m.ids) then sc.name else rc.name end,
         coalesce(s_t.name, sc.name),
         s.sent_on, s.decided_on, s.decision_note, true
    from mytrakin.sows s
    join mytrakin.agreements a on a.id = s.agreement_id
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    join mytrakin.tenants s_t on s_t.id = s.tenant_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
   where s.tenant_id is distinct from mytrakin.ctx_tenant()
     and s.status <> 'draft'
     and exists (select 1 from mytrakin.companies mine_c
                  where mine_c.id = any (m.ids)
                    and (mine_c.id = a.company_id or mine_c.id = coalesce(a.initiator_company_id, t.company_id)))
$$;

-- 3. Send for approval, and the other company's answer --------------------------
create or replace function mytrakin.submit_sow_for_approval(p_sow uuid) returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; peer uuid;
begin
  select * into s from mytrakin.sows where id = p_sow for update;
  if not found then raise exception 'SOW not found' using errcode = 'MT404'; end if;
  if s.tenant_id is distinct from mytrakin.ctx_tenant() then
    raise exception 'This SOW belongs to another workspace' using errcode = 'MT403';
  end if;
  if s.status <> 'draft' then
    raise exception 'This SOW has already been sent' using errcode = 'MT409';
  end if;
  peer := mytrakin.agreement_peer_company(s.agreement_id);
  if peer is null then
    raise exception 'There is no other company on this agreement to send it to' using errcode = 'MT422';
  end if;
  update mytrakin.sows set status = 'pending', sent_on = now() where id = p_sow;
end $$;

-- The company it was sent to approves it (it comes into force) or turns it down.
-- The sender of the SOW cannot answer their own SOW: it is the *other* party to the
-- agreement who does that, and only if their company is one of ours.
create or replace function mytrakin.respond_to_sow(p_sow uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('approve', 'reject') then
    raise exception 'The decision must be approve or reject' using errcode = 'MT422';
  end if;
  select * into s from mytrakin.sows where id = p_sow for update;
  if not found then raise exception 'SOW not found' using errcode = 'MT404'; end if;
  if s.tenant_id = mytrakin.ctx_tenant() then
    raise exception 'This is your own SOW — only the company it was sent to can answer it' using errcode = 'MT403';
  end if;
  if mytrakin.my_side(s.agreement_id) is null then
    raise exception 'You are not a party to this agreement' using errcode = 'MT403';
  end if;
  if s.status <> 'pending' then
    raise exception 'This SOW is not waiting for an answer' using errcode = 'MT409';
  end if;
  if p_decision = 'reject' and note is null then
    raise exception 'Say why you are turning it down' using errcode = 'MT422';
  end if;
  update mytrakin.sows
     set status = case p_decision when 'approve' then 'active' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = note
   where id = p_sow;
end $$;

revoke all on function mytrakin.agreement_peer_company(uuid), mytrakin.shared_sows(),
  mytrakin.submit_sow_for_approval(uuid), mytrakin.respond_to_sow(uuid, text, text) from public;
grant execute on function mytrakin.agreement_peer_company(uuid), mytrakin.shared_sows(),
  mytrakin.submit_sow_for_approval(uuid), mytrakin.respond_to_sow(uuid, text, text) to mytrakin_api;

-- Source: migrations/20261016001800_signature_never_blocked.sql
-- =============================================================================
-- myTrakIn · 20261016 1800 · A signature is never refused
--
--   Signing DREP's MSA for Velocity failed with "There is already an active MSA
--   between these two companies (MSA-DREPSOFTWARE-001)". Two things had gone wrong:
--
--   1. Velocity could raise a counter-MSA while DREP's was out_for_signature,
--      because the trigger only counts pending/accepted/active as "live". Both
--      companies then held an unsigned MSA for the same pair.
--   2. When the last signer finished, completion set the agreement to 'accepted'.
--      That is an UPDATE, so the same trigger fired, spotted the other pending MSA
--      and raised -- aborting the whole transaction. The signature was real and had
--      been recorded in the audit trail, yet the request failed and the signer was
--      told to try again. Recording a signature may never be refused.
--
--   Now:
--     - the rule guards *creating* a second live MSA, which is where duplicates
--       actually come from. A status change on an agreement that already exists
--       never raises.
--     - when an MSA comes into force, the opposite-direction agreement for the same
--       pair that has NOT come into force is superseded rather than left dangling:
--       it is the same commercial relationship, and keeping both 'pending' leaves
--       two people waiting on each other. An MSA already in force is left alone --
--       a signature must never quietly end a live agreement.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.enforce_one_live_master() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare me uuid; other record; key text; incoming boolean;
begin
  if NEW.kind not in ('msa', 'subcontract') or NEW.company_id is null
     or NEW.status not in ('pending', 'accepted', 'active') then
    return NEW;                                    -- drafts and unsigned copies are not "live"
  end if;

  me := mytrakin.agreement_sender_key(NEW.tenant_id, NEW.initiator_company_id);
  key := least(me, NEW.company_id)::text || ':' || greatest(me, NEW.company_id)::text;
  perform pg_advisory_xact_lock(hashtextextended(key, 0));

  select o.id, o.code, o.status into other from mytrakin.agreements o
   where o.id <> NEW.id and o.kind in ('msa', 'subcontract') and o.company_id is not null
     and o.status in ('pending', 'accepted', 'active')
     and ((o.company_id = NEW.company_id
           and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = me)
       or (o.company_id = me
           and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = NEW.company_id))
   limit 1;
  if other.id is null then
    return NEW;
  end if;

  incoming := NEW.status in ('accepted', 'active');

  -- This agreement has just come into force: retire the other side's copy of the
  -- same relationship if it is still unsigned, so the pair settles on one agreement.
  if TG_OP = 'UPDATE' and incoming and other.status not in ('accepted', 'active') then
    update mytrakin.agreements
       set status = 'terminated',
           decision_note = coalesce(nullif(decision_note, ''),
                                   'Superseded by ' || NEW.code || ', which covers the same agreement between these two companies.')
     where id = other.id;
    return NEW;
  end if;

  -- Creating a second live MSA for a pair that already has one is the case worth
  -- stopping: it is a duplicate nobody asked for.
  if TG_OP = 'INSERT' then
    raise exception 'There is already an active MSA between these two companies (%). End or expire it first.', other.code
      using errcode = 'MT409';
  end if;

  -- An UPDATE that is not a coming-into-force (re-dating, re-pointing at a company,
  -- correcting a status) never blocks anything.
  return NEW;
end $$;

-- Source: migrations/20261018000100_credit_notes.sql
-- =============================================================================
-- myTrakIn · 20261018 0100 · Credit notes against client invoices (PLAN AR-06, TS-07)
--
--   A credit note lowers what the customer owes on one AR invoice (billing error, holiday
--   hours at the regular rate, a correction after an approved timesheet changes). It is
--   never more than the invoice's open balance. invoice_balances now subtracts credits, so
--   aging, dashboards, payment caps and pay-when-paid release all follow automatically.
--   Status is derived: "open" while the invoice still has a balance, "applied" once settled.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.credit_notes (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references mytrakin.tenants (id) on delete cascade,
  number      text not null,
  invoice_id  uuid not null references mytrakin.invoices (id) on delete cascade,
  issued_on   date not null default current_date,
  reason      text not null,
  amount      numeric(14, 2) not null check (amount > 0),
  created_by  uuid,
  created_at  timestamptz not null default now(),
  unique (tenant_id, number)
);
create index if not exists credit_notes_invoice_idx on mytrakin.credit_notes (invoice_id);

grant select, insert on mytrakin.credit_notes to mytrakin_api;
alter table mytrakin.credit_notes enable row level security;
drop policy if exists tenant_isolation on mytrakin.credit_notes;
create policy tenant_isolation on mytrakin.credit_notes as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
-- Staff, and the customer the invoice is billed to (AR money is never shown to vendors or consultants).
drop policy if exists credit_notes_read on mytrakin.credit_notes;
create policy credit_notes_read on mytrakin.credit_notes for select to mytrakin_api
  using (mytrakin.is_internal() or (mytrakin.ctx_role() = 'client_user' and exists (
           select 1 from mytrakin.invoices i where i.id = credit_notes.invoice_id and i.company_id = mytrakin.ctx_company())));
drop policy if exists credit_notes_write on mytrakin.credit_notes;
create policy credit_notes_write on mytrakin.credit_notes for insert to mytrakin_api with check (mytrakin.can('finance'));

drop trigger if exists credit_notes_audit on mytrakin.credit_notes;
create trigger credit_notes_audit after insert or update or delete on mytrakin.credit_notes
  for each row execute function mytrakin.audit_row();

-- Pay-when-paid: a client invoice settled by payments plus credits releases the vendor invoice.
create or replace function mytrakin.client_invoice_unpaid(p_invoice uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from invoices ar
     where ar.id = p_invoice and ar.tenant_id = ctx_tenant() and ar.direction = 'ar'
       and ar.amount - coalesce((select sum(p.amount) from payments p
                                  where p.invoice_id = ar.id and p.status in ('completed', 'confirmed')), 0)
                     - coalesce((select sum(c.amount) from credit_notes c where c.invoice_id = ar.id), 0) > 0)
$$;

-- Same view as 20261016000600 with credits subtracted from the balance; "credited" is appended last.
create or replace view mytrakin.invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                                             as paid,
  i.amount - coalesce(p.paid, 0) - coalesce(c.credited, 0)        as balance,
  greatest(0, current_date - i.due_on)                            as days_late,
  case
    when i.status = 'void'                                                         then 'void'
    when i.amount - coalesce(p.paid, 0) - coalesce(c.credited, 0) <= 0             then 'paid'
    when i.status = 'exception'                                                    then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and mytrakin.client_invoice_unpaid(i.pay_when_paid_of)                    then 'held'
    when i.status = 'scheduled'                                                    then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0                       then 'overdue_part_paid'
    when i.due_on < current_date                                                   then 'overdue'
    when coalesce(p.paid, 0) > 0                                                   then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null                     then 'ready_to_pay'
    else 'open'
  end                                                             as live_status,
  coalesce(c.credited, 0)                                         as credited
from mytrakin.invoices i
left join (select invoice_id, sum(amount) as paid from mytrakin.payments
            where status in ('completed', 'confirmed') group by invoice_id) p on p.invoice_id = i.id
left join (select invoice_id, sum(amount) as credited from mytrakin.credit_notes group by invoice_id) c on c.invoice_id = i.id;

-- Source: migrations/20261019000100_shared_projects.sql
-- =============================================================================
-- myTrakIn · 20261019 0100 · Projects another company assigned to us (T011303-1047)
--
-- Company A puts Company B on one of A's projects by sending B a SOW / work order
-- for it. Projects live in their own workspace, so B never saw that project when
-- placing a consultant. Now:
--   - shared_projects(): A's live projects that have a SOW sent to one of our
--     companies (visibility = shared_sows()). Names and dates only — no money.
--   - projects.source_project_id: B's own copy of such a project, created the
--     first time B places someone on it. Timesheets, invoices and rates stay in
--     B's workspace (AR/AP only, RULE-01).
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.projects
  add column if not exists source_project_id uuid references mytrakin.projects (id) on delete set null;
create unique index if not exists projects_source_once on mytrakin.projects (tenant_id, source_project_id)
  where source_project_id is not null;

create or replace function mytrakin.shared_projects()
returns table (id uuid, code text, name text, status text, start_date date, end_date date, description text,
               client_company_id uuid, client text, assigned_by_company_id uuid, assigned_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select distinct on (p.id)
         p.id, p.code, p.name, p.status, p.start_date, p.end_date, p.description,
         p.client_company_id, cl.name,
         mytrakin.agreement_peer_company(s.agreement_id), mytrakin.company_public_name(mytrakin.agreement_peer_company(s.agreement_id))
    from mytrakin.shared_sows() ss
    join mytrakin.sows s on s.id = ss.id
    join mytrakin.projects p on p.id = s.project_id
    left join mytrakin.companies cl on cl.id = p.client_company_id
   where ss.status not in ('rejected', 'ended', 'terminated')
     and p.status in ('active', 'planned')
     and p.tenant_id is distinct from mytrakin.ctx_tenant()
   order by p.id
$$;

revoke all on function mytrakin.shared_projects() from public;
grant execute on function mytrakin.shared_projects() to mytrakin_api;

-- Source: migrations/20261020000100_timesheet_two_level_approval.sql
-- =============================================================================
-- myTrakIn · 20261020000100 · Two-level timesheet approval
--
-- A timesheet must be approved by both companies on the placement chain:
--   - the Placed By company (the vendor that placed the consultant, ap_company_id)
--   - the End Client company (end_client_company_id)
--
-- Once both companies approve, the timesheet is fully approved.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.timesheets
  add column if not exists placed_by_approved boolean not null default false,
  add column if not exists end_client_approved boolean not null default false;

create index if not exists timesheets_placed_by_approved_idx on mytrakin.timesheets (placed_by_approved);
create index if not exists timesheets_end_client_approved_idx on mytrakin.timesheets (end_client_approved);

-- Source: migrations/20261021000100_timesheet_weekend_confirmation.sql
-- =============================================================================
-- myTrakIn · 20261021 0100 · Weekend-hours confirmation workflow
--
--   Weekend hours stay a "review" check, but approval is now gated: the approver
--   asks the consultant to confirm the weekend work (optionally with a note), the
--   consultant is told by e-mail (logged in notifications) and sees a banner in
--   My timesheet, and the week can only be approved once the consultant confirms.
--   Rejecting, returning or resubmitting clears the state so every round starts
--   fresh.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.timesheets
  add column if not exists weekend_requested_by uuid,
  add column if not exists weekend_requested_at timestamptz,
  add column if not exists weekend_review_note text,
  add column if not exists weekend_confirmed boolean not null default false,
  add column if not exists weekend_confirmed_by uuid,
  add column if not exists weekend_confirmed_at timestamptz;

-- Source: migrations/20261021000200_client_timesheet_approval.sql
-- =============================================================================
-- myTrakIn · 20261021 0200 · End-client approval of placed-by timesheets
--
--   Two-level approval: the company that placed the consultant approves first
--   (its staff, in its own workspace). The end client approves second — but only
--   that company's own representative can do it: someone the placing company
--   invited into its workspace as a member of the end client's company
--   (client_user with company_id = the end client). These policies give that
--   representative read access to the timesheet and the right to approve it.
--   Everything else stays as-is: money columns are masked for client_user by
--   the API layer, and other roles are untouched.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create policy timesheets_client_read on mytrakin.timesheets for select to mytrakin_api
  using (ctx_role() = 'client_user' and timesheets.status in ('submitted', 'approved') and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()));

create policy timesheets_client_approve on mytrakin.timesheets for update to mytrakin_api
  using (ctx_role() = 'client_user' and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()))
  with check (ctx_role() = 'client_user' and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()));

-- The review page joins the consultant's details; let the end client's
-- representative see the consultants behind the timesheets they must approve.
create policy consultants_client_read on mytrakin.consultants for select to mytrakin_api
  using (ctx_role() = 'client_user' and exists (
           select 1 from timesheets t join timesheet_entries e on e.timesheet_id = t.id
                 join placements p on p.id = e.placement_id
            where t.consultant_id = consultants.id
              and p.end_client_company_id = ctx_company()));

-- Source: migrations/20261021000300_fix_client_policy_recursion.sql
-- =============================================================================
-- myTrakIn · 20261021 0300 · Fix RLS recursion from the client-approval policies
--
--   20261021000200 wrote the end-client checks as EXISTS over timesheet_entries;
--   entries_read itself exists-checks timesheets, so planning any timesheets
--   query looped (Postgres: "infinite recursion detected in policy") and every
--   role got a 500 — the week overview, history and review pages all died.
--   Re-express the checks through a SECURITY DEFINER helper on placements
--   (which never re-enters the timesheets policies), then recreate the policies.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists timesheets_client_read on mytrakin.timesheets;
drop policy if exists timesheets_client_approve on mytrakin.timesheets;
drop policy if exists consultants_client_read on mytrakin.consultants;

create or replace function mytrakin.client_is_end_client(p_consultant uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from mytrakin.placements p
     where p.consultant_id = p_consultant
       and p.end_client_company_id = mytrakin.ctx_company());
$$;

revoke all on function mytrakin.client_is_end_client(uuid) from public;
grant execute on function mytrakin.client_is_end_client(uuid) to mytrakin_api;

create policy timesheets_client_read on mytrakin.timesheets for select to mytrakin_api
  using (ctx_role() = 'client_user' and timesheets.status in ('submitted', 'approved')
         and mytrakin.client_is_end_client(timesheets.consultant_id));

create policy timesheets_client_approve on mytrakin.timesheets for update to mytrakin_api
  using (ctx_role() = 'client_user' and mytrakin.client_is_end_client(timesheets.consultant_id))
  with check (ctx_role() = 'client_user' and mytrakin.client_is_end_client(timesheets.consultant_id));

-- The review page joins the consultant's details; let the end client's
-- representative see the consultants behind the timesheets they must approve.
create policy consultants_client_read on mytrakin.consultants for select to mytrakin_api
  using (ctx_role() = 'client_user' and mytrakin.client_is_end_client(consultants.id));

-- Source: migrations/20261021000400_ts_approval_links.sql
-- =============================================================================
-- myTrakIn · 20261021 0400 · End-client timesheet approval links
--
--   The placed-by company approves first; the week then flows to the end client's
--   timesheet manager. That person may not be a member of the placing workspace, so
--   the flow works the way e-signatures do: a personal, expiring link (token hashed
--   at rest) opens a read-only view of the week and lets them approve it or return
--   it with a note — no account or membership needed for that one decision.
--   The link read/decide helpers are SECURITY DEFINER and tightly scoped: they only
--   ever touch the linked timesheet, and only while it is placed-by-approved and
--   still awaiting the end client.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.ts_approval_links (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,                 -- the placing workspace
  timesheet_id uuid not null references mytrakin.timesheets (id) on delete cascade,
  company_id uuid,                         -- the end-client company this link is for
  token_hash text not null unique,
  created_by uuid,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '45 days',
  used_at timestamptz
);
create index if not exists ts_approval_links_ts_idx on mytrakin.ts_approval_links (timesheet_id);

alter table mytrakin.ts_approval_links enable row level security;
create policy ts_links_internal on mytrakin.ts_approval_links for select to mytrakin_api
  using (is_internal());

-- What the public approval page shows: the week's hours, no rates, and the state.
create or replace function mytrakin.ts_approval_view(p_hash text) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; tn text; weeks json; total numeric;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null then
    return json_build_object('error', 'used');
  end if;
  if link.expires_at < now() then
    return json_build_object('error', 'expired');
  end if;
  select t.*, c.full_name, c.engagement, emp.name as employer
    into ts
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
    left join mytrakin.companies emp on emp.id = c.employer_company_id
   where t.id = link.timesheet_id;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select name into tn from mytrakin.tenants where id = link.tenant_id;
  select coalesce(sum(hours), 0) into total from mytrakin.timesheet_entries where timesheet_id = link.timesheet_id;
  select json_agg(x) into weeks
    from (select coalesce(pr.name, 'Internal / non-billable') as project,
                 json_agg(json_build_object('d', e.work_date, 'h', e.hours) order by e.work_date) as hours
            from mytrakin.timesheet_entries e
            left join mytrakin.placements p on p.id = e.placement_id
            left join mytrakin.projects pr on pr.id = p.project_id
           where e.timesheet_id = link.timesheet_id
           group by 1) x;
  return json_build_object(
    'timesheet_id', ts.id, 'week_start', ts.week_start, 'status', ts.status,
    'consultant', ts.full_name, 'engagement', ts.engagement, 'employer', ts.employer,
    'placed_by', tn, 'note', ts.note, 'rows', coalesce(weeks, '[]'::json), 'total_hours', total,
    'expires_at', link.expires_at);
end $$;
revoke all on function mytrakin.ts_approval_view(text) from public;
grant execute on function mytrakin.ts_approval_view(text) to mytrakin_api;

-- The end client's decision. Borrowed links can't restart a decided week.
create or replace function mytrakin.ts_client_decide(p_hash text, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; v_creator text; v_client text; v_cemail text;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null or link.expires_at < now() then
    return json_build_object('error', case when link.used_at is not null then 'used' else 'expired' end);
  end if;
  select * into ts from mytrakin.timesheets where id = link.timesheet_id for update;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select coalesce((select email from mytrakin.profiles where id = link.created_by), '') into v_creator;
  select coalesce(c.name, '') into v_client from mytrakin.companies c where c.id = link.company_id;
  select coalesce((select p.email from mytrakin.profiles p where p.id = c.user_id), c.email, '')
    into v_cemail
    from mytrakin.consultants c join mytrakin.timesheets t on t.consultant_id = c.id
   where t.id = link.timesheet_id;

  if p_decision = 'approve' then
    update mytrakin.timesheets
       set status = 'approved', end_client_approved = true, decided_at = now(), reject_reason = null
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'approved', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  elsif p_decision = 'return' then
    if p_note is null or length(btrim(p_note)) < 3 then
      return json_build_object('error', 'note_required');
    end if;
    update mytrakin.timesheets
       set status = 'rejected', reject_reason = btrim(p_note), decided_at = now(),
           placed_by_approved = false, end_client_approved = false
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'rejected', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  end if;
  return json_build_object('error', 'invalid_decision');
end $$;
revoke all on function mytrakin.ts_client_decide(text, text, text) from public;
grant execute on function mytrakin.ts_client_decide(text, text, text) to mytrakin_api;

-- Source: migrations/20261021000500_client_timesheet_queue.sql
-- =============================================================================
-- myTrakIn · 20261021 0500 · The end client's in-app timesheet queue
--
--   After the placed-by approval, the week must be visible to the end client's
--   own workspace too — a "waiting for us" list on the Timesheets page, with an
--   approval link they can act on right away (the e-mail flow from 0400 uses the
--   same link table). These SECURITY DEFINER helpers never relax the restrictive
--   tenant isolation: they expose exactly one thing — weeks waiting on our end-
--   client approval — keyed on the companies the caller acts for (their workspace's
--   own company, or the company their membership represents).
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- The companies the caller acts for in this workspace: their membership's company
-- (client_user and vendor reps) plus the workspace's own company.
create or replace function mytrakin.ts_my_companies() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct x), '{}') from (
    select mytrakin.ctx_company() as x where mytrakin.ctx_company() is not null
    union all
    select t.company_id from mytrakin.tenants t
     where t.id = mytrakin.ctx_tenant() and t.company_id is not null) s;
$$;
revoke all on function mytrakin.ts_my_companies() from public;
grant execute on function mytrakin.ts_my_companies() to mytrakin_api;

-- Weeks whose placed-by approval is in and are waiting on us as the end client.
create or replace function mytrakin.ts_client_queue() returns table (
  timesheet_id uuid, week_start date, consultant text, engagement text, employer text,
  placed_by text, note text, weekend_confirmed boolean, submitted_at timestamptz,
  days numeric[], total numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.week_start, c.full_name, c.engagement, emp.name, tn.name, t.note,
         t.weekend_confirmed, t.submitted_at,
         coalesce((select array_agg(coalesce(d.h, 0) order by s.dn)
                     from generate_series(0, 6) s(dn)
                     left join (select (e.work_date - t.week_start) as dn, sum(e.hours) as h
                                  from mytrakin.timesheet_entries e
                                 where e.timesheet_id = t.id group by 1) d using (dn)),
                  '{0,0,0,0,0,0,0}'),
         (select coalesce(sum(hours), 0) from mytrakin.timesheet_entries where timesheet_id = t.id)
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
    left join mytrakin.companies emp on emp.id = c.employer_company_id
    left join mytrakin.tenants tn on tn.id = t.tenant_id
   where t.status = 'submitted' and t.placed_by_approved
     and exists (select 1 from mytrakin.placements p
                  where p.consultant_id = t.consultant_id
                    and p.end_client_company_id = any (mytrakin.ts_my_companies()))
   order by t.week_start desc, c.full_name;
$$;
revoke all on function mytrakin.ts_client_queue() from public;
grant execute on function mytrakin.ts_client_queue() to mytrakin_api;

-- One waiting week's review data for an end-client approver (hours only, no rates).
create or replace function mytrakin.ts_client_view(p_ts uuid) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; tn text; weeks json; total numeric; v_client text;
begin
  select t.*, c.full_name, c.engagement, emp.name as employer
    into ts
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
    left join mytrakin.companies emp on emp.id = c.employer_company_id
   where t.id = p_ts;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  if not exists (select 1 from mytrakin.placements p
                  where p.consultant_id = ts.consultant_id
                    and p.end_client_company_id = any (mytrakin.ts_my_companies())) then
    return json_build_object('error', 'not_ours');
  end if;
  select name into tn from mytrakin.tenants where id = ts.tenant_id;
  select coalesce(sum(hours), 0) into total from mytrakin.timesheet_entries where timesheet_id = p_ts;
  select json_agg(x) into weeks
    from (select coalesce(pr.name, 'Internal / non-billable') as project,
                 json_agg(json_build_object('d', e.work_date, 'h', e.hours) order by e.work_date) as hours
            from mytrakin.timesheet_entries e
            left join mytrakin.placements p on p.id = e.placement_id
            left join mytrakin.projects pr on pr.id = p.project_id
           where e.timesheet_id = p_ts
           group by 1) x;
  return json_build_object(
    'timesheet_id', ts.id, 'tenant_id', ts.tenant_id,
    'week_start', ts.week_start, 'status', ts.status, 'consultant', ts.full_name,
    'engagement', ts.engagement, 'employer', ts.employer, 'placed_by', tn,
    'note', ts.note, 'rows', coalesce(weeks, '[]'::json), 'total_hours', total);
end $$;
revoke all on function mytrakin.ts_client_view(uuid) from public;
grant execute on function mytrakin.ts_client_view(uuid) to mytrakin_api;

-- Create (or refresh) an approval link for a waiting week, from inside the client's
-- own workspace or as its representative. The token itself is passed in (hashed here).
create or replace function mytrakin.ts_client_link(p_ts uuid, p_hash text, p_creator uuid) returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare v json; link uuid;
begin
  v := mytrakin.ts_client_view(p_ts);
  if v is null or v ->> 'error' is not null then
    return v;
  end if;
  insert into mytrakin.ts_approval_links (tenant_id, timesheet_id, token_hash, created_by)
  values ((v ->> 'tenant_id')::uuid, p_ts, p_hash, p_creator) returning id into link;
  return json_build_object('ok', true, 'timesheet_id', p_ts, 'link_id', link);
end $$;
revoke all on function mytrakin.ts_client_link(uuid, text, uuid) from public;
grant execute on function mytrakin.ts_client_link(uuid, text, uuid) to mytrakin_api;

-- The end client's in-app decision — same gates and effects as the link decision.
create or replace function mytrakin.ts_client_decide_ts(p_ts uuid, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; v_client text; v_creator text; v_cemail text; out_name text;
begin
  select t.*, c.full_name, c.engagement into ts
    from mytrakin.timesheets t join mytrakin.consultants c on c.id = t.consultant_id
   where t.id = p_ts;
  if ts.id is not null and ts.status = 'submitted' and ts.placed_by_approved then
    select coalesce(c.name, '') into out_name from mytrakin.companies c
     where c.id = any (mytrakin.ts_my_companies())
       and c.id in (select p.end_client_company_id from mytrakin.placements p
                      join mytrakin.timesheet_entries e on e.placement_id = p.id
                     where e.timesheet_id = p_ts)
     limit 1;
    select coalesce((select p2.email from mytrakin.ts_approval_links l
                       join mytrakin.profiles p2 on p2.id = l.created_by
                      where l.timesheet_id = p_ts and l.used_at is null
                      order by l.created_at desc limit 1), '') into v_creator;
    select coalesce((select p2.email from mytrakin.profiles p2 where p2.id = c.user_id), c.email, '')
      into v_cemail from mytrakin.consultants c where c.id = ts.consultant_id;
  end if;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  if out_name is null then
    return json_build_object('error', 'not_ours');
  end if;

  if p_decision = 'approve' then
    update mytrakin.timesheets
       set status = 'approved', end_client_approved = true, decided_at = now(), reject_reason = null
     where id = p_ts;
    update mytrakin.ts_approval_links set used_at = now() where timesheet_id = p_ts and used_at is null;
    return json_build_object('ok', true, 'status', 'approved', 'week_start', ts.week_start,
                             'tenant_id', ts.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', out_name, 'consultant_email', v_cemail);
  elsif p_decision = 'return' then
    if p_note is null or length(btrim(p_note)) < 3 then
      return json_build_object('error', 'note_required');
    end if;
    update mytrakin.timesheets
       set status = 'rejected', reject_reason = btrim(p_note), decided_at = now(),
           placed_by_approved = false, end_client_approved = false
     where id = p_ts;
    update mytrakin.ts_approval_links set used_at = now() where timesheet_id = p_ts and used_at is null;
    return json_build_object('ok', true, 'status', 'rejected', 'week_start', ts.week_start,
                             'tenant_id', ts.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', out_name, 'consultant_email', v_cemail);
  end if;
  return json_build_object('error', 'invalid_decision');
end $$;
revoke all on function mytrakin.ts_client_decide_ts(uuid, text, text) from public;
grant execute on function mytrakin.ts_client_decide_ts(uuid, text, text) to mytrakin_api;

-- The links table was created after the original security grants, so grant it now.
grant select, insert, update, delete on mytrakin.ts_approval_links to mytrakin_api;

-- Source: migrations/20261022000100_placement_end_client_backfill.sql
-- Backfill placements.end_client_company_id from the project's client.
-- Rows created before the end-client chain fix (placement on a project another
-- company assigned to us) never got the field set; the project's client_company_id
-- is the original company that initiated the chain (the end client).
update mytrakin.placements p
   set end_client_company_id = pr.client_company_id
  from mytrakin.projects pr
 where pr.id = p.project_id
   and p.end_client_company_id is null
   and pr.client_company_id is not null;

-- Same through one assignment hop (our local project copy keeps the chain in
-- source_project_id when the copy itself still has no client).
update mytrakin.placements p
   set end_client_company_id = src.client_company_id
  from mytrakin.placements p0
   join mytrakin.projects pr on pr.id = p0.project_id
   join mytrakin.projects src on src.id = pr.source_project_id
 where p0.id = p.id
   and p.end_client_company_id is null
   and src.client_company_id is not null;

-- Source: migrations/20261022000200_ts_client_recipients.sql
-- =============================================================================
-- myTrakIn · 20261022000200 · Cross-tenant end-client approver discovery
--
--   _end_client_recipients (timesheets API) tried to find "who can approve for
--   the end client" with a plain query over mytrakin.tenants + memberships +
--   profiles. Under the API session RLS only exposes the caller's OWN tenant
--   (tenants_read / profiles_read), so the end client's workspace was always
--   invisible: every week finalised on the placing company's approval alone —
--   status 'approved', end_client_approved false, no approval link e-mailed —
--   even when the end client's own workspace had active members.
--
--   This SECURITY DEFINER helper exposes the minimum: the e-mail addresses of
--   active members of the end-client companies' OWN workspaces. Nothing else.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.ts_client_recipients(p_companies uuid[])
returns table (company_id uuid, email text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.company_id, p.email
    from mytrakin.tenants t
    join mytrakin.memberships m on m.tenant_id = t.id and m.status = 'active' and m.user_id is not null
    join mytrakin.profiles p on p.id = m.user_id
   where t.company_id is not null and t.company_id = any (p_companies) and p.email is not null
$$;

revoke all on function mytrakin.ts_client_recipients(uuid[]) from public;
grant execute on function mytrakin.ts_client_recipients(uuid[]) to mytrakin_api;

-- Source: migrations/20261022000300_timesheet_resubmit_check_fix.sql
-- =============================================================================
-- myTrakIn · 20261022000300 · Fix the rejected-timesheet resubmit RLS check
--
--   When a consultant's timesheet week is returned (rejected), they must be able
--   to edit and resubmit it (PUT /timesheets/mine). The consultant update policy's
--   USING clause accepts rows in 'draft'/'rejected', but its deployed WITH CHECK
--   lost the 'rejected' status (draft + submitted only) — so touching a rejected
--   row violated the policy and the API surfaced it as 403
--   "You don't have permission to do that" (SQLSTATE 42501).
--   Recreate the policy with the statuses aligned on both sides.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists timesheets_consultant_update on mytrakin.timesheets;
create policy timesheets_consultant_update on mytrakin.timesheets for update to mytrakin_api
  using (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
           and status in ('draft', 'rejected'))
  with check (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
           and status in ('draft', 'rejected', 'submitted'));

-- Source: migrations/20261022000400_ts_client_decide_fix.sql
-- =============================================================================
-- myTrakIn · 20261022000400 · Fix ts_client_decide crash (ts.full_name)
--
--   ts_client_decide (the e-mailed approval link's decision, used by
--   /public/ts-approvals/{token}/approve and /return) selected the timesheet row
--   only — `select * into ts from mytrakin.timesheets ...` — but then returned
--   ts.full_name in the decision payload. plpgsql raises
--   'record "ts" has no field "full_name"', so approving from the client's link
--   (and the placed-by's in-app Review & approve for the same week) dies with a
--   500. Recreate the function joining the consultant with explicit aliases;
--   behaviour and gates unchanged.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.ts_client_decide(p_hash text, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; v_creator text; v_client text; v_cemail text;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null or link.expires_at < now() then
    return json_build_object('error', case when link.used_at is not null then 'used' else 'expired' end);
  end if;
  select t.id, t.status, t.placed_by_approved, t.end_client_approved, t.week_start, t.consultant_id,
         c.full_name as full_name, c.engagement as engagement
    into ts
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
   where t.id = link.timesheet_id
     for update of t;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select coalesce((select email from mytrakin.profiles where id = link.created_by), '') into v_creator;
  select coalesce(c.name, '') into v_client from mytrakin.companies c where c.id = link.company_id;
  select coalesce((select p.email from mytrakin.profiles p where p.id = c.user_id), c.email, '')
    into v_cemail
    from mytrakin.consultants c
   where c.id = ts.consultant_id;

  if p_decision = 'approve' then
    update mytrakin.timesheets
       set status = 'approved', end_client_approved = true, decided_at = now(), reject_reason = null
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'approved', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  elsif p_decision = 'return' then
    if p_note is null or length(btrim(p_note)) < 3 then
      return json_build_object('error', 'note_required');
    end if;
    update mytrakin.timesheets
       set status = 'rejected', reject_reason = btrim(p_note), decided_at = now(),
           placed_by_approved = false, end_client_approved = false
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'rejected', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  end if;
  return json_build_object('error', 'invalid_decision');
end $$;
revoke all on function mytrakin.ts_client_decide(text, text, text) from public;
grant execute on function mytrakin.ts_client_decide(text, text, text) to mytrakin_api;

-- Source: migrations/20261022000500_ts_links_insert_policy.sql
-- =============================================================================
-- myTrakIn · 20261022000500 · ts_approval_links staff INSERT policy
--
--   After the placed-by approval the API e-mails the end client's approvers and
--   records the link (timesheets._send_client_approval inserts directly). That
--   runs in the placing workspace's staff session — but 20261021000400 created
--   only a SELECT policy on mytrakin.ts_approval_links, so the insert violated
--   RLS and POST /timesheets/{id}/approve failed with the mapped 403
--   "You don't have permission to do that" (SQLSTATE 42501).
--   Decisions themselves stay definer-scoped; only staff can create links.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists ts_links_staff_insert on mytrakin.ts_approval_links;
create policy ts_links_staff_insert on mytrakin.ts_approval_links for insert to mytrakin_api
  with check (mytrakin.can(VARIADIC array['approver', 'account_manager', 'hr', 'finance']));

-- Source: migrations/20261022000600_client_payables_view.sql
-- =============================================================================
-- myTrakIn · 20261022000600 · The end client sees what it is being invoiced
--
--   A client invoice the placing company (B) issues to its end client (A) lives
--   only in B's workspace (RULE-01). A's workspace therefore showed nothing in
--   its AP / payment-flow views. These SECURITY DEFINER helpers expose exactly
--   the rows where A is the billed company (i.company_id in the companies the
--   caller acts for) from OTHER workspaces — money A is party to:
--     * client_payables()        — AP-list shaped rows for the Invoices page
--     * client_payable_flow(p_open) — payment-flow shaped rows (what A owes B)
--   Statuses are recomputed inline (the invoice_balances view is security_invoker
--   and its own RLS would hide the placing workspace's rows here).
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.client_payables()
returns table (
  id uuid, number text, tenant_id uuid, placed_by text,
  consultant text, project text, sow text,
  period_start date, period_end date, hours numeric, amount numeric,
  paid numeric, balance numeric, due_on date, terms text, issued_on date,
  status text, live_status text, engagement text, is_client_payable boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select i.id, i.number, i.tenant_id, tn.name,
         c.full_name, pr.name, s.code,
         i.period_start, i.period_end, i.hours, i.amount,
         coalesce(pm.paid, 0), i.amount - coalesce(pm.paid, 0), i.due_on, i.terms, i.issued_on,
         i.status,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.status = 'void'                                       then 'void'
           when i.status = 'exception'                                  then 'exception'
           when i.status = 'scheduled'                                  then 'scheduled'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status = 'sent'                                       then 'open'
           else i.status
         end,
         c.engagement,
         true
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    left join mytrakin.sows s on s.id = i.sow_id
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
   order by i.period_start desc, c.full_name
$$;

create or replace function mytrakin.client_payable_flow(p_open boolean default true)
returns table (
  flow_key text, consultant text, project text,
  period_start date, period_end date, hours numeric, engagement text,
  payee text, ap_id uuid, ap_number text, ap_amount numeric, ap_due date,
  ap_status text, ap_balance numeric, is_client_flow boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (i.tenant_id::text || ':' || i.id::text), c.full_name, pr.name,
         i.period_start, i.period_end, i.hours, c.engagement,
         tn.name, i.id, i.number, i.amount, i.due_on,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status = 'draft'                                      then 'open'
           else i.status
         end,
         i.amount - coalesce(pm.paid, 0), true
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and (not coalesce(p_open, true) or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;

revoke all on function mytrakin.client_payables(), mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.client_payables(), mytrakin.client_payable_flow(boolean) to mytrakin_api;

-- Source: migrations/20261022000700_chain_of.sql
-- =============================================================================
-- myTrakIn · 20261022000700 · The payment-flow chain per logged-in company
--
--   A project assigned down the vendor chain keeps its source in
--   projects.source_project_id. Walking that chain (in other tenants, hidden by
--   RLS from a staff session) gives the end client (the root project's client)
--   and the assignment path "who placed us" ending with the caller's own
--   company. SECURITY DEFINER: every other layer's amounts stay private — this
--   only publishes company names.
--
--   Example: A(Profin) → B(Preview IT) → C(TCS) → D(South Cloud) → E(Twitter)
--     chain_of(D's project) = ('Profin AI Solutions', 'TCS → South Cloud ...')
--     chain_of(B's root)    = ('Profin AI Solutions', 'Preview IT')
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.chain_of(p_project uuid)
returns table (end_client text, placed_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with recursive w as (
       select pr.id, pr.prime_company_id, pr.source_project_id, pr.client_company_id, pr.tenant_id, 0 as depth
         from mytrakin.projects pr
        where pr.id = p_project
       union all
       select s.id, s.prime_company_id, s.source_project_id, s.client_company_id, s.tenant_id, w.depth + 1
         from mytrakin.projects s
         join w on s.id = w.source_project_id),
       root as (select tenant_id, client_company_id from w where depth = 0),
       own as (select coalesce(t.company_id, null::uuid) as cid from mytrakin.tenants t where t.id = (select root.tenant_id from root)),
       hops as (
         select x.depth, mytrakin.company_public_name(x.prime_company_id) as n
           from w x
          where x.prime_company_id is not null
            and x.source_project_id is not null
            and not exists (select 1 from mytrakin.companies co
                             where co.id = x.prime_company_id
                               and co.tenant_id = (select root.tenant_id from root))),
       dedup as (
          select n, lag(n) over (order by depth desc) as prev
            from hops),
       assigners as (
          select string_agg(n, ' → ') as chain
            from dedup
           where n is not null and n <> coalesce(prev, '__none__')),
       ownname as (select coalesce(mytrakin.company_public_name((select own.cid from own)), (select t.name from mytrakin.tenants t where t.id = (select root.tenant_id from root)), '') as own_name)
  select
    coalesce((select mytrakin.company_public_name(r.client_company_id) from w r where r.source_project_id is null limit 1), '') as end_client,
    coalesce(
      case
        when (select a.chain from assigners a) = '' then (select o.own_name from ownname o)
        when (select a.chain from assigners a) = (select o.own_name from ownname o) then (select o.own_name from ownname o)
        else (select a.chain from assigners a) || ' → ' || (select o.own_name from ownname o)
      end, (select o.own_name from ownname o)) as placed_by
$$;

-- Re-issue the payable flow with the chain columns for the end client's mirror.
drop function if exists mytrakin.client_payable_flow(boolean);
create or replace function mytrakin.client_payable_flow(p_open boolean default true)
returns table (
  flow_key text, consultant text, project text,
  period_start date, period_end date, hours numeric, engagement text,
  payee text, ap_id uuid, ap_number text, ap_amount numeric, ap_due date,
  ap_status text, ap_balance numeric, is_client_flow boolean,
  end_client text, placed_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (i.tenant_id::text || ':' || i.id::text), c.full_name, pr.name,
         i.period_start, i.period_end, i.hours, c.engagement,
         tn.name, i.id, i.number, i.amount, i.due_on,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status = 'draft'                                      then 'open'
           else i.status
         end,
         i.amount - coalesce(pm.paid, 0), true,
         ch.end_client, ch.placed_by
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    cross join lateral mytrakin.chain_of(p.project_id) ch
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and (not coalesce(p_open, true) or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;

revoke all on function mytrakin.chain_of(uuid), mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.chain_of(uuid), mytrakin.client_payable_flow(boolean) to mytrakin_api;

-- Source: migrations/20261022000800_flow_tiles_polish.sql
-- =============================================================================
-- myTrakIn · 20261022000800 · Payment-flow tile polish
--   The end client's mirrored flow card: a 'sent' invoice reads as 'open'
--   (AP-style display), and self-billed placements never appear.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop function if exists mytrakin.client_payable_flow(boolean);
create or replace function mytrakin.client_payable_flow(p_open boolean default true)
returns table (
  flow_key text, consultant text, project text,
  period_start date, period_end date, hours numeric, engagement text,
  payee text, ap_id uuid, ap_number text, ap_amount numeric, ap_due date,
  ap_status text, ap_balance numeric, is_client_flow boolean,
  end_client text, placed_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (i.tenant_id::text || ':' || i.id::text), c.full_name, pr.name,
         i.period_start, i.period_end, i.hours, c.engagement,
         tn.name, i.id, i.number, i.amount, i.due_on,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status in ('draft', 'sent')                           then 'open'
           else i.status
         end,
         i.amount - coalesce(pm.paid, 0), true,
         ch.end_client, ch.placed_by
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    cross join lateral mytrakin.chain_of(p.project_id) ch
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and (not p_open or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;
revoke all on function mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.client_payable_flow(boolean) to mytrakin_api;

-- Source: migrations/20261022000900_restricted_company_docs.sql
-- =============================================================================
-- myTrakIn · 20261022000900 · Restricted company compliance documents
--
--   US companies may create with manually typed W-9 details and upload the
--   document afterwards; the platform verifies that W-9 before activation and
--   can additionally attach government-issued certificates (tax certificate,
--   certificate of good standing, and so on). Those files carry confidential
--   taxpayer identities: they are visible only to the platform team and that
--   company's super admin (owners), never to ordinary members or other tenants.
--
--   documents.restricted marks them. can_see_restricted() is the single gate:
--   platform role (including 'system', which the platform uses while acting
--   inside a tenant) or the owning company's super_admin / owner.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.documents add column if not exists restricted boolean not null default false;

create or replace function mytrakin.can_see_restricted(p_owner_type text, p_owner_id uuid)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select mytrakin.ctx_role() in ('platform_admin', 'system')
      or (p_owner_type = 'company' and mytrakin.company_role(p_owner_id) in ('super_admin', 'owner'))
$$;

-- Read: restricted rows only through the gate; everything keeps today's visibility.
drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
    mytrakin.can_see_restricted(owner_type, owner_id)
    or (restricted is false and (
      is_internal()
      or (mytrakin.ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = mytrakin.ctx_consultant()) or owner_type = 'policy'))
      or (mytrakin.ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = mytrakin.ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
            where s.id = owner_id and s.created_by = mytrakin.ctx_user()))))));

-- Upload: restricted rows only by the platform or that company's super admin / owner;
-- unrestricted rows keep today's rules.
drop policy if exists documents_upload on mytrakin.documents;
create policy documents_upload on mytrakin.documents for insert to mytrakin_api
  with check ((
    mytrakin.can_see_restricted(owner_type, owner_id)
    or (restricted is false and (
      is_internal()
      or (mytrakin.ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = mytrakin.ctx_consultant()))
      or (mytrakin.ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = mytrakin.ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) in ('super_admin', 'owner', 'admin'))
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
            where s.id = owner_id and s.created_by = mytrakin.ctx_user()))
      or (mytrakin.ctx_role() = 'public' and owner_type = 'registration')))));

-- Source: migrations/20261022001000_consultant_by_code.sql
-- =============================================================================
-- myTrakIn · 20261022001000 · Resolve a consultant's ID in imports
--
--   Imports tag people by their system user code (U000123) — but RLS hides
--   user_codes from the importing session, so the CSV importer would create
--   duplicates instead of matching. This SECURITY DEFINER helper resolves the
--   code inside the caller's own tenant only.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.consultant_by_code(p_code text)
returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select c.id from mytrakin.consultants c
   join mytrakin.user_codes uc on uc.user_id = c.user_id
  where upper(uc.code) = upper(p_code)
    and c.tenant_id = mytrakin.ctx_tenant()
  limit 1
$$;

revoke all on function mytrakin.consultant_by_code(text) from public;
grant execute on function mytrakin.consultant_by_code(text) to mytrakin_api;

-- Source: migrations/20261022001100_project_peer_companies.sql
-- =============================================================================
-- myTrakIn · 20261022001100 · Consistent counterparties for the New-project form
--
--   The New project form's Client / Prime vendor options list the companies we
--   have an MSA in force with. That used a plain query over agreements, whose
--   row-level visibility differs by role — so different authorised users saw
--   different options (the end client missing for some). These are only company
--   names, nothing sensitive: publish them to every workspace member through a
--   SECURITY DEFINER helper so the form is the same for everyone.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.project_peer_companies()
returns table (id uuid, name text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select x.id, mytrakin.company_public_name(x.id)
    from (select a.company_id as id from mytrakin.agreements a
            where a.tenant_id = mytrakin.ctx_tenant() and a.status in ('active', 'accepted')
              and a.kind = any (array['msa', 'subcontract'])
          union
          select mytrakin.agreement_peer_company(s.id) from mytrakin.shared_agreements() s
           where s.status in ('active', 'accepted') and s.kind = any (array['msa', 'subcontract'])) x
   where x.id is not null
     and not x.id = any (mytrakin.my_company_ids())
     and mytrakin.company_public_name(x.id) is not null
$$;

revoke all on function mytrakin.project_peer_companies() from public;
grant execute on function mytrakin.project_peer_companies() to mytrakin_api;

-- Source: migrations/20261026000100_rejections.sql
-- =============================================================================
-- myTrakIn · 20261026 0100 · Rejections you can recover from (T011303-1084, 1086, 1087)
--
--   The platform's "reject" used to close the company (status 'closed'). Closed
--   tenants are refused at session start, yet my_tenants() still listed them, so the
--   web app kept the rejected company selected and every call answered "You don't
--   have access to this company yet". The owner could not see why, fix anything, or
--   create another company.
--
--   Now:
--     rejected   the platform turned it down; the owner can open its profile (like a
--                company waiting for activation), read the reason, fix the details
--                and resubmit it (back to 'onboarding').
--     closed     really closed: not listed anywhere the user can pick it.
--
--   my_businesses() also returns the tenant status, the platform's note and the
--   company logo, so My companies can show "Rejected" with the reason and the logo.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.tenants drop constraint if exists tenants_status_check;
alter table mytrakin.tenants add constraint tenants_status_check
  check (status in ('onboarding', 'active', 'suspended', 'rejected', 'closed'));

-- Companies the platform rejected before this change (closed with a note, never activated).
update mytrakin.tenants set status = 'rejected'
 where status = 'closed' and company_id is not null and activated_at is null and decision_note is not null;

create or replace function mytrakin.my_tenants(p_user uuid)
returns table (tenant_id uuid, tenant_name text, role text, tenant_status text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, m.role, t.status
    from mytrakin.memberships m join mytrakin.tenants t on t.id = m.tenant_id
   where m.user_id = p_user and m.status = 'active' and t.status <> 'closed'
   order by t.name
$$;

-- Same rows as 20261016000900 plus tenant_status / decision_note / logo_path, closed companies left out.
drop function if exists mytrakin.my_businesses(uuid);
create or replace function mytrakin.my_businesses(p_user uuid)
returns table (tenant_id uuid, tenant_name text, company_id uuid, business_code text,
               company_name text, kind text, kinds text[], company_role text, tenant_role text,
               status text, session_id uuid, tenant_status text, decision_note text, logo_path text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         cm.company_role,
         (select m.role from mytrakin.memberships m
           where m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
           order by m.created_at limit 1),
         c.status, null::uuid, t.status, t.decision_note, c.logo_path
    from mytrakin.company_members cm
    join mytrakin.companies c on c.id = cm.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where cm.user_id = p_user and cm.status = 'active' and c.status <> 'inactive' and t.status <> 'closed'
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         null::text, m.role, c.status, null::uuid, t.status, t.decision_note, c.logo_path
    from mytrakin.memberships m
    join mytrakin.companies c on c.id = m.company_id
    join mytrakin.tenants t on t.id = c.tenant_id
   where m.user_id = p_user and m.status = 'active' and c.status <> 'inactive' and t.status <> 'closed'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
  union
  select t.id, t.name, c.id, c.business_code, c.name as company_name, c.kind, c.kinds,
         null::text, m.role, c.status, null::uuid, t.status, t.decision_note, c.logo_path
    from mytrakin.consultants k
    join auth.users u on u.id = p_user
    join mytrakin.companies c on c.id = k.employer_company_id
    join mytrakin.tenants t on t.id = c.tenant_id
    join mytrakin.memberships m on m.user_id = p_user and m.tenant_id = t.id and m.status = 'active'
   where k.email = u.email and c.status <> 'inactive' and t.status <> 'closed'
     and not exists (select 1 from mytrakin.company_members cm
                      where cm.company_id = c.id and cm.user_id = p_user and cm.status = 'active')
     and not exists (select 1 from mytrakin.memberships m2
                      where m2.user_id = p_user and m2.company_id = c.id and m2.status = 'active')
  union
  select t.id, t.name, null::uuid, null::text, t.name, 'draft'::text, array['draft']::text[],
         null::text, m.role, 'draft'::text,
         (select s.id from mytrakin.onboarding_sessions s
           where s.tenant_id = t.id and s.created_by = p_user and s.status <> 'complete'
           order by s.created_at desc limit 1),
         t.status, null::text, null::text
    from mytrakin.tenants t
    join mytrakin.memberships m on m.id = t.owner_membership_id
   where m.user_id = p_user and m.status = 'active'
     and t.status = 'onboarding' and t.company_id is null
   order by company_name
$$;
revoke all on function mytrakin.my_businesses(uuid) from public;
grant execute on function mytrakin.my_businesses(uuid) to mytrakin_api;

-- T011303-1086: a SOW the other company turned down can be corrected and sent again
-- (the web app's "Send again"); the previous answer is cleared for the new round.
create or replace function mytrakin.submit_sow_for_approval(p_sow uuid) returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; peer uuid;
begin
  select * into s from mytrakin.sows where id = p_sow for update;
  if not found then raise exception 'SOW not found' using errcode = 'MT404'; end if;
  if s.tenant_id is distinct from mytrakin.ctx_tenant() then
    raise exception 'This SOW belongs to another workspace' using errcode = 'MT403';
  end if;
  if s.status not in ('draft', 'rejected') then
    raise exception 'This SOW has already been sent' using errcode = 'MT409';
  end if;
  peer := mytrakin.agreement_peer_company(s.agreement_id);
  if peer is null then
    raise exception 'There is no other company on this agreement to send it to' using errcode = 'MT422';
  end if;
  update mytrakin.sows set status = 'pending', sent_on = now(), decided_on = null, decided_by = null, decision_note = null
   where id = p_sow;
end $$;

commit;
