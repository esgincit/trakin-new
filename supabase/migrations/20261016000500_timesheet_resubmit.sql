-- A consultant could not fix a week their approver returned: saving keeps the status at 'rejected',
-- but the update policy's WITH CHECK only allowed 'draft' or 'submitted' for the new row, so every
-- save of a returned week failed with 403. Allow the row to stay 'rejected' while it is being fixed.
drop policy if exists timesheets_consultant_update on mytrakin.timesheets;
create policy timesheets_consultant_update on mytrakin.timesheets for update to mytrakin_api
  using (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant() and status in ('draft', 'rejected'))
  with check (mytrakin.ctx_role() = 'consultant' and consultant_id = mytrakin.ctx_consultant()
              and status in ('draft', 'rejected', 'submitted'));
