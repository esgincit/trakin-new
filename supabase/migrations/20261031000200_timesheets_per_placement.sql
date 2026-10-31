-- =============================================================================
-- myTrakIn · 20261031 0200 · One timesheet per project, not per week
--
--   The per-placement split (04011b0) writes one timesheet per project so each
--   project is routed to its own placed-by company and end client. The table
--   still carried the original `unique (consultant_id, week_start)` from the
--   one-timesheet-per-week design, so inserting the second project's timesheet
--   failed with a duplicate key — saving a second project returned
--   409 "A record with the same key already exists" and that project could
--   never be submitted.
--
--   Drop the weekly uniqueness; a plain index keeps the per-consultant/week
--   lookups fast.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.timesheets drop constraint if exists timesheets_consultant_id_week_start_key;

create index if not exists timesheets_consultant_week_idx
    on mytrakin.timesheets (consultant_id, week_start);
