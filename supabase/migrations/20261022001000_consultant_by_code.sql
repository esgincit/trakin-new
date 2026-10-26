-- =============================================================================
-- myTrakIn · 20261022001000 · Resolve a consultant's ID in imports
--
--   Imports tag people by their system user code (U000123) — but RLS hides
--   user_codes from the importing session, so the CSV importer would create
--   duplicates instead of matching. This SECURITY DEFINER helper resolves the
--   code inside the caller's own tenant only.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.consultant_by_code(p_code text)
returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select c.id from mytrakin.consultants c
   join mytrakin.user_codes uc on uc.user_id = c.user_id
  where upper(uc.code) = upper(p_code)
    and c.tenant_id = mytrakin.ctx_tenant()
  limit 1
$$;

revoke all on function mytrakin.consultant_by_code(text) from public;
grant execute on function mytrakin.consultant_by_code(text) to mytrakin_api;
