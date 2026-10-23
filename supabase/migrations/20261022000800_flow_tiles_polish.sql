-- =============================================================================
-- myTrakIn · 20261022000800 · Payment-flow tile polish
--   The end client's mirrored flow card: a 'sent' invoice reads as 'open'
--   (AP-style display), and self-billed placements never appear.
-- =============================================================================

set search_path = mytrakin, public, extensions;

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
           when i.status in ('draft', 'sent')                           then 'open'
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
     and (not p_open or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;
revoke all on function mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.client_payable_flow(boolean) to mytrakin_api;
