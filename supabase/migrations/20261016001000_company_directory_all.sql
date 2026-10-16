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
