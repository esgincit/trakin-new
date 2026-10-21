-- =============================================================================
-- myTrakIn · 20261021 0200 · End-client approval of placed-by timesheets
--
--   Two-level approval: the company that placed the consultant approves first
--   (its staff, in its own workspace). The end client approves second — but only
--   that company's own representative can do it: someone the placing company
--   invited into its workspace as a member of the end client's company
--   (client_user with company_id = the end client). These policies give that
--   representative read access to the timesheet and the right to approve it.
--   Everything else stays as-is: money columns are masked for client_user by
--   the API layer, and other roles are untouched.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create policy timesheets_client_read on mytrakin.timesheets for select to mytrakin_api
  using (ctx_role() = 'client_user' and timesheets.status in ('submitted', 'approved') and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()));

create policy timesheets_client_approve on mytrakin.timesheets for update to mytrakin_api
  using (ctx_role() = 'client_user' and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()))
  with check (ctx_role() = 'client_user' and exists (
           select 1 from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = timesheets.id
              and p.end_client_company_id = ctx_company()));

-- The review page joins the consultant's details; let the end client's
-- representative see the consultants behind the timesheets they must approve.
create policy consultants_client_read on mytrakin.consultants for select to mytrakin_api
  using (ctx_role() = 'client_user' and exists (
           select 1 from timesheets t join timesheet_entries e on e.timesheet_id = t.id
                 join placements p on p.id = e.placement_id
            where t.consultant_id = consultants.id
              and p.end_client_company_id = ctx_company()));
