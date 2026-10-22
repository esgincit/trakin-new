-- =============================================================================
-- myTrakIn · 20261022000300 · Fix the rejected-timesheet resubmit RLS check
--
--   When a consultant's timesheet week is returned (rejected), they must be able
--   to edit and resubmit it (PUT /timesheets/mine). The consultant update policy's
--   USING clause accepts rows in 'draft'/'rejected', but its deployed WITH CHECK
--   lost the 'rejected' status (draft + submitted only) — so touching a rejected
--   row violated the policy and the API surfaced it as 403
--   "You don't have permission to do that" (SQLSTATE 42501).
--   Recreate the policy with the statuses aligned on both sides.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists timesheets_consultant_update on mytrakin.timesheets;
create policy timesheets_consultant_update on mytrakin.timesheets for update to mytrakin_api
  using (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
           and status in ('draft', 'rejected'))
  with check (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
           and status in ('draft', 'rejected', 'submitted'));
