-- =============================================================================
-- myTrakIn · 20261031 0700 · The end client can open an approved week
--
--   History in the client's own workspace lists approved weeks from the placing
--   workspace (ts_client_history). Clicking one opened /timesheets/{id}, whose
--   RLS-scoped read returns nothing for that workspace — the page failed
--   instead of showing the approved week. This SECURITY DEFINER view returns the
--   same week, hours per project only for the caller's company, read-only.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.ts_client_history_view(p_ts uuid) returns json
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare
  t record;
  v_rows json;
  v_total numeric;
begin
  select ts.id, ts.week_start, ts.status, ts.note, ts.reject_reason, ts.decided_at,
         ts.placed_by_approved, ts.end_client_approved,
         k.full_name, k.engagement, emp.name as employer
    into t
    from mytrakin.timesheets ts
    join mytrakin.consultants k on k.id = ts.consultant_id
    left join mytrakin.companies emp on emp.id = k.employer_company_id
   where ts.id = p_ts;

  if t.id is null or t.status <> 'approved' then
    return null;
  end if;
  if not exists (
       select 1 from mytrakin.timesheet_entries e
         join mytrakin.placements p on p.id = e.placement_id
        where e.timesheet_id = p_ts
          and p.end_client_company_id = any (mytrakin.ts_my_companies())) then
    return null;
  end if;

  -- One row per project, seven day totals; only projects where this company is
  -- the end client (a legacy week can span more than one client's placements).
  select json_agg(json_build_object('placement_id', x.pid, 'project', x.project, 'hours', x.hours)
                  order by x.project),
         sum(x.hours_total)
    into v_rows, v_total
    from (
      select p.id as pid,
             coalesce(pr.name, 'Internal / non-billable') as project,
             (select json_agg(coalesce(d.h, 0) order by s.dn)
                from generate_series(0, 6) s(dn)
                left join (
                  select (e2.work_date - t.week_start) as dn, sum(e2.hours) as h
                    from mytrakin.timesheet_entries e2
                   where e2.timesheet_id = p_ts
                     and e2.placement_id is not distinct from p.id
                   group by 1) d on d.dn = s.dn) as hours,
             (select coalesce(sum(e3.hours), 0)
                from mytrakin.timesheet_entries e3
               where e3.timesheet_id = p_ts
                 and e3.placement_id is not distinct from p.id) as hours_total
        from mytrakin.timesheet_entries e
        left join mytrakin.placements p on p.id = e.placement_id
        left join mytrakin.projects pr on pr.id = p.project_id
       where e.timesheet_id = p_ts
         and (p.id is null or p.end_client_company_id = any (mytrakin.ts_my_companies()))
       group by p.id, pr.name
    ) x;

  return json_build_object(
    'id', t.id, 'week_start', t.week_start, 'status', t.status,
    'full_name', t.full_name, 'engagement', t.engagement, 'employer', t.employer,
    'note', t.note, 'reject_reason', t.reject_reason, 'decided_at', t.decided_at,
    'placed_by_approved', t.placed_by_approved, 'end_client_approved', t.end_client_approved,
    'rows', coalesce(v_rows, '[]'::json),
    'total_hours', coalesce(v_total, 0),
    'checks', '[]'::json,
    'summary', json_build_object('label', 'Approved', 'result', 'pass'),
    'client_view', true,
    'awaiting_end_client', false,
    'end_client_companies', '[]'::json);
end $$;
revoke all on function mytrakin.ts_client_history_view(uuid) from public;
grant execute on function mytrakin.ts_client_history_view(uuid) to mytrakin_api;
