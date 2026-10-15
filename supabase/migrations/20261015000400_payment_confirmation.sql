-- =============================================================================
-- myTrakIn · 20261015 0400 · Payment status and payment confirmation (PLAN WF-09)
--
--   Invoice → Payment → Payment confirmation. A payment moves pending → processing →
--   completed (money moved) → confirmed (the receiving side confirmed it arrived), which
--   closes the financial lifecycle. Existing payments were recorded as done: completed.
--   Only completed / confirmed payments reduce an invoice's balance.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.payments
  add column if not exists status text not null default 'completed'
    check (status in ('pending', 'processing', 'completed', 'confirmed')),
  add column if not exists confirmed_by uuid,
  add column if not exists confirmed_by_name text,
  add column if not exists confirmed_at timestamptz;

-- Same columns as before; payments still in flight don't count yet.
create or replace view mytrakin.invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                              as paid,
  i.amount - coalesce(p.paid, 0)                   as balance,
  greatest(0, current_date - i.due_on)             as days_late,
  case
    when i.status = 'void'                                      then 'void'
    when i.amount - coalesce(p.paid, 0) <= 0                     then 'paid'
    when i.status = 'exception'                                  then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and exists (select 1 from mytrakin.invoices ar
                      left join (select invoice_id, sum(amount) s from mytrakin.payments
                                  where status in ('completed', 'confirmed') group by invoice_id) arp on arp.invoice_id = ar.id
                      where ar.id = i.pay_when_paid_of and ar.amount - coalesce(arp.s, 0) > 0)
                                                                 then 'held'
    when i.status = 'scheduled'                                  then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0     then 'overdue_part_paid'
    when i.due_on < current_date                                 then 'overdue'
    when coalesce(p.paid, 0) > 0                                 then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null   then 'ready_to_pay'
    else 'open'
  end                                              as live_status
from mytrakin.invoices i
left join (select invoice_id, sum(amount) as paid from mytrakin.payments
            where status in ('completed', 'confirmed') group by invoice_id) p on p.invoice_id = i.id;

-- The payee (vendor admin, or the 1099 contractor) confirms a payment made to them.
drop policy if exists payments_payee_confirm on mytrakin.payments;
create policy payments_payee_confirm on mytrakin.payments for update to mytrakin_api
  using (exists (select 1 from mytrakin.invoices i where i.id = payments.invoice_id and i.direction = 'ap'
                  and ((mytrakin.ctx_role() = 'vendor_admin' and i.company_id = mytrakin.ctx_company())
                    or (mytrakin.ctx_role() = 'consultant' and i.consultant_id = mytrakin.ctx_consultant()))))
  with check (status = 'confirmed');
