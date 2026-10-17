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
