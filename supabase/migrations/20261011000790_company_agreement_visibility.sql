-- =============================================================================
-- myTrakIn · 0790 · Company-side agreement visibility + NDA gate that can see
--
-- A company member (owner/admin/member/vendor) must see agreements their company
-- is party to — on either side of the link — and the Verify → NDA → MSA gate
-- must be able to check for an NDA without reading the whole row (RLS would hide
-- counterparties' agreements from the check itself).
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop policy if exists agreements_member on mytrakin.agreements;
create policy agreements_member on mytrakin.agreements for select to mytrakin_api
  using (mytrakin.company_role(company_id) is not null
      or (initiator_company_id is not null and mytrakin.company_role(initiator_company_id) is not null));

create or replace function mytrakin.has_company_agreement(p_tenant uuid, p_kinds text[], p_company uuid, p_on date default current_date)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from mytrakin.agreements
                  where tenant_id = p_tenant and kind = any (p_kinds) and company_id = p_company
                    and status = 'active'
                    and coalesce(effective_on, p_on) <= p_on and coalesce(expires_on, p_on) >= p_on)
$$;
grant execute on function mytrakin.has_company_agreement(uuid, text[], uuid, date) to mytrakin_api;
