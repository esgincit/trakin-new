-- =============================================================================
-- myTrakIn · 0720 · Company members read their own company
--
-- Anyone with a company membership (owner/admin/member) can open that company's
-- profile, whatever their workspace role — otherwise a consultant who creates a
-- business could never see it. Money and tax shielding still happens in the API.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_member on mytrakin.companies;
create policy companies_member on mytrakin.companies for select to mytrakin_api
  using (mytrakin.company_role(id) is not null);
