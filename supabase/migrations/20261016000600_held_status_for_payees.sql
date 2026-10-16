-- =============================================================================
-- myTrakIn · 20261016 0600 · Pay-when-paid "held" status for vendors and 1099 payees
--
--   invoice_balances runs with the caller's rights (security_invoker). A vendor admin can't
--   read the client (AR) invoice an AP invoice waits for, so the "is the client invoice still
--   unpaid?" check found nothing and a held invoice showed the vendor "ready to pay".
--   client_invoice_unpaid() answers only that yes/no question (same tenant only), so the
--   payee sees "held" correctly while every AR amount stays hidden (RULE-01 / masking).
--   The view is otherwise unchanged.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.client_invoice_unpaid(p_invoice uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from invoices ar
     where ar.id = p_invoice and ar.tenant_id = ctx_tenant() and ar.direction = 'ar'
       and ar.amount - coalesce((select sum(p.amount) from payments p
                                  where p.invoice_id = ar.id and p.status in ('completed', 'confirmed')), 0) > 0)
$$;

revoke all on function mytrakin.client_invoice_unpaid(uuid) from public;
grant execute on function mytrakin.client_invoice_unpaid(uuid) to mytrakin_api;

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
         and mytrakin.client_invoice_unpaid(i.pay_when_paid_of)
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
