-- =============================================================================
-- myTrakIn · 20261022000500 · ts_approval_links staff INSERT policy
--
--   After the placed-by approval the API e-mails the end client's approvers and
--   records the link (timesheets._send_client_approval inserts directly). That
--   runs in the placing workspace's staff session — but 20261021000400 created
--   only a SELECT policy on mytrakin.ts_approval_links, so the insert violated
--   RLS and POST /timesheets/{id}/approve failed with the mapped 403
--   "You don't have permission to do that" (SQLSTATE 42501).
--   Decisions themselves stay definer-scoped; only staff can create links.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists ts_links_staff_insert on mytrakin.ts_approval_links;
create policy ts_links_staff_insert on mytrakin.ts_approval_links for insert to mytrakin_api
  with check (mytrakin.can(VARIADIC array['approver', 'account_manager', 'hr', 'finance']));
