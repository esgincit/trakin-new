-- =============================================================================
-- myTrakIn · 20261031 0600 · Shared SOWs carry their project
--
--   The placement form lists our own SOWs plus SOWs other workspaces sent us
--   (shared_sows). Those incoming rows had no project, so the "AR SOW / work
--   order" picker read "CON-… · company" with nothing to tell apart two
--   contracts with the same company. The project code and name are now part of
--   the same SECURITY DEFINER result.
-- =============================================================================

set search_path = mytrakin, public, extensions;

drop function if exists mytrakin.shared_sows();

create function mytrakin.shared_sows()
returns table(id uuid, code text, title text, side text, status text,
              start_date date, end_date date, agreement_code text, agreement_id uuid,
              counterparty text, sent_by text, sent_on timestamp with time zone,
              decided_on timestamp with time zone, decision_note text, shared boolean,
              project_id uuid, project_code text, project_name text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with mine as (select mytrakin.my_company_ids() as ids)
  select s.id, s.code, s.title,
         case when s.side = 'we_bill' then 'we_pay' else 'we_bill' end,
         s.status, s.start_date, s.end_date,
         a.code, a.id,
         -- the other company on the MSA, from where the reader stands
         case when a.company_id = any (m.ids) then sc.name else rc.name end,
         coalesce(s_t.name, sc.name),
         s.sent_on, s.decided_on, s.decision_note, true,
         s.project_id, pj.code, pj.name
    from mytrakin.sows s
    join mytrakin.agreements a on a.id = s.agreement_id
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    join mytrakin.tenants s_t on s_t.id = s.tenant_id
    left join mytrakin.projects pj on pj.id = s.project_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
   where s.tenant_id is distinct from mytrakin.ctx_tenant()
     and s.status <> 'draft'
     and exists (select 1 from mytrakin.companies mine_c
                  where mine_c.id = any (m.ids)
                    and (mine_c.id = a.company_id or mine_c.id = coalesce(a.initiator_company_id, t.company_id)))
$$;
revoke all on function mytrakin.shared_sows() from public;
grant execute on function mytrakin.shared_sows() to mytrakin_api;
