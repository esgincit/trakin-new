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
