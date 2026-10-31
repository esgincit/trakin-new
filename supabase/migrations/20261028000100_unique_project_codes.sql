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
--
-- Existing data already collides: every workspace numbered its first project
-- PRJ-01. Renumber the duplicates before adding the constraint, keeping the
-- oldest project on each code and moving the rest to the next free PRJ-<n>.
-- (Codes are display labels; nothing references a project by its code.)
-- =============================================================================

set search_path = mytrakin, public, extensions;

begin;

-- 1. Keep the oldest project on each code, renumber the later duplicates.
with ranked as (
    select id, code,
           row_number() over (partition by code order by created_at, id) as keep_no
      from mytrakin.projects
), dupes as (
    select id, row_number() over (order by code, id) as new_no
      from ranked
     where keep_no > 1
), base as (
    -- Highest number already used, so the new codes cannot collide with anything.
    select coalesce(max(substring(code from '^PRJ-([0-9]+)$')::int), 0) as max_no
      from mytrakin.projects
     where code ~ '^PRJ-[0-9]+$'
)
update mytrakin.projects p
   set code = 'PRJ-' || lpad((base.max_no + d.new_no)::text, 2, '0'),
       updated_at = now()
  from dupes d, base
 where p.id = d.id;

-- 2. Fail with a readable message (instead of a bare unique violation) if a
--    hand-typed code is still duplicated and cannot be renumbered automatically.
do $$
declare
    remaining text;
begin
    select string_agg(code, ', ') into remaining
      from (select code from mytrakin.projects group by code having count(*) > 1) d;
    if remaining is not null then
        raise exception 'Duplicate project codes remain after renumbering: %', remaining
            using hint = 'Give these projects distinct codes, then re-run the migration.';
    end if;
end $$;

-- 3. Swap the per-tenant unique constraint for a global one.
alter table mytrakin.projects drop constraint if exists projects_tenant_id_code_key;

alter table mytrakin.projects add constraint projects_code_key unique (code);

commit;
