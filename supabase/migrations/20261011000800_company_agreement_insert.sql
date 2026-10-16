-- =============================================================================
-- myTrakIn · 0800 · Let membership-linked company admins create agreements
--
-- 0780's agreements_write INSERT policy only accepted staff roles or a
-- company_members row (super_admin/owner/admin) on the initiating company.
-- A vendor_admin / client_admin / client_user has NO company_members row —
-- their authority comes from memberships (role + membership.company_id, surfaced
-- as app.company_id by begin_request). The API gate (_can_manage_company)
-- already allows them, so the INSERT died with 42501 → HTTP 403.
-- Accept initiator_company_id = ctx_company() for those membership roles.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists agreements_write on mytrakin.agreements;
create policy agreements_write on mytrakin.agreements for insert to mytrakin_api
  with check (tenant_id = mytrakin.ctx_tenant()
      and (mytrakin.can('legal', 'account_manager', 'finance', 'hr')
          or mytrakin.company_role(initiator_company_id) in ('super_admin', 'owner', 'admin')
          or (initiator_company_id is not null
              and initiator_company_id = mytrakin.ctx_company()
              and mytrakin.ctx_role() in ('vendor_admin', 'client_admin', 'client_user'))));
