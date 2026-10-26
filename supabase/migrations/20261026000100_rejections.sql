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
