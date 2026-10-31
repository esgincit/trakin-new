-- =============================================================================
-- myTrakIn · 20261031 0100 · The end client's completed weeks (History)
--
--   20261021 0500 gave the end client's own workspace a queue of weeks waiting
--   on its approval (ts_client_queue). Once the week is approved it leaves that
--   queue and there was nowhere left to see it: the timesheet belongs to the
--   placing workspace, and the restrictive tenant isolation hides it from the
--   client's workspace. The History tab therefore showed nothing even though
--   the client had just approved the week.
--
--   ts_client_history() is the read-only counterpart of the queue: the weeks
--   this company approved as the end client, keyed on the same companies the
--   caller acts for (ts_my_companies) — never relaxing tenant isolation for
--   anything else.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.ts_client_history()
returns table (
  timesheet_id uuid, week_start date, status text, consultant text, consultant_id uuid,
  engagement text, employer text, project text, hours numeric, decided_at timestamptz,
  placed_by text, placed_by_approved boolean, end_client_approved boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.week_start, t.status, c.full_name, c.id, c.engagement, emp.name,
         coalesce(pr.name, 'Internal'), sum(e.hours), t.decided_at, tn.name,
         t.placed_by_approved, t.end_client_approved
    from mytrakin.timesheets t
    join mytrakin.consultants c on c.id = t.consultant_id
    join mytrakin.timesheet_entries e on e.timesheet_id = t.id
    left join mytrakin.placements p on p.id = e.placement_id
    left join mytrakin.projects pr on pr.id = p.project_id
    left join mytrakin.companies emp on emp.id = c.employer_company_id
    left join mytrakin.tenants tn on tn.id = t.tenant_id
   where t.status = 'approved'
     and exists (select 1 from mytrakin.placements p2
                  where p2.consultant_id = t.consultant_id
                    and p2.end_client_company_id = any (mytrakin.ts_my_companies()))
     -- Only the projects this company is the end client on: a legacy timesheet
     -- can cover placements for more than one client, and the others' hours and
     -- project names are none of its business.
     and p.end_client_company_id = any (mytrakin.ts_my_companies())
   group by t.id, c.id, pr.name, emp.name, tn.name
   order by t.week_start desc, c.full_name, coalesce(pr.name, 'Internal')
   limit 2000;
$$;
revoke all on function mytrakin.ts_client_history() from public;
grant execute on function mytrakin.ts_client_history() to mytrakin_api;
