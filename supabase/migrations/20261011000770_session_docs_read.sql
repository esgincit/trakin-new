-- =============================================================================
-- myTrakIn · 0770 · Session documents are readable by their uploader
--
-- INSERT ... RETURNING checks SELECT policies too. The 0730 uploader clause let
-- creators store session files (W-9/MOA) but nothing let them read the row back,
-- so uploads 403'd for non-staff. Staff already see everything via is_internal().
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists documents_read on mytrakin.documents;
create policy documents_read on mytrakin.documents for select to mytrakin_api
  using ((
         is_internal()
      or (ctx_role() = 'consultant' and ((owner_type = 'consultant' and owner_id = ctx_consultant()) or owner_type = 'policy'))
      or (ctx_role() = 'vendor_admin' and owner_type = 'company' and owner_id = ctx_company())
      or (owner_type = 'company' and mytrakin.company_role(owner_id) is not null)
      or (owner_type = 'session' and exists (select 1 from mytrakin.onboarding_sessions s
                                             where s.id = owner_id and s.created_by = mytrakin.ctx_user()))));
