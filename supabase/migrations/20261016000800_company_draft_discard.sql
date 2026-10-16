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
