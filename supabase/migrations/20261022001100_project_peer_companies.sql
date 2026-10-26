-- =============================================================================
-- myTrakIn · 20261022001100 · Consistent counterparties for the New-project form
--
--   The New project form's Client / Prime vendor options list the companies we
--   have an MSA in force with. That used a plain query over agreements, whose
--   row-level visibility differs by role — so different authorised users saw
--   different options (the end client missing for some). These are only company
--   names, nothing sensitive: publish them to every workspace member through a
--   SECURITY DEFINER helper so the form is the same for everyone.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.project_peer_companies()
returns table (id uuid, name text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select x.id, mytrakin.company_public_name(x.id)
    from (select a.company_id as id from mytrakin.agreements a
            where a.tenant_id = mytrakin.ctx_tenant() and a.status in ('active', 'accepted')
              and a.kind = any (array['msa', 'subcontract'])
          union
          select mytrakin.agreement_peer_company(s.id) from mytrakin.shared_agreements() s
           where s.status in ('active', 'accepted') and s.kind = any (array['msa', 'subcontract'])) x
   where x.id is not null
     and not x.id = any (mytrakin.my_company_ids())
     and mytrakin.company_public_name(x.id) is not null
$$;

revoke all on function mytrakin.project_peer_companies() from public;
grant execute on function mytrakin.project_peer_companies() to mytrakin_api;
