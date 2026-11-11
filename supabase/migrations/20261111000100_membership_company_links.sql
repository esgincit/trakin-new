-- =============================================================================
-- myTrakIn · 20261111 0100 · A user's company / consultant link must belong to the workspace
--
--   memberships.company_id (vendor_admin / client_user: the company the person
--   represents) and memberships.consultant_id (consultant: their own record) become
--   app.company_id / app.consultant_id for every request. Several cross-workspace
--   helpers read them, so the link has to be one the workspace really has:
--
--     company_id     a company record of this workspace (companies.tenant_id = the
--                    membership's tenant), or a company of another workspace that this
--                    workspace has an MSA / subcontract with that the OTHER side confirmed:
--                    either we sent it and a person of that company (its company member,
--                    or staff of the workspace that is that company) accepted it, or that
--                    company's own workspace sent it to our company and it was accepted.
--                    Drafts, pending, rejected, imported or manually 'active' agreements,
--                    NDAs and SOWs (which a sender can record on its own) do not count.
--     consultant_id  a consultant record of this workspace. A vendor company may invite
--                    its 1099 contractor this way; the contractor's consultant role only
--                    reaches their own timesheets, contracts and documents there.
--
--   1. membership_link_ok() states the rule; a trigger enforces it on every insert
--      and on every change of the link, so no code path can store a bad link.
--   2. Existing links that fail the rule are removed (see the clean-up block).
--   3. Defence in depth: the cross-workspace helpers trust app.company_id only for a
--      company record of the caller's own workspace, and the workspace's own company
--      only for its staff (not for vendor/client representatives or consultants).
--   4. link_consultant_user only touches the consultant record of the same workspace.
--   5. End-client timesheet helpers check the week's own entries (not any placement of
--      the consultant) and only for approver roles; recording a payment on another
--      workspace's invoice needs finance (or admin); signing admins of a company are
--      listed only to workspaces that work with it.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- 1. The rule ------------------------------------------------------------------------
create or replace function mytrakin.membership_link_ok(p_tenant uuid, p_company uuid, p_consultant uuid)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (p_company is null
          or exists (select 1 from mytrakin.companies c where c.id = p_company and c.tenant_id = p_tenant)
          or exists (
               select 1
                 from mytrakin.agreements a
                 join mytrakin.tenants at on at.id = a.tenant_id
                 join mytrakin.tenants mine on mine.id = p_tenant
                where a.kind in ('msa', 'subcontract') and a.status in ('accepted', 'active')
                  and a.decided_by is not null
                  and (
                    -- We sent it: someone of THAT company (its member, or staff of the
                    -- workspace that is that company) accepted it.
                    (a.tenant_id = p_tenant and a.company_id = p_company
                     and (exists (select 1 from mytrakin.company_members cm
                                   where cm.company_id = p_company and cm.user_id = a.decided_by
                                     and cm.status = 'active')
                          or exists (select 1 from mytrakin.memberships dm
                                       join mytrakin.tenants dt on dt.id = dm.tenant_id
                                      where dt.company_id = p_company and dm.user_id = a.decided_by
                                        and dm.status = 'active'
                                        and dm.role in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr'))))
                    -- That company's own workspace sent it to our company and we accepted.
                 or (a.tenant_id <> p_tenant and at.company_id = p_company
                     and coalesce(a.initiator_company_id, p_company) = p_company
                     and a.company_id = mine.company_id))))
     and (p_consultant is null
          or exists (select 1 from mytrakin.consultants k where k.id = p_consultant and k.tenant_id = p_tenant))
$$;
revoke all on function mytrakin.membership_link_ok(uuid, uuid, uuid) from public;
grant execute on function mytrakin.membership_link_ok(uuid, uuid, uuid) to mytrakin_api;

-- 2. Clean up links stored before the rule. Representatives / consultants whose link
--    fails lose it and are deactivated (an admin re-invites them with a valid link);
--    staff keep their access and only lose the stray company link. Nothing is deleted
--    (RULE-03) and the audit trigger records each change.
do $$
declare n_ext int; n_staff int; n_cons int;
begin
  update mytrakin.memberships m set company_id = null, status = 'deactivated'
   where m.role in ('vendor_admin', 'client_user') and m.company_id is not null
     and not mytrakin.membership_link_ok(m.tenant_id, m.company_id, null);
  get diagnostics n_ext = row_count;
  update mytrakin.memberships m set company_id = null
   where m.company_id is not null
     and not mytrakin.membership_link_ok(m.tenant_id, m.company_id, null);
  get diagnostics n_staff = row_count;
  update mytrakin.memberships m set consultant_id = null,
         status = case when m.role = 'consultant' then 'deactivated' else m.status end
   where m.consultant_id is not null
     and not mytrakin.membership_link_ok(m.tenant_id, null, m.consultant_id);
  get diagnostics n_cons = row_count;
  raise notice 'membership links removed: % representatives deactivated, % staff company links cleared, % consultant links cleared',
    n_ext, n_staff, n_cons;
end $$;

-- 3. The guard -----------------------------------------------------------------------
create or replace function mytrakin.memberships_link_guard() returns trigger
language plpgsql set search_path = mytrakin, public, extensions as $$
begin
  if (tg_op = 'INSERT'
      or new.company_id is distinct from old.company_id
      or new.consultant_id is distinct from old.consultant_id
      or new.tenant_id is distinct from old.tenant_id)
     and not mytrakin.membership_link_ok(new.tenant_id, new.company_id, new.consultant_id) then
    raise exception 'A user can only be linked to a company or consultant this workspace works with'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;
revoke all on function mytrakin.memberships_link_guard() from public;

drop trigger if exists memberships_link_guard on mytrakin.memberships;
create trigger memberships_link_guard
  before insert or update of company_id, consultant_id, tenant_id on mytrakin.memberships
  for each row execute function mytrakin.memberships_link_guard();

-- 4. Consultant login link stays inside the workspace --------------------------------
create or replace function mytrakin.link_consultant_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if new.consultant_id is not null and new.user_id is not null then
    update consultants set user_id = new.user_id
     where id = new.consultant_id and tenant_id = new.tenant_id and user_id is distinct from new.user_id;
  end if;
  return new;
end
$$;
revoke all on function mytrakin.link_consultant_user() from public;

-- 5. Companies the caller acts for, across workspaces ---------------------------------
-- The representative's company counts only when it is a record of the caller's own
-- workspace; the workspace's own company only for its staff.
create or replace function mytrakin.my_company_ids() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct s.cid) filter (where s.cid is not null), '{}'::uuid[])
    from (
      select t.company_id as cid from mytrakin.tenants t
       where t.id = mytrakin.ctx_tenant() and mytrakin.is_internal()
      union all
      select c.id from mytrakin.companies c
       where c.id = mytrakin.ctx_company() and c.tenant_id = mytrakin.ctx_tenant()
      union all
      select cm.company_id from mytrakin.company_members cm
       where cm.user_id = mytrakin.ctx_user() and cm.status = 'active'
    ) s
$$;

create or replace function mytrakin.ts_my_companies() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct x), '{}') from (
    select c.id as x from mytrakin.companies c
     where c.id = mytrakin.ctx_company() and c.tenant_id = mytrakin.ctx_tenant()
    union all
    select t.company_id from mytrakin.tenants t
     where t.id = mytrakin.ctx_tenant() and t.company_id is not null and mytrakin.is_internal()) s;
$$;

-- Who may act as the end client on a timesheet: approver roles and client representatives.
create or replace function mytrakin.ts_client_role_ok() returns boolean
language sql stable as $$
  select mytrakin.ctx_role() in ('tenant_admin', 'approver', 'account_manager', 'hr', 'finance', 'client_user', 'system')
$$;
grant execute on function mytrakin.ts_client_role_ok() to mytrakin_api;

-- 6. End-client timesheet helpers: the week's own entries decide ------------------------
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
     and mytrakin.ts_client_role_ok()
     and exists (select 1 from mytrakin.timesheet_entries e
                   join mytrakin.placements p on p.id = e.placement_id
                  where e.timesheet_id = t.id
                    and p.end_client_company_id = any (mytrakin.ts_my_companies()))
   order by t.week_start desc, c.full_name;
$$;

create or replace function mytrakin.ts_client_view(p_ts uuid) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; tn text; weeks json; total numeric;
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
  if not mytrakin.ts_client_role_ok()
     or not exists (select 1 from mytrakin.timesheet_entries e
                      join mytrakin.placements p on p.id = e.placement_id
                     where e.timesheet_id = p_ts
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

create or replace function mytrakin.ts_client_decide_ts(p_ts uuid, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; v_creator text; v_cemail text; out_name text;
begin
  select t.*, c.full_name, c.engagement into ts
    from mytrakin.timesheets t join mytrakin.consultants c on c.id = t.consultant_id
   where t.id = p_ts;
  if ts.id is not null and ts.status = 'submitted' and ts.placed_by_approved and mytrakin.ts_client_role_ok() then
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

-- 7. Recording a payment on another workspace's invoice: finance (or admin) only ------
create or replace function mytrakin.client_record_payment(
    p_invoice uuid, p_amount numeric, p_paid_on date, p_method text,
    p_reference text, p_user uuid) returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  inv record;
  pay_id uuid;
begin
  if mytrakin.ctx_role() not in ('finance', 'tenant_admin') then
    return json_build_object('error', 'forbidden');
  end if;
  select i.id, i.number, i.tenant_id, i.direction, i.status, i.company_id,
         i.amount - coalesce(pm.paid, 0) - coalesce(cn.credited, 0) as open_balance
    into inv
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join (select invoice_id, sum(amount) as credited from mytrakin.credit_notes
                group by invoice_id) cn on cn.invoice_id = i.id
   where i.id = p_invoice;

  if inv.id is null or inv.direction <> 'ar' or inv.status = 'void' then
    return json_build_object('error', 'not_found');
  end if;
  if inv.tenant_id = mytrakin.ctx_tenant() or not (inv.company_id = any (mytrakin.ts_my_companies())) then
    return json_build_object('error', 'not_ours');
  end if;
  if p_paid_on is null or p_paid_on > current_date then
    return json_build_object('error', 'future_date');
  end if;
  if p_amount is null or p_amount <= 0 then
    return json_build_object('error', 'invalid_amount');
  end if;
  if p_amount > inv.open_balance + 0.005 then
    return json_build_object('error', 'over_balance', 'balance', inv.open_balance);
  end if;
  if coalesce(p_method, '') not in ('ACH', 'Wire', 'Check', 'Card', 'Other') then
    return json_build_object('error', 'invalid_method');
  end if;

  insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference, status, created_by)
  values (inv.tenant_id, p_invoice, p_amount, p_paid_on, p_method, nullif(btrim(coalesce(p_reference, '')), ''),
          'completed', p_user)
  returning id into pay_id;

  return json_build_object('ok', true, 'payment_id', pay_id, 'invoice_id', p_invoice,
                           'tenant_id', inv.tenant_id, 'number', inv.number,
                           'amount', p_amount, 'balance', inv.open_balance - p_amount);
end $$;

-- 8. Signing admins of a company: only for a workspace that works with it -------------
-- A workspace works with a company when it is one of its own records, a company the
-- caller acts for, or a company with a confirmed MSA / subcontract with this workspace
-- (membership_link_ok). Signer rows of envelopes are typed by the sender and prove
-- nothing, so they do not count. Before that,
-- the sender uses the company's public contact address (company_counterparty()).
-- Representatives are listed only from the company's own workspace.
create or replace function mytrakin.company_signing_admins(p_company_id uuid)
returns table (user_id uuid, name text, email text, company_role text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with related as (
    select (exists (select 1 from mytrakin.companies c where c.id = p_company_id and c.tenant_id = mytrakin.ctx_tenant())
         or p_company_id = any (mytrakin.my_company_ids())
         or mytrakin.membership_link_ok(mytrakin.ctx_tenant(), p_company_id, null)) as ok
  ),
  admins as (
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
      join mytrakin.companies co on co.id = m.company_id and co.tenant_id = m.tenant_id
      left join mytrakin.profiles p on p.id = m.user_id
     where m.company_id = p_company_id
       and m.status = 'active'
       and m.role in ('vendor_admin', 'client_user')
       and (m.user_id is not null or m.invited_email is not null)
    union all
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
      select distinct on (lower(a.email)) a.user_id, a.name, a.email, a.company_role, a.rank
        from admins a, related r
       where r.ok and a.email is not null
       order by lower(a.email), a.rank, a.name
    ) d
   order by d.rank, d.name
$$;
