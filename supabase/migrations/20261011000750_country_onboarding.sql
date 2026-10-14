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
