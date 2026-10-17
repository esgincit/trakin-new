-- =============================================================================
-- myTrakIn · 20261016 1200 · Agreements shared with the company they are with
--
--   An MSA is recorded in the sender's workspace. Until now only that workspace
--   could read it (tenant isolation), so the counterparty company never saw it.
--   These functions let a company's workspace read — and only read — the
--   agreements where its company is a party, and the files attached to them.
--
--   - my_company_ids():           companies the signed-in user acts for (their
--                                 workspace's company, their company membership)
--   - shared_agreements():        agreements of OTHER workspaces where one of those
--                                 companies is the counterparty or the sender.
--                                 Shown from the counterparty's side (supplier and
--                                 buyer swapped). No money: agreements carry no rates.
--   - shared_agreement_files():   files attached to a shared agreement
--   - shared_document():          one such file, for download
--
--   Nothing here lets a counterparty edit, sign for the sender, or see SOWs,
--   invoices or payments of the sender.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.my_company_ids() returns uuid[]
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(array_agg(distinct s.cid) filter (where s.cid is not null), '{}'::uuid[])
    from (
      select t.company_id as cid from mytrakin.tenants t where t.id = mytrakin.ctx_tenant()
      union all
      select mytrakin.ctx_company()
      union all
      select cm.company_id from mytrakin.company_members cm
       where cm.user_id = mytrakin.ctx_user() and cm.status = 'active'
    ) s
$$;

create or replace function mytrakin.shared_agreements()
returns table (
  id uuid, tenant_id uuid, code text, kind text, company_id uuid, initiator_company_id uuid,
  tenant_side text, effective_on date, expires_on date, payment_terms text, renewal text,
  notice_period text, insurance_required text, status text, signed_by text, source text,
  created_at timestamptz, counterparty text, sent_by_company text, shared boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with mine as (select mytrakin.my_company_ids() as ids)
  select a.id, a.tenant_id, a.code, a.kind, a.company_id, a.initiator_company_id,
         case when a.company_id = any (m.ids) and not coalesce(a.initiator_company_id = any (m.ids), false)
              then case a.tenant_side when 'supplier' then 'buyer' when 'buyer' then 'supplier' else a.tenant_side end
              else a.tenant_side end,
         a.effective_on, a.expires_on, a.payment_terms, a.renewal, a.notice_period, a.insurance_required,
         a.status, a.signed_by, a.source, a.created_at,
         case when a.company_id = any (m.ids) then sc.name else rc.name end,
         sc.name, true
    from mytrakin.agreements a
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
   where a.tenant_id is distinct from mytrakin.ctx_tenant()
     and (a.company_id = any (m.ids) or a.initiator_company_id = any (m.ids))
$$;

create or replace function mytrakin.shared_agreement_files(p_agreement uuid)
returns setof mytrakin.documents
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select d.* from mytrakin.documents d
   where d.owner_type = 'agreement' and d.owner_id = p_agreement and d.deleted_at is null
     and exists (select 1 from mytrakin.shared_agreements() s where s.id = p_agreement)
$$;

create or replace function mytrakin.shared_document(p_id uuid)
returns setof mytrakin.documents
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select d.* from mytrakin.documents d
   where d.id = p_id and d.owner_type = 'agreement' and d.deleted_at is null
     and exists (select 1 from mytrakin.shared_agreements() s where s.id = d.owner_id)
$$;

revoke all on function mytrakin.my_company_ids(), mytrakin.shared_agreements(),
  mytrakin.shared_agreement_files(uuid), mytrakin.shared_document(uuid) from public;
grant execute on function mytrakin.my_company_ids(), mytrakin.shared_agreements(),
  mytrakin.shared_agreement_files(uuid), mytrakin.shared_document(uuid) to mytrakin_api;
