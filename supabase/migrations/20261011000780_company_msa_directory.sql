-- =============================================================================
-- myTrakIn · 0780 · MSAs as connections between two companies
--
-- A company admin picks the counterparty from a searchable directory and
-- records (or requests) an MSA. Supporting schema:
--   agreements.initiator_company_id  the company that started it (null = staff record)
--   companies_directory             every non-inactive company, readable by any
--                                   signed-in tenant member (names only downstream)
--   agreements_party                either side's company users can read their MSAs
--   agreements_write                owners/admins of the initiating company may
--                                   *create* (updates/deletes stay staff-only)
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.agreements
  add column if not exists initiator_company_id uuid references mytrakin.companies (id) on delete set null;
create index if not exists agreements_initiator_idx on mytrakin.agreements (tenant_id, initiator_company_id);

drop policy if exists agreements_party on mytrakin.agreements;
create policy agreements_party on mytrakin.agreements for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user')
          and (company_id = ctx_company() or initiator_company_id = ctx_company()))
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (mytrakin.company_role(company_id) is not null)
      or (initiator_company_id is not null and mytrakin.company_role(initiator_company_id) is not null));

drop policy if exists agreements_write on mytrakin.agreements;
create policy agreements_write on mytrakin.agreements for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr')
      or (initiator_company_id is not null
          and mytrakin.company_role(initiator_company_id) in ('super_admin', 'owner', 'admin')));
create policy agreements_staff_write on mytrakin.agreements for update to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'))
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
create policy agreements_staff_delete on mytrakin.agreements for delete to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop policy if exists companies_directory on mytrakin.companies;
create policy companies_directory on mytrakin.companies for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));
