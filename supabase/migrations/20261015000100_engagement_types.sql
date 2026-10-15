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
