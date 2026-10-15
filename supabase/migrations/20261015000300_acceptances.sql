-- =============================================================================
-- myTrakIn · 20261015 0300 · Acceptance records (PLAN WF-05, WF-06)
--
--   Who accepted an NDA / MSA / SOW / amendment / resource contract, when and how
--   (e-signature or recorded by staff for paper / e-mail acceptance). E-sign completion
--   writes one automatically. The full history stays here and in the audit log.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.acceptances (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references mytrakin.tenants (id) on delete cascade,
  entity_type  text not null check (entity_type in ('agreement', 'sow', 'amendment')),
  entity_id    uuid not null,
  accepted_by  text not null,
  accepted_at  timestamptz not null default now(),
  method       text not null check (method in ('esign', 'manual')),
  envelope_id  uuid references mytrakin.envelopes (id) on delete set null,
  note         text,
  created_by   uuid
);
create index if not exists acceptances_entity_idx on mytrakin.acceptances (tenant_id, entity_type, entity_id);

grant select, insert on mytrakin.acceptances to mytrakin_api;
alter table mytrakin.acceptances enable row level security;
drop policy if exists tenant_isolation on mytrakin.acceptances;
create policy tenant_isolation on mytrakin.acceptances as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists acceptances_read on mytrakin.acceptances;
create policy acceptances_read on mytrakin.acceptances for select to mytrakin_api using (mytrakin.is_internal());
drop policy if exists acceptances_write on mytrakin.acceptances;
create policy acceptances_write on mytrakin.acceptances for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop trigger if exists acceptances_audit on mytrakin.acceptances;
create trigger acceptances_audit after insert or update or delete on mytrakin.acceptances
  for each row execute function mytrakin.audit_row();
