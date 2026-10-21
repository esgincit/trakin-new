-- =============================================================================
-- myTrakIn · 20261021 0300 · Fix RLS recursion from the client-approval policies
--
--   20261021000200 wrote the end-client checks as EXISTS over timesheet_entries;
--   entries_read itself exists-checks timesheets, so planning any timesheets
--   query looped (Postgres: "infinite recursion detected in policy") and every
--   role got a 500 — the week overview, history and review pages all died.
--   Re-express the checks through a SECURITY DEFINER helper on placements
--   (which never re-enters the timesheets policies), then recreate the policies.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists timesheets_client_read on mytrakin.timesheets;
drop policy if exists timesheets_client_approve on mytrakin.timesheets;
drop policy if exists consultants_client_read on mytrakin.consultants;

create or replace function mytrakin.client_is_end_client(p_consultant uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from mytrakin.placements p
     where p.consultant_id = p_consultant
       and p.end_client_company_id = mytrakin.ctx_company());
$$;

revoke all on function mytrakin.client_is_end_client(uuid) from public;
grant execute on function mytrakin.client_is_end_client(uuid) to mytrakin_api;

create policy timesheets_client_read on mytrakin.timesheets for select to mytrakin_api
  using (ctx_role() = 'client_user' and timesheets.status in ('submitted', 'approved')
         and mytrakin.client_is_end_client(timesheets.consultant_id));

create policy timesheets_client_approve on mytrakin.timesheets for update to mytrakin_api
  using (ctx_role() = 'client_user' and mytrakin.client_is_end_client(timesheets.consultant_id))
  with check (ctx_role() = 'client_user' and mytrakin.client_is_end_client(timesheets.consultant_id));

-- The review page joins the consultant's details; let the end client's
-- representative see the consultants behind the timesheets they must approve.
create policy consultants_client_read on mytrakin.consultants for select to mytrakin_api
  using (ctx_role() = 'client_user' and mytrakin.client_is_end_client(consultants.id));
