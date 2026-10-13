-- =============================================================================
-- myTrakIn · 0400 · Grants and row-level security
--
-- Layers of protection:
--   1. Supabase client roles (anon, authenticated) get NO access to this schema.
--   2. The API switches to mytrakin_api, which has table grants but no BYPASSRLS.
--   3. A RESTRICTIVE policy on every tenant table pins rows to app.tenant_id.
--   4. PERMISSIVE policies decide what each role may read or change.
--   5. The API additionally hides columns a role must not see (e.g. rates).
-- =============================================================================

set search_path = mytrakin, public, extensions;

revoke all on all tables in schema mytrakin from public;
revoke all on schema mytrakin from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on all tables in schema mytrakin from anon, authenticated';
    execute 'revoke all on schema mytrakin from anon, authenticated';
  end if;
end $$;

grant select, insert, update, delete on all tables in schema mytrakin to mytrakin_api;
grant usage, select on all sequences in schema mytrakin to mytrakin_api;
revoke insert, update, delete on mytrakin.audit_log from mytrakin_api;
revoke update, delete on mytrakin.signature_events from mytrakin_api;

-- -----------------------------------------------------------------------------
-- Session start: resolve the caller's role for a tenant (runs before the role
-- switch, so it may read memberships without a tenant context).
-- -----------------------------------------------------------------------------
create or replace function resolve_access(p_user uuid, p_tenant uuid)
returns table (tenant_id uuid, role text, company_id uuid, consultant_id uuid, membership_id uuid, is_platform_admin boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select m.tenant_id, m.role, m.company_id, m.consultant_id, m.id,
         exists (select 1 from platform_admins pa where pa.user_id = p_user)
    from memberships m
    join tenants t on t.id = m.tenant_id
   where m.user_id = p_user
     and m.status = 'active'
     and t.status <> 'closed'
     and (p_tenant is null or m.tenant_id = p_tenant)
   order by m.created_at
   limit 1
$$;

create or replace function my_tenants(p_user uuid)
returns table (tenant_id uuid, tenant_name text, role text, tenant_status text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, t.name, m.role, t.status
    from memberships m join tenants t on t.id = m.tenant_id
   where m.user_id = p_user and m.status = 'active'
   order by t.name
$$;

create or replace function is_platform_admin_user(p_user uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from platform_admins where user_id = p_user)
$$;

-- Lists active tenants for scheduled jobs (cron runs one tenant at a time).
create or replace function active_tenant_ids() returns setof uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select id from tenants where status in ('onboarding', 'active')
$$;

revoke all on function resolve_access(uuid, uuid), my_tenants(uuid), is_platform_admin_user(uuid), active_tenant_ids() from public;
grant execute on function resolve_access(uuid, uuid), my_tenants(uuid), is_platform_admin_user(uuid), active_tenant_ids() to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Turn RLS on everywhere and pin tenant tables to the request's tenant.
-- -----------------------------------------------------------------------------
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'mytrakin' loop
    execute format('alter table mytrakin.%I enable row level security', t);
  end loop;

  foreach t in array array['memberships', 'counters', 'companies', 'consultants', 'agreements', 'sows', 'sow_amendments',
                           'projects', 'placements', 'timesheets', 'timesheet_entries', 'invoices', 'payments',
                           'collection_notes', 'expenses', 'time_off', 'payroll_lines', 'referral_agreements',
                           'referral_payments', 'documents', 'tracked_documents', 'policies', 'policy_acceptances',
                           'registrations', 'envelopes', 'envelope_signers', 'signature_events', 'reminder_rules',
                           'notifications', 'import_jobs', 'audit_log']
  loop
    execute format(
      'create policy tenant_isolation on mytrakin.%I as restrictive to mytrakin_api
         using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant())', t);
  end loop;
end $$;

-- Shorthand used below:
--   internal()  = tenant staff     can(...) = staff with one of the roles (admins always pass)

-- Tenants and platform -----------------------------------------------------------
create policy tenants_read on tenants for select to mytrakin_api
  using (id = ctx_tenant() or is_platform_admin());
create policy tenants_admin on tenants for update to mytrakin_api
  using (is_platform_admin() or (id = ctx_tenant() and can('tenant_admin')))
  with check (is_platform_admin() or (id = ctx_tenant() and can('tenant_admin')));
create policy tenants_create on tenants for insert to mytrakin_api with check (is_platform_admin());

create policy signups_platform on tenant_signups for all to mytrakin_api
  using (is_platform_admin()) with check (is_platform_admin());
create policy signups_public_insert on tenant_signups for insert to mytrakin_api
  with check (ctx_role() = 'public' and status = 'pending');

create policy platform_admins_self on platform_admins for select to mytrakin_api
  using (user_id = ctx_user() or is_platform_admin());

-- People ----------------------------------------------------------------------
create policy profiles_read on profiles for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));
create policy profiles_self on profiles for update to mytrakin_api
  using (id = ctx_user()) with check (id = ctx_user());

create policy memberships_read on memberships for select to mytrakin_api
  using (is_internal() or user_id = ctx_user());
create policy memberships_admin on memberships for all to mytrakin_api
  using (can('tenant_admin')) with check (can('tenant_admin'));

create policy counters_all on counters for all to mytrakin_api using (true) with check (true);

-- Companies ---------------------------------------------------------------------
create policy companies_internal on companies for select to mytrakin_api using (is_internal());
create policy companies_own on companies for select to mytrakin_api
  using (ctx_role() in ('vendor_admin', 'client_user') and id = ctx_company());
create policy companies_consultant on companies for select to mytrakin_api
  using (ctx_role() = 'consultant' and (
         exists (select 1 from consultants c where c.id = ctx_consultant() and c.employer_company_id = companies.id)
      or exists (select 1 from placements p where p.consultant_id = ctx_consultant()
                  and companies.id in (p.ar_company_id, p.end_client_company_id, p.ap_company_id))));
create policy companies_write on companies for all to mytrakin_api
  using (can('account_manager', 'finance', 'legal')) with check (can('account_manager', 'finance', 'legal'));

-- Consultants -------------------------------------------------------------------
create policy consultants_internal on consultants for select to mytrakin_api using (is_internal());
create policy consultants_vendor on consultants for select to mytrakin_api
  using (ctx_role() = 'vendor_admin' and employer_company_id = ctx_company());
create policy consultants_self on consultants for select to mytrakin_api
  using (ctx_role() = 'consultant' and id = ctx_consultant());
create policy consultants_write on consultants for all to mytrakin_api
  using (can('hr', 'account_manager', 'legal')) with check (can('hr', 'account_manager', 'legal'));

-- Agreements, SOWs, amendments ------------------------------------------------------
create policy agreements_internal on agreements for select to mytrakin_api using (is_internal());
create policy agreements_party on agreements for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user') and company_id = ctx_company())
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy agreements_write on agreements for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));

create policy sows_internal on sows for select to mytrakin_api using (is_internal());
create policy sows_party on sows for select to mytrakin_api
  using ((ctx_role() in ('vendor_admin', 'client_user') and company_id = ctx_company())
      or (ctx_role() = 'consultant' and exists (
            select 1 from placements p where p.consultant_id = ctx_consultant() and sows.id in (p.ar_sow_id, p.ap_sow_id))));
create policy sows_write on sows for all to mytrakin_api
  using (can('legal', 'account_manager')) with check (can('legal', 'account_manager'));

create policy amendments_read on sow_amendments for select to mytrakin_api
  using (is_internal() or exists (select 1 from sows s where s.id = sow_amendments.sow_id));
create policy amendments_write on sow_amendments for all to mytrakin_api
  using (can('legal', 'account_manager')) with check (can('legal', 'account_manager'));

-- Projects and placements -------------------------------------------------------------
create policy projects_internal on projects for select to mytrakin_api using (is_internal());
create policy projects_party on projects for select to mytrakin_api
  using ((ctx_role() = 'consultant' and exists (select 1 from placements p where p.project_id = projects.id and p.consultant_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and exists (select 1 from placements p where p.project_id = projects.id and p.ap_company_id = ctx_company()))
      or (ctx_role() = 'client_user' and ctx_company() in (client_company_id, prime_company_id)));
create policy projects_write on projects for all to mytrakin_api
  using (can('account_manager')) with check (can('account_manager'));

create policy placements_internal on placements for select to mytrakin_api using (is_internal());
create policy placements_party on placements for select to mytrakin_api
  using ((ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and ap_company_id = ctx_company())
      or (ctx_role() = 'client_user' and ar_company_id = ctx_company()));
create policy placements_write on placements for all to mytrakin_api
  using (can('account_manager', 'finance')) with check (can('account_manager', 'finance'));

-- Timesheets ----------------------------------------------------------------------
create policy timesheets_internal on timesheets for select to mytrakin_api using (is_internal());
create policy timesheets_party on timesheets for select to mytrakin_api
  using ((ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and exists (
            select 1 from consultants c where c.id = timesheets.consultant_id and c.employer_company_id = ctx_company())));
create policy timesheets_consultant_insert on timesheets for insert to mytrakin_api
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'submitted'));
create policy timesheets_consultant_update on timesheets for update to mytrakin_api
  using (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'rejected'))
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status in ('draft', 'submitted'));
create policy timesheets_staff_write on timesheets for all to mytrakin_api
  using (can('approver', 'account_manager', 'hr', 'finance')) with check (can('approver', 'account_manager', 'hr', 'finance'));

create policy entries_read on timesheet_entries for select to mytrakin_api
  using (exists (select 1 from timesheets t where t.id = timesheet_entries.timesheet_id));
create policy entries_consultant_write on timesheet_entries for all to mytrakin_api
  using (ctx_role() = 'consultant' and exists (
           select 1 from timesheets t where t.id = timesheet_entries.timesheet_id
              and t.consultant_id = ctx_consultant() and t.status in ('draft', 'rejected')))
  with check (ctx_role() = 'consultant' and exists (
           select 1 from timesheets t where t.id = timesheet_entries.timesheet_id
              and t.consultant_id = ctx_consultant() and t.status in ('draft', 'rejected')));
create policy entries_staff_write on timesheet_entries for all to mytrakin_api
  using (can('approver', 'account_manager', 'hr', 'finance')) with check (can('approver', 'account_manager', 'hr', 'finance'));

-- Money -----------------------------------------------------------------------------
create policy invoices_internal on invoices for select to mytrakin_api using (is_internal());
create policy invoices_party on invoices for select to mytrakin_api
  using ((ctx_role() = 'vendor_admin' and direction = 'ap' and company_id = ctx_company())
      or (ctx_role() = 'client_user' and direction = 'ar' and company_id = ctx_company())
      or (ctx_role() = 'consultant' and (consultant_id = ctx_consultant()
            or exists (select 1 from placements p where p.id = invoices.placement_id and p.consultant_id = ctx_consultant()))));
create policy invoices_finance on invoices for all to mytrakin_api
  using (can('finance')) with check (can('finance'));
create policy invoices_vendor_submit on invoices for insert to mytrakin_api
  with check (ctx_role() = 'vendor_admin' and direction = 'ap' and company_id = ctx_company() and status = 'received');

create policy payments_read on payments for select to mytrakin_api
  using (is_internal() or exists (select 1 from invoices i where i.id = payments.invoice_id));
create policy payments_finance on payments for all to mytrakin_api
  using (can('finance')) with check (can('finance'));

create policy notes_read on collection_notes for select to mytrakin_api using (is_internal());
create policy notes_write on collection_notes for insert to mytrakin_api with check (can('finance', 'account_manager'));

create policy expenses_read on expenses for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy expenses_submit on expenses for insert to mytrakin_api
  with check ((ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status = 'submitted') or can('finance', 'hr'));
create policy expenses_decide on expenses for update to mytrakin_api
  using (can('finance', 'hr', 'approver')) with check (can('finance', 'hr', 'approver'));

create policy time_off_read on time_off for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy time_off_request on time_off for insert to mytrakin_api
  with check ((ctx_role() = 'consultant' and consultant_id = ctx_consultant() and status = 'requested') or can('hr', 'approver'));
create policy time_off_decide on time_off for update to mytrakin_api
  using (can('hr', 'approver', 'account_manager')) with check (can('hr', 'approver', 'account_manager'));

create policy payroll_finance on payroll_lines for all to mytrakin_api using (can('finance')) with check (can('finance'));
create policy referrals_finance on referral_agreements for all to mytrakin_api using (can('finance', 'hr')) with check (can('finance', 'hr'));
create policy referral_payments_finance on referral_payments for all to mytrakin_api using (can('finance')) with check (can('finance'));

-- Documents and compliance ---------------------------------------------------------------
-- (Soft-deleted rows stay readable to RLS so the delete itself can be written; queries filter deleted_at.)
create policy documents_read on documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())));
create policy documents_upload on documents for insert to mytrakin_api
  with check (is_internal()
      or (ctx_role() = 'consultant' and owner_type in ('consultant', 'expense') and (owner_type = 'expense' or owner_id = ctx_consultant()))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (ctx_role() = 'public' and owner_type = 'registration'));
create policy documents_manage on documents for update to mytrakin_api
  using (uploaded_by = ctx_user() or can('hr', 'legal', 'finance'))
  with check (uploaded_by = ctx_user() or can('hr', 'legal', 'finance'));

create policy tracked_read on tracked_documents for select to mytrakin_api
  using (is_internal()
      or (ctx_role() = 'consultant' and consultant_id = ctx_consultant())
      or (ctx_role() = 'vendor_admin' and (company_id = ctx_company() or exists (
            select 1 from consultants c where c.id = tracked_documents.consultant_id and c.employer_company_id = ctx_company()))));
create policy tracked_write on tracked_documents for all to mytrakin_api
  using (can('hr', 'legal')) with check (can('hr', 'legal'));

create policy policies_read on policies for select to mytrakin_api using (ctx_role() not in ('anonymous', 'public', 'signer'));
create policy policies_write on policies for all to mytrakin_api using (can('hr', 'legal')) with check (can('hr', 'legal'));

create policy acceptances_read on policy_acceptances for select to mytrakin_api
  using (is_internal() or (ctx_role() = 'consultant' and consultant_id = ctx_consultant()));
create policy acceptances_accept on policy_acceptances for insert to mytrakin_api
  with check (ctx_role() = 'consultant' and consultant_id = ctx_consultant());

create policy registrations_staff on registrations for all to mytrakin_api
  using (can('legal', 'hr', 'account_manager')) with check (can('legal', 'hr', 'account_manager'));
create policy registrations_public on registrations for insert to mytrakin_api
  with check (ctx_role() = 'public' and status = 'pending');

-- E-signatures ------------------------------------------------------------------------
create or replace function signer_envelope() returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select envelope_id from envelope_signers where id = ctx_signer()
$$;
grant execute on function signer_envelope() to mytrakin_api;

create policy envelopes_internal on envelopes for select to mytrakin_api using (is_internal());
-- Envelopes and their signers refer to each other, so the party rule lives in one
-- SECURITY DEFINER function (policies that query each other would recurse).
create or replace function envelope_visible(p_envelope uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from envelopes e
     where e.id = p_envelope and e.tenant_id = ctx_tenant()
       and (is_internal()
         or (ctx_role() = 'consultant' and e.consultant_id = ctx_consultant())
         or (ctx_role() in ('vendor_admin', 'client_user')
             and exists (select 1 from envelope_signers s where s.envelope_id = e.id and s.company_id = ctx_company()))
         or (ctx_role() = 'signer' and e.id = signer_envelope())))
$$;
grant execute on function envelope_visible(uuid) to mytrakin_api;

create policy envelopes_party on envelopes for select to mytrakin_api using (envelope_visible(id));
create policy envelopes_write on envelopes for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));
create policy envelopes_signer_complete on envelopes for update to mytrakin_api
  using (ctx_role() = 'signer' and id = signer_envelope()) with check (ctx_role() = 'signer' and id = signer_envelope());

create policy signers_read on envelope_signers for select to mytrakin_api
  using (is_internal() or envelope_visible(envelope_id));
create policy signers_write on envelope_signers for all to mytrakin_api
  using (can('legal', 'account_manager', 'finance', 'hr')) with check (can('legal', 'account_manager', 'finance', 'hr'));
create policy signers_signer_update on envelope_signers for update to mytrakin_api
  using (ctx_role() = 'signer' and envelope_id = signer_envelope())
  with check (ctx_role() = 'signer' and envelope_id = signer_envelope());

create policy sigevents_read on signature_events for select to mytrakin_api
  using (is_internal() or envelope_visible(envelope_id));
create policy sigevents_insert on signature_events for insert to mytrakin_api
  with check (can('legal', 'account_manager', 'finance', 'hr')
      or (ctx_role() = 'signer' and envelope_id = signer_envelope()));

-- Reminders, notifications, imports, audit ---------------------------------------------------
create policy reminder_rules_read on reminder_rules for select to mytrakin_api using (is_internal());
create policy reminder_rules_admin on reminder_rules for all to mytrakin_api using (can('tenant_admin')) with check (can('tenant_admin'));

create policy notifications_read on notifications for select to mytrakin_api using (is_internal());
-- Notifications are written only through log_notification() / mark_notification().

create policy imports_rw on import_jobs for all to mytrakin_api
  using (can('finance', 'hr', 'legal')) with check (can('finance', 'hr', 'legal'));

create policy audit_read on audit_log for select to mytrakin_api using (can('legal', 'finance'));

-- Network (cross-tenant, scoped to the person) ------------------------------------------------
create policy connections_mine on connections for select to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id));
create policy connections_request on connections for insert to mytrakin_api
  with check (requester_id = ctx_user());
create policy connections_respond on connections for update to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id)) with check (ctx_user() in (requester_id, addressee_id));
create policy connections_remove on connections for delete to mytrakin_api
  using (ctx_user() in (requester_id, addressee_id));

create policy posts_read on posts for select to mytrakin_api
  using (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()));
create policy posts_write on posts for insert to mytrakin_api with check (author_id = ctx_user());
create policy posts_own on posts for delete to mytrakin_api using (author_id = ctx_user());
create policy posts_like on posts for update to mytrakin_api
  using (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()))
  with check (ctx_user() is not null and (tenant_id is null or tenant_id = ctx_tenant()));

create policy messages_mine on messages for select to mytrakin_api using (ctx_user() in (sender_id, recipient_id));
create policy messages_send on messages for insert to mytrakin_api with check (sender_id = ctx_user());
create policy messages_read_receipt on messages for update to mytrakin_api
  using (recipient_id = ctx_user()) with check (recipient_id = ctx_user());

grant select on invoice_balances, sow_burn to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Cross-tenant helpers. SECURITY DEFINER, so each checks the caller itself.
-- -----------------------------------------------------------------------------

-- Platform console: usage per tenant (seats are billable active users).
create or replace function platform_tenant_stats()
returns table (tenant_id uuid, active_users bigint, invited_users bigint, consultants bigint, active_placements bigint,
               last_user_activity timestamptz)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id,
         (select count(*) from memberships m where m.tenant_id = t.id and m.status = 'active'),
         (select count(*) from memberships m where m.tenant_id = t.id and m.status = 'invited'),
         (select count(*) from consultants c where c.tenant_id = t.id and c.status <> 'former'),
         (select count(*) from placements p where p.tenant_id = t.id and p.status in ('active', 'ending')),
         (select max(m.last_active_at) from memberships m where m.tenant_id = t.id)
    from tenants t
   where is_platform_admin()
$$;

-- Network: may the caller see this person's profile? 'network' = anyone signed in;
-- 'company' = people who share a workspace; 'company_and_connections' adds accepted connections.
create or replace function visible_profile(p_profile uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select ctx_user() is not null and (
         p_profile = ctx_user()
      or exists (select 1 from profiles p where p.id = p_profile and p.visibility = 'network')
      or exists (select 1 from memberships a join memberships b on b.tenant_id = a.tenant_id
                  where a.user_id = ctx_user() and b.user_id = p_profile and a.status = 'active' and b.status = 'active')
      or exists (select 1 from profiles p join connections c
                   on c.status = 'accepted' and ((c.requester_id = ctx_user() and c.addressee_id = p.id)
                                              or (c.addressee_id = ctx_user() and c.requester_id = p.id))
                  where p.id = p_profile and p.visibility = 'company_and_connections'))
$$;

-- Workspaces two people share (shown on profiles as "Also at ...").
create or replace function shared_workspaces(p_profile uuid) returns setof text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.name from memberships a join memberships b on b.tenant_id = a.tenant_id join tenants t on t.id = a.tenant_id
   where a.user_id = ctx_user() and b.user_id = p_profile and a.status = 'active' and b.status = 'active'
$$;

revoke all on function platform_tenant_stats(), visible_profile(uuid), shared_workspaces(uuid) from public;
grant execute on function platform_tenant_stats(), visible_profile(uuid), shared_workspaces(uuid) to mytrakin_api;
