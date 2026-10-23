-- =============================================================================
-- myTrakIn · 20261022000600 · The end client sees what it is being invoiced
--
--   A client invoice the placing company (B) issues to its end client (A) lives
--   only in B's workspace (RULE-01). A's workspace therefore showed nothing in
--   its AP / payment-flow views. These SECURITY DEFINER helpers expose exactly
--   the rows where A is the billed company (i.company_id in the companies the
--   caller acts for) from OTHER workspaces — money A is party to:
--     * client_payables()        — AP-list shaped rows for the Invoices page
--     * client_payable_flow(p_open) — payment-flow shaped rows (what A owes B)
--   Statuses are recomputed inline (the invoice_balances view is security_invoker
--   and its own RLS would hide the placing workspace's rows here).
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.client_payables()
returns table (
  id uuid, number text, tenant_id uuid, placed_by text,
  consultant text, project text, sow text,
  period_start date, period_end date, hours numeric, amount numeric,
  paid numeric, balance numeric, due_on date, terms text, issued_on date,
  status text, live_status text, engagement text, is_client_payable boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select i.id, i.number, i.tenant_id, tn.name,
         c.full_name, pr.name, s.code,
         i.period_start, i.period_end, i.hours, i.amount,
         coalesce(pm.paid, 0), i.amount - coalesce(pm.paid, 0), i.due_on, i.terms, i.issued_on,
         i.status,
         case
           when i.amount - coalesce(pm.paid, 0) <= 0                    then 'paid'
           when i.status = 'void'                                       then 'void'
           when i.status = 'exception'                                  then 'exception'
           when i.status = 'scheduled'                                  then 'scheduled'
           when i.due_on < current_date and coalesce(pm.paid, 0) > 0    then 'overdue_part_paid'
           when i.due_on < current_date                                 then 'overdue'
           when coalesce(pm.paid, 0) > 0                                then 'part_paid'
           when i.status = 'sent'                                       then 'open'
           else i.status
         end,
         c.engagement,
         true
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    left join mytrakin.sows s on s.id = i.sow_id
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
   order by i.period_start desc, c.full_name
$$;

create or replace function mytrakin.client_payable_flow(p_open boolean default true)
returns table (
  flow_key text, consultant text, project text,
  period_start date, period_end date, hours numeric, engagement text,
  payee text, ap_id uuid, ap_number text, ap_amount numeric, ap_due date,
  ap_status text, ap_balance numeric, is_client_flow boolean)
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
         i.amount - coalesce(pm.paid, 0), true
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join mytrakin.tenants tn on tn.id = i.tenant_id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
   where i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and (not coalesce(p_open, true) or i.amount - coalesce(pm.paid, 0) > 0)
   order by i.period_start desc, c.full_name
$$;

revoke all on function mytrakin.client_payables(), mytrakin.client_payable_flow(boolean) from public;
grant execute on function mytrakin.client_payables(), mytrakin.client_payable_flow(boolean) to mytrakin_api;
