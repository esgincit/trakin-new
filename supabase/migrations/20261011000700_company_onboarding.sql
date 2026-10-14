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
