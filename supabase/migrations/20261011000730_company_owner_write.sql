-- =============================================================================
-- myTrakIn · 0730 · Company owners can drive onboarding, whatever their workspace role
--
-- Creating is open to members, so writing must be too — scoped to companies the
-- caller owns or admins (activation and money rules stay staff-only in the API):
--   companies   : any signed-in member may insert drafts (status onboarding);
--                 owners/admins may update their own company's onboarding data
--                 (which columns is enforced per-endpoint in the API);
--                 deletes stay with staff
--   documents / tracked_documents: company owners/admins may manage their own
--                 company's files (W-9 uploads, logos)
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_write on mytrakin.companies;
drop policy if exists companies_insert on mytrakin.companies;
drop policy if exists companies_staff_update on mytrakin.companies;
drop policy if exists companies_staff_delete on mytrakin.companies;
drop policy if exists companies_creator on mytrakin.companies;
drop policy if exists companies_owner_update on mytrakin.companies;
create policy companies_insert on mytrakin.companies for insert to mytrakin_api
  with check (mytrakin.ctx_role() not in ('anonymous', 'public', 'signer') and status = 'onboarding');
create policy companies_staff_update on mytrakin.companies for update to mytrakin_api
  using (mytrakin.can('account_manager', 'finance', 'legal'))
  with check (mytrakin.can('account_manager', 'finance', 'legal'));
create policy companies_staff_delete on mytrakin.companies for delete to mytrakin_api
  using (mytrakin.can('account_manager', 'finance', 'legal'));

-- The creator can read their draft back (INSERT ... RETURNING checks SELECT
-- policies too, and no membership exists yet at insert time).
create policy companies_creator on mytrakin.companies for select to mytrakin_api
  using (created_by is not null and created_by = mytrakin.ctx_user());

-- Owners/admins keep their company's onboarding data moving (tax, logo, W-9,
-- verification). Which columns each role may touch is enforced in the API;
-- activation itself stays staff-only there.
create policy companies_owner_update on mytrakin.companies for update to mytrakin_api
  using (mytrakin.company_role(id) in ('owner', 'admin'))
  with check (mytrakin.company_role(id) in ('owner', 'admin'));

drop policy if exists documents_upload on mytrakin.documents;
drop policy if exists documents_read on mytrakin.documents;
create policy documents_upload on mytrakin.documents for insert to mytrakin_api
  with check (is_internal()
      or (ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) in ('owner', 'admin'))
      or (ctx_role() = 'public' and owner_type = 'registration'));

drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)));

drop policy if exists tracked_write on mytrakin.tracked_documents;
create policy tracked_write on mytrakin.tracked_documents for all to mytrakin_api
  using (mytrakin.can('hr', 'legal')
         or (company_id is not null and mytrakin.company_role(company_id) in ('owner', 'admin')))
  with check (mytrakin.can('hr', 'legal')
              or (company_id is not null and mytrakin.company_role(company_id) in ('owner', 'admin')));

drop policy if exists tracked_read on mytrakin.tracked_documents;
create policy tracked_read on mytrakin.tracked_documents for select to mytrakin_api
  using (is_internal()
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and (company_id = ctx_company() or exists (
            select 1 from consultants c where c.id = tracked_documents.consultant_id and c.employer_company_id = ctx_company())))
      or (company_id is not null and mytrakin.company_role(company_id) is not null));
