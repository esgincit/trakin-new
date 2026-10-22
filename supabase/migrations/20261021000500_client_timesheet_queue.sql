-- =============================================================================
-- myTrakIn · 20261021 0500 · The end client's in-app timesheet queue
--
--   After the placed-by approval, the week must be visible to the end client's
--   own workspace too — a "waiting for us" list on the Timesheets page, with an
--   approval link they can act on right away (the e-mail flow from 0400 uses the
--   same link table). These SECURITY DEFINER helpers never relax the restrictive
--   tenant isolation: they expose exactly one thing — weeks waiting on our end-
--   client approval — keyed on the companies the caller acts for (their workspace's
--   own company, or the company their membership represents).
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- The companies the caller acts for in this workspace: their membership's company
-- (client_user and vendor reps) plus the workspace's own company.
create or replace function mytrakin.ts_my_companies() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct x), '{}') from (
    select mytrakin.ctx_company() as x where mytrakin.ctx_company() is not null
    union all
    select t.company_id from mytrakin.tenants t
     where t.id = mytrakin.ctx_tenant() and t.company_id is not null) s;
$$;
revoke all on function mytrakin.ts_my_companies() from public;
grant execute on function mytrakin.ts_my_companies() to mytrakin_api;

-- Weeks whose placed-by approval is in and are waiting on us as the end client.
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
     and exists (select 1 from mytrakin.placements p
                  where p.consultant_id = t.consultant_id
                    and p.end_client_company_id = any (mytrakin.ts_my_companies()))
   order by t.week_start desc, c.full_name;
$$;
revoke all on function mytrakin.ts_client_queue() from public;
grant execute on function mytrakin.ts_client_queue() to mytrakin_api;

-- One waiting week's review data for an end-client approver (hours only, no rates).
create or replace function mytrakin.ts_client_view(p_ts uuid) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; tn text; weeks json; total numeric; v_client text;
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
  if not exists (select 1 from mytrakin.placements p
                  where p.consultant_id = ts.consultant_id
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
revoke all on function mytrakin.ts_client_view(uuid) from public;
grant execute on function mytrakin.ts_client_view(uuid) to mytrakin_api;

-- Create (or refresh) an approval link for a waiting week, from inside the client's
-- own workspace or as its representative. The token itself is passed in (hashed here).
create or replace function mytrakin.ts_client_link(p_ts uuid, p_hash text, p_creator uuid) returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare v json; link uuid;
begin
  v := mytrakin.ts_client_view(p_ts);
  if v is null or v ->> 'error' is not null then
    return v;
  end if;
  insert into mytrakin.ts_approval_links (tenant_id, timesheet_id, token_hash, created_by)
  values ((v ->> 'tenant_id')::uuid, p_ts, p_hash, p_creator) returning id into link;
  return json_build_object('ok', true, 'timesheet_id', p_ts, 'link_id', link);
end $$;
revoke all on function mytrakin.ts_client_link(uuid, text, uuid) from public;
grant execute on function mytrakin.ts_client_link(uuid, text, uuid) to mytrakin_api;

-- The end client's in-app decision — same gates and effects as the link decision.
create or replace function mytrakin.ts_client_decide_ts(p_ts uuid, p_decision text, p_note text default null)
returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  ts record; v_client text; v_creator text; v_cemail text; out_name text;
begin
  select t.*, c.full_name, c.engagement into ts
    from mytrakin.timesheets t join mytrakin.consultants c on c.id = t.consultant_id
   where t.id = p_ts;
  if ts.id is not null and ts.status = 'submitted' and ts.placed_by_approved then
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
revoke all on function mytrakin.ts_client_decide_ts(uuid, text, text) from public;
grant execute on function mytrakin.ts_client_decide_ts(uuid, text, text) to mytrakin_api;

-- The links table was created after the original security grants, so grant it now.
grant select, insert, update, delete on mytrakin.ts_approval_links to mytrakin_api;
