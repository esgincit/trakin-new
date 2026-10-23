-- =============================================================================
-- myTrakIn · 20261022000700 · The payment-flow chain per logged-in company
--
--   A project assigned down the vendor chain keeps its source in
--   projects.source_project_id. Walking that chain (in other tenants, hidden by
--   RLS from a staff session) gives the end client (the root project's client)
--   and the assignment path "who placed us" ending with the caller's own
--   company. SECURITY DEFINER: every other layer's amounts stay private — this
--   only publishes company names.
--
--   Example: A(Profin) → B(Preview IT) → C(TCS) → D(South Cloud) → E(Twitter)
--     chain_of(D's project) = ('Profin AI Solutions', 'TCS → South Cloud ...')
--     chain_of(B's root)    = ('Profin AI Solutions', 'Preview IT')
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.chain_of(p_project uuid)
returns table (end_client text, placed_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with recursive w as (
       select pr.id, pr.prime_company_id, pr.source_project_id, pr.client_company_id, pr.tenant_id, 0 as depth
         from mytrakin.projects pr
        where pr.id = p_project
       union all
       select s.id, s.prime_company_id, s.source_project_id, s.client_company_id, s.tenant_id, w.depth + 1
         from mytrakin.projects s
         join w on s.id = w.source_project_id),
       root as (select tenant_id, client_company_id from w where depth = 0),
       own as (select coalesce(t.company_id, null::uuid) as cid from mytrakin.tenants t where t.id = (select root.tenant_id from root)),
       hops as (
         select x.depth, mytrakin.company_public_name(x.prime_company_id) as n
           from w x
          where x.prime_company_id is not null
            and x.source_project_id is not null
            and not exists (select 1 from mytrakin.companies co
                             where co.id = x.prime_company_id
                               and co.tenant_id = (select root.tenant_id from root))),
       dedup as (
          select n, lag(n) over (order by depth desc) as prev
            from hops),
       assigners as (
          select string_agg(n, ' → ') as chain
            from dedup
           where n is not null and n <> coalesce(prev, '__none__')),
       ownname as (select coalesce(mytrakin.company_public_name((select own.cid from own)), (select t.name from mytrakin.tenants t where t.id = (select root.tenant_id from root)), '') as own_name)
  select
    coalesce((select mytrakin.company_public_name(r.client_company_id) from w r where r.source_project_id is null limit 1), '') as end_client,
    coalesce(
      case
        when (select a.chain from assigners a) = '' then (select o.own_name from ownname o)
        when (select a.chain from assigners a) = (select o.own_name from ownname o) then (select o.own_name from ownname o)
        else (select a.chain from assigners a) || ' → ' || (select o.own_name from ownname o)
      end, (select o.own_name from ownname o)) as placed_by
$$;

-- Re-issue the payable flow with the chain columns for the end client's mirror.
drop function if exists mytrakin.client_payable_flow(boolean);
create or replace function mytrakin.client_payable_flow(p_open boolean default true)
returns table (
  flow_key text, consultant text, project text,
  period_start date, period_end date, hours numeric, engagement text,
  payee text, ap_id uuid, ap_number text, ap_amount numeric, ap_due date,
  ap_status text, ap_balance numeric, is_client_flow boolean,
  end_client text, placed_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (i.tenant_id::text || ':' || i.id::text), c.full_name, pr.name,
         i.period_start, i.period_end, i.hours, c.engagement,
         tn.name, i.id, i.number, i.amount, i.due_on,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status = 'draft'                                      then 'open'
           else i.status
         end,
         i.amount - coalesce(pm.paid, 0), true,
         ch.end_client, ch.placed_by
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    cross join lateral mytrakin.chain_of(p.project_id) ch
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and (not coalesce(p_open, true) or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;

revoke all on function mytrakin.chain_of(uuid), mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.chain_of(uuid), mytrakin.client_payable_flow(boolean) to mytrakin_api;
