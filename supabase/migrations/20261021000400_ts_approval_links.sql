-- =============================================================================
-- myTrakIn · 20261021 0400 · End-client timesheet approval links
--
--   The placed-by company approves first; the week then flows to the end client's
--   timesheet manager. That person may not be a member of the placing workspace, so
--   the flow works the way e-signatures do: a personal, expiring link (token hashed
--   at rest) opens a read-only view of the week and lets them approve it or return
--   it with a note — no account or membership needed for that one decision.
--   The link read/decide helpers are SECURITY DEFINER and tightly scoped: they only
--   ever touch the linked timesheet, and only while it is placed-by-approved and
--   still awaiting the end client.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.ts_approval_links (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,                 -- the placing workspace
  timesheet_id uuid not null references mytrakin.timesheets (id) on delete cascade,
  company_id uuid,                         -- the end-client company this link is for
  token_hash text not null unique,
  created_by uuid,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '45 days',
  used_at timestamptz
);
create index if not exists ts_approval_links_ts_idx on mytrakin.ts_approval_links (timesheet_id);

alter table mytrakin.ts_approval_links enable row level security;
create policy ts_links_internal on mytrakin.ts_approval_links for select to mytrakin_api
  using (is_internal());

-- What the public approval page shows: the week's hours, no rates, and the state.
create or replace function mytrakin.ts_approval_view(p_hash text) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; tn text; weeks json; total numeric;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null then
    return json_build_object('error', 'used');
  end if;
  if link.expires_at < now() then
    return json_build_object('error', 'expired');
  end if;
  select t.*, c.full_name, c.engagement, emp.name as employer
    into ts
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
    left join mytrakin.companies emp on emp.id = c.employer_company_id
   where t.id = link.timesheet_id;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select name into tn from mytrakin.tenants where id = link.tenant_id;
  select coalesce(sum(hours), 0) into total from mytrakin.timesheet_entries where timesheet_id = link.timesheet_id;
  select json_agg(x) into weeks
    from (select coalesce(pr.name, 'Internal / non-billable') as project,
                 json_agg(json_build_object('d', e.work_date, 'h', e.hours) order by e.work_date) as hours
            from mytrakin.timesheet_entries e
            left join mytrakin.placements p on p.id = e.placement_id
            left join mytrakin.projects pr on pr.id = p.project_id
           where e.timesheet_id = link.timesheet_id
           group by 1) x;
  return json_build_object(
    'timesheet_id', ts.id, 'week_start', ts.week_start, 'status', ts.status,
    'consultant', ts.full_name, 'engagement', ts.engagement, 'employer', ts.employer,
    'placed_by', tn, 'note', ts.note, 'rows', coalesce(weeks, '[]'::json), 'total_hours', total,
    'expires_at', link.expires_at);
end $$;
revoke all on function mytrakin.ts_approval_view(text) from public;
grant execute on function mytrakin.ts_approval_view(text) to mytrakin_api;

-- The end client's decision. Borrowed links can't restart a decided week.
create or replace function mytrakin.ts_client_decide(p_hash text, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  link record; ts record; v_creator text; v_client text; v_cemail text;
begin
  select * into link from mytrakin.ts_approval_links where token_hash = p_hash;
  if link.id is null then
    return json_build_object('error', 'invalid');
  end if;
  if link.used_at is not null or link.expires_at < now() then
    return json_build_object('error', case when link.used_at is not null then 'used' else 'expired' end);
  end if;
  select * into ts from mytrakin.timesheets where id = link.timesheet_id for update;
  if ts.id is null or ts.status <> 'submitted' or not ts.placed_by_approved then
    return json_build_object('error', 'not_ready');
  end if;
  select coalesce((select email from mytrakin.profiles where id = link.created_by), '') into v_creator;
  select coalesce(c.name, '') into v_client from mytrakin.companies c where c.id = link.company_id;
  select coalesce((select p.email from mytrakin.profiles p where p.id = c.user_id), c.email, '')
    into v_cemail
    from mytrakin.consultants c join mytrakin.timesheets t on t.consultant_id = c.id
   where t.id = link.timesheet_id;

  if p_decision = 'approve' then
    update mytrakin.timesheets
       set status = 'approved', end_client_approved = true, decided_at = now(), reject_reason = null
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'approved', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  elsif p_decision = 'return' then
    if p_note is null or length(btrim(p_note)) < 3 then
      return json_build_object('error', 'note_required');
    end if;
    update mytrakin.timesheets
       set status = 'rejected', reject_reason = btrim(p_note), decided_at = now(),
           placed_by_approved = false, end_client_approved = false
     where id = ts.id;
    update mytrakin.ts_approval_links set used_at = now() where id = link.id;
    return json_build_object('ok', true, 'status', 'rejected', 'week_start', ts.week_start,
                             'tenant_id', link.tenant_id, 'creator_email', v_creator,
                             'consultant', ts.full_name, 'company_name', v_client,
                             'consultant_email', v_cemail);
  end if;
  return json_build_object('error', 'invalid_decision');
end $$;
revoke all on function mytrakin.ts_client_decide(text, text, text) from public;
grant execute on function mytrakin.ts_client_decide(text, text, text) to mytrakin_api;
