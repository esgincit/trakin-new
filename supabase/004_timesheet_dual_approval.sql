-- 004: dual-approval timesheet workflow (Placed By + End Client)
-- A consultant's timesheet must be routed to both the Placed By company
-- and the End Client company; it is fully approved only after BOTH approve.

-- Placement chain parties (who placed the consultant / who is the end client)
alter table public.placements
  add column if not exists end_client_company_id uuid references public.companies(id),
  add column if not exists placed_by_company_id uuid references public.companies(id);

-- Per-party approval state on the timesheet.
-- Overall status stays one of ('Not submitted','Submitted','Approved','Rejected'):
-- 'Approved' only when both parties approved; any rejection => 'Rejected'.
alter table public.timesheets
  add column if not exists placement_id uuid references public.placements(id),
  add column if not exists placed_by_status text not null default 'Pending'
    check (placed_by_status in ('Pending','Approved','Rejected')),
  add column if not exists placed_by_decided_by uuid references public.app_users(id),
  add column if not exists placed_by_decided_at timestamptz,
  add column if not exists placed_by_reject_reason text,
  add column if not exists end_client_status text not null default 'Pending'
    check (end_client_status in ('Pending','Approved','Rejected')),
  add column if not exists end_client_decided_by uuid references public.app_users(id),
  add column if not exists end_client_decided_at timestamptz,
  add column if not exists end_client_reject_reason text;

create index if not exists timesheet_lines_timesheet_idx on public.timesheet_lines(timesheet_id);
create index if not exists placements_end_client_idx on public.placements(end_client_company_id);
create index if not exists placements_placed_by_idx on public.placements(placed_by_company_id);

-- FKs on decided_by columns (added separately so this also applies when the
-- columns were created by schema.sql without FKs). FK to app_users (backend
-- identity), matching 003_auth_fk.sql.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'timesheets_placed_by_decided_by_fkey') then
    alter table public.timesheets
      add constraint timesheets_placed_by_decided_by_fkey foreign key (placed_by_decided_by) references public.app_users(id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'timesheets_end_client_decided_by_fkey') then
    alter table public.timesheets
      add constraint timesheets_end_client_decided_by_fkey foreign key (end_client_decided_by) references public.app_users(id);
  end if;
end $$;
