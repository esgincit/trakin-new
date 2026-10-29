-- =============================================================================
-- myTrakIn · 20261028000100 · Globally unique project codes
--
-- Project codes were unique per tenant (unique (tenant_id, code)), which let
-- two different workspaces generate the same code (e.g. PRJ-04). When a shared
-- project appears in another company's placement dropdown, the duplicate code
-- is confusing. Make project codes globally unique so every project has a
-- distinct code regardless of which workspace created it.
--
-- The existing retry loop in POST /projects (IntegrityError → recompute code)
-- handles any cross-tenant collision that slips past the numbering service's
-- _taken check.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Drop the per-tenant unique constraint
alter table mytrakin.projects drop constraint if exists projects_tenant_id_code_key;

-- Add a globally unique constraint on project code
alter table mytrakin.projects add constraint projects_code_key unique (code);
