-- =============================================================================
-- myTrakIn · 20261018 0100 · Credit notes against client invoices (PLAN AR-06, TS-07)
--
--   A credit note lowers what the customer owes on one AR invoice (billing error, holiday
--   hours at the regular rate, a correction after an approved timesheet changes). It is
--   never more than the invoice's open balance. invoice_balances now subtracts credits, so
--   aging, dashboards, payment caps and pay-when-paid release all follow automatically.
--   Status is derived: "open" while the invoice still has a balance, "applied" once settled.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create table if not exists mytrakin.credit_notes (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references mytrakin.tenants (id) on delete cascade,
  number      text not null,
  invoice_id  uuid not null references mytrakin.invoices (id) on delete cascade,
  issued_on   date not null default current_date,
  reason      text not null,
  amount      numeric(14, 2) not null check (amount > 0),
  created_by  uuid,
  created_at  timestamptz not null default now(),
  unique (tenant_id, number)
);
create index if not exists credit_notes_invoice_idx on mytrakin.credit_notes (invoice_id);

grant select, insert on mytrakin.credit_notes to mytrakin_api;
alter table mytrakin.credit_notes enable row level security;
drop policy if exists tenant_isolation on mytrakin.credit_notes;
create policy tenant_isolation on mytrakin.credit_notes as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
-- Staff, and the customer the invoice is billed to (AR money is never shown to vendors or consultants).
drop policy if exists credit_notes_read on mytrakin.credit_notes;
create policy credit_notes_read on mytrakin.credit_notes for select to mytrakin_api
  using (mytrakin.is_internal() or (mytrakin.ctx_role() = 'client_user' and exists (
           select 1 from mytrakin.invoices i where i.id = credit_notes.invoice_id and i.company_id = mytrakin.ctx_company())));
drop policy if exists credit_notes_write on mytrakin.credit_notes;
create policy credit_notes_write on mytrakin.credit_notes for insert to mytrakin_api with check (mytrakin.can('finance'));

drop trigger if exists credit_notes_audit on mytrakin.credit_notes;
create trigger credit_notes_audit after insert or update or delete on mytrakin.credit_notes
  for each row execute function mytrakin.audit_row();

-- Pay-when-paid: a client invoice settled by payments plus credits releases the vendor invoice.
create or replace function mytrakin.client_invoice_unpaid(p_invoice uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from invoices ar
     where ar.id = p_invoice and ar.tenant_id = ctx_tenant() and ar.direction = 'ar'
       and ar.amount - coalesce((select sum(p.amount) from payments p
                                  where p.invoice_id = ar.id and p.status in ('completed', 'confirmed')), 0)
                     - coalesce((select sum(c.amount) from credit_notes c where c.invoice_id = ar.id), 0) > 0)
$$;

-- Same view as 20261016000600 with credits subtracted from the balance; "credited" is appended last.
create or replace view mytrakin.invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                                             as paid,
  i.amount - coalesce(p.paid, 0) - coalesce(c.credited, 0)        as balance,
  greatest(0, current_date - i.due_on)                            as days_late,
  case
    when i.status = 'void'                                                         then 'void'
    when i.amount - coalesce(p.paid, 0) - coalesce(c.credited, 0) <= 0             then 'paid'
    when i.status = 'exception'                                                    then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and mytrakin.client_invoice_unpaid(i.pay_when_paid_of)                    then 'held'
    when i.status = 'scheduled'                                                    then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0                       then 'overdue_part_paid'
    when i.due_on < current_date                                                   then 'overdue'
    when coalesce(p.paid, 0) > 0                                                   then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null                     then 'ready_to_pay'
    else 'open'
  end                                                             as live_status,
  coalesce(c.credited, 0)                                         as credited
from mytrakin.invoices i
left join (select invoice_id, sum(amount) as paid from mytrakin.payments
            where status in ('completed', 'confirmed') group by invoice_id) p on p.invoice_id = i.id
left join (select invoice_id, sum(amount) as credited from mytrakin.credit_notes group by invoice_id) c on c.invoice_id = i.id;
