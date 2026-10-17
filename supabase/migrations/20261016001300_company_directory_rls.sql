-- =============================================================================
-- myTrakIn · 20261016 1300 · Close the cross-tenant company read hole
--
--   Migration 0780 added `companies_directory`: "every non-inactive company,
--   readable by any signed-in member". Written as a bare
--   `ctx_role() not in ('anonymous','public','signer')` it grants far more
--   than a directory — it lets ANY signed-in person SELECT every row of
--   `companies` in EVERY tenant: contact e-mail, address, EIN, W-9 status and
--   data, notes, bank_verified. That is a RULE-05 / SEC-13 breach (tenant
--   isolation) and it made GET /companies/{id} answer 200 for another
--   workspace's company.
--
--   Migration 1000 already replaced the picker's need with narrow
--   security-definer functions (`company_directory_all`,
--   `company_public_name`, `company_counterparty`) that expose directory
--   columns only. So the broad policy is now redundant as well as unsafe:
--   drop it. Legitimate reads are all covered by the remaining policies —
--   `tenant_isolation` (own workspace), `companies_internal` (staff),
--   `companies_member` (a company member), `companies_own` (vendor/client
--   admin's own company) and `companies_consultant` (a consultant's chain).
--
--   Nothing is lost: the MSA counterparty picker, agreement counterparty
--   names and counterparty e-mails all go through the 1000 helpers.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists companies_directory on mytrakin.companies;