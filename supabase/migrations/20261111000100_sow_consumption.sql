-- =============================================================================
-- myTrakIn · 20261111 0100 · One assignment per SOW (consumption) (T011303-1128)
--
-- An SOW / work order is a slot for exactly one engagement. Once it has been
-- assigned — placed on a consultant, or flowed down to a downstream company's
-- SOW — it is consumed and must stop appearing as an available option:
--
--   * Add SOW → "Supports client SOW (vendor SOWs)" lists only unconsumed SOWs
--   * Placement AR / AP SOW pickers list only unconsumed SOWs
--   * Every picker reads "CODE · Project · Role" so multi-SOW projects are clear
--
-- The backend computes consumption per workspace from placements (ar_sow_id /
-- ap_sow_id) and downstream SOWs (flows_from_sow_id). For SOWs another
-- workspace sent us, shared_sows() now also exposes that SOW's project so the
-- picker can name it (names only — money stays in the owner's workspace).
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.shared_sows()
returns table (
  id uuid, code text, title text, side text, status text, start_date date, end_date date,
  agreement_code text, agreement_id uuid, counterparty text, sent_by text,
  sent_on timestamptz, decided_on timestamptz, decision_note text, shared boolean,
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
         p.id, p.code, p.name
    from mytrakin.sows s
    join mytrakin.agreements a on a.id = s.agreement_id
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    join mytrakin.tenants s_t on s_t.id = s.tenant_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
    left join mytrakin.projects p on p.id = s.project_id
   where s.tenant_id is distinct from mytrakin.ctx_tenant()
     and s.status <> 'draft'
     and exists (select 1 from mytrakin.companies mine_c
                  where mine_c.id = any (m.ids)
                    and (mine_c.id = a.company_id or mine_c.id = coalesce(a.initiator_company_id, t.company_id)))
$$;

revoke all on function mytrakin.shared_sows() from public;
grant execute on function mytrakin.shared_sows() to mytrakin_api;
