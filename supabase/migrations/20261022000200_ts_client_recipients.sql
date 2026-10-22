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
