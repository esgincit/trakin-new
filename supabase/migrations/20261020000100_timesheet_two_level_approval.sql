-- =============================================================================
-- myTrakIn · 20261020000100 · Two-level timesheet approval
--
-- A timesheet must be approved by both companies on the placement chain:
--   - the Placed By company (the vendor that placed the consultant, ap_company_id)
--   - the End Client company (end_client_company_id)
--
-- Once both companies approve, the timesheet is fully approved.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.timesheets
  add column if not exists placed_by_approved boolean not null default false,
  add column if not exists end_client_approved boolean not null default false;

create index if not exists timesheets_placed_by_approved_idx on mytrakin.timesheets (placed_by_approved);
create index if not exists timesheets_end_client_approved_idx on mytrakin.timesheets (end_client_approved);
