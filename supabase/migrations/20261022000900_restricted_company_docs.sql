-- =============================================================================
-- myTrakIn · 20261022000900 · Restricted company compliance documents
--
--   US companies may create with manually typed W-9 details and upload the
--   document afterwards; the platform verifies that W-9 before activation and
--   can additionally attach government-issued certificates (tax certificate,
--   certificate of good standing, and so on). Those files carry confidential
--   taxpayer identities: they are visible only to the platform team and that
--   company's super admin (owners), never to ordinary members or other tenants.
--
--   documents.restricted marks them. can_see_restricted() is the single gate:
--   platform role (including 'system', which the platform uses while acting
--   inside a tenant) or the owning company's super_admin / owner.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.documents add column if not exists restricted boolean not null default false;

create or replace function mytrakin.can_see_restricted(p_owner_type text, p_owner_id uuid)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select mytrakin.ctx_role() in ('platform_admin', 'system')
      or (p_owner_type = 'company' and mytrakin.company_role(p_owner_id) in ('super_admin', 'owner'))
$$;

-- Read: restricted rows only through the gate; everything keeps today's visibility.
drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
    mytrakin.can_see_restricted(owner_type, owner_id)
    or (restricted is false and (
      is_internal()
      or (mytrakin.ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = mytrakin.ctx_consultant()) or owner_type = 'policy'))
      or (mytrakin.ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = mytrakin.ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
            where s.id = owner_id and s.created_by = mytrakin.ctx_user()))))));

-- Upload: restricted rows only by the platform or that company's super admin / owner;
-- unrestricted rows keep today's rules.
drop policy if exists documents_upload on mytrakin.documents;
create policy documents_upload on mytrakin.documents for insert to mytrakin_api
  with check ((
    mytrakin.can_see_restricted(owner_type, owner_id)
    or (restricted is false and (
      is_internal()
      or (mytrakin.ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = mytrakin.ctx_consultant()))
      or (mytrakin.ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = mytrakin.ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) in ('super_admin', 'owner', 'admin'))
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
            where s.id = owner_id and s.created_by = mytrakin.ctx_user()))
      or (mytrakin.ctx_role() = 'public' and owner_type = 'registration')))));
