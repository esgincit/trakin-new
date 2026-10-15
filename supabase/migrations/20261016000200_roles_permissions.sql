-- =============================================================================
-- myTrakIn · P · 0200 · Owner-configurable roles & permissions
--   custom_roles: a named role built on a base role + a module → none/read/write map
--   memberships.custom_role_id / permission_overrides: per-user assignment and exceptions
--   Only the company owner writes; members of the company can read role names.
-- =============================================================================
set search_path = mytrakin, public, extensions;

create table if not exists custom_roles (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  name        text not null check (length(name) between 2 and 60),
  base_role   text not null check (base_role in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr',
                                                 'approver', 'viewer', 'vendor_admin', 'client_user', 'consultant')),
  permissions jsonb not null default '{}'::jsonb,
  created_by  uuid,
  created_at  timestamptz not null default now()
);
create unique index if not exists custom_roles_name_uq on custom_roles (tenant_id, lower(name));

alter table memberships
  add column if not exists custom_role_id       uuid references custom_roles (id) on delete set null,
  add column if not exists permission_overrides jsonb not null default '{}'::jsonb;

alter table custom_roles enable row level security;
drop policy if exists custom_roles_read on custom_roles;
create policy custom_roles_read on custom_roles for select to mytrakin_api using (tenant_id = ctx_tenant());
drop policy if exists custom_roles_write on custom_roles;
create policy custom_roles_write on custom_roles for all to mytrakin_api
  using (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'))
  with check (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'));
grant select, insert, update, delete on custom_roles to mytrakin_api;

drop trigger if exists custom_roles_audit on custom_roles;
create trigger custom_roles_audit after insert or update or delete on custom_roles
  for each row execute function audit_row();
