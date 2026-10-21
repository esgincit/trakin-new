-- =============================================================================
-- myTrakIn · 20261021 0100 · Weekend-hours confirmation workflow
--
--   Weekend hours stay a "review" check, but approval is now gated: the approver
--   asks the consultant to confirm the weekend work (optionally with a note), the
--   consultant is told by e-mail (logged in notifications) and sees a banner in
--   My timesheet, and the week can only be approved once the consultant confirms.
--   Rejecting, returning or resubmitting clears the state so every round starts
--   fresh.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.timesheets
  add column if not exists weekend_requested_by uuid,
  add column if not exists weekend_requested_at timestamptz,
  add column if not exists weekend_review_note text,
  add column if not exists weekend_confirmed boolean not null default false,
  add column if not exists weekend_confirmed_by uuid,
  add column if not exists weekend_confirmed_at timestamptz;
