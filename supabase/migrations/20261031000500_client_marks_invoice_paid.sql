-- =============================================================================
-- myTrakIn · 20261031 0500 · The billed client can mark an invoice paid
--
--   An invoice lives in the placing company's workspace; the company that has to
--   pay it (its client) sees it read-only under AP (client_payables()). The client
--   can now record the payment they made — in full or in part — from their own
--   workspace, and the placing company acknowledges it (the existing payment
--   confirmation flow on their side).
--
--   Both helpers are SECURITY DEFINER and only act for an invoice where the
--   caller's company is the billed customer and the invoice belongs to another
--   workspace, so nothing else is exposed.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.client_payable_detail(p_invoice uuid) returns json
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select json_build_object(
           'id', i.id, 'number', i.number, 'direction', 'ar',
           'period_start', i.period_start, 'period_end', i.period_end,
           'hours', i.hours, 'approved_hours', i.approved_hours, 'rate', i.rate,
           'amount', i.amount, 'paid', coalesce(pm.paid, 0), 'credited', coalesce(cn.credited, 0),
           'balance', i.amount - coalesce(pm.paid, 0) - coalesce(cn.credited, 0),
           'issued_on', i.issued_on, 'due_on', i.due_on, 'terms', i.terms,
           'days_late', greatest(0, current_date - i.due_on),
           'status', i.status,
           'live_status', case
               when i.amount - coalesce(pm.paid, 0) - coalesce(cn.credited, 0) <= 0 then 'paid'
               when i.status = 'exception' then 'exception'
               when i.status = 'scheduled' then 'scheduled'
               when i.due_on < current_date and coalesce(pm.paid, 0) > 0 then 'overdue_part_paid'
               when i.due_on < current_date then 'overdue'
               when coalesce(pm.paid, 0) > 0 then 'part_paid'
               else 'open' end,
           'party', tn.name, 'provider', tn.name, 'shared', true,
           'sow', s.code, 'consultant', c.full_name, 'project', pr.name,
           'payments', (select coalesce(json_agg(json_build_object(
                                  'id', pay.id, 'amount', pay.amount, 'paid_on', pay.paid_on,
                                  'method', pay.method, 'reference', pay.reference, 'status', pay.status,
                                  'confirmed_by_name', pay.confirmed_by_name, 'confirmed_at', pay.confirmed_at)
                                order by pay.paid_on, pay.created_at), '[]'::json)
                          from mytrakin.payments pay where pay.invoice_id = i.id),
           'credits', (select coalesce(json_agg(json_build_object(
                                 'id', cr.id, 'number', cr.number, 'issued_on', cr.issued_on,
                                 'amount', cr.amount, 'reason', cr.reason)
                               order by cr.issued_on, cr.number), '[]'::json)
                         from mytrakin.credit_notes cr where cr.invoice_id = i.id))
    from mytrakin.invoices i
    join mytrakin.tenants tn on tn.id = i.tenant_id
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join (select invoice_id, sum(amount) as credited from mytrakin.credit_notes
                group by invoice_id) cn on cn.invoice_id = i.id
    left join mytrakin.placements p on p.id = i.placement_id
    left join mytrakin.consultants c on c.id = p.consultant_id
    left join mytrakin.projects pr on pr.id = p.project_id
    left join mytrakin.sows s on s.id = i.sow_id
   where i.id = p_invoice
     and i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
$$;
revoke all on function mytrakin.client_payable_detail(uuid) from public;
grant execute on function mytrakin.client_payable_detail(uuid) to mytrakin_api;

-- The client records money it paid on an invoice of another workspace.
create or replace function mytrakin.client_record_payment(
    p_invoice uuid, p_amount numeric, p_paid_on date, p_method text,
    p_reference text, p_user uuid) returns json
language plpgsql volatile security definer set search_path = mytrakin, public, extensions as $$
declare
  inv record;
  pay_id uuid;
begin
  select i.id, i.number, i.tenant_id, i.direction, i.status, i.company_id,
         i.amount - coalesce(pm.paid, 0) - coalesce(cn.credited, 0) as open_balance
    into inv
    from mytrakin.invoices i
    left join (select invoice_id, sum(amount) as paid from mytrakin.payments
                where status in ('completed', 'confirmed') group by invoice_id) pm on pm.invoice_id = i.id
    left join (select invoice_id, sum(amount) as credited from mytrakin.credit_notes
                group by invoice_id) cn on cn.invoice_id = i.id
   where i.id = p_invoice;

  if inv.id is null or inv.direction <> 'ar' or inv.status = 'void' then
    return json_build_object('error', 'not_found');
  end if;
  if inv.tenant_id = mytrakin.ctx_tenant() or not (inv.company_id = any (mytrakin.ts_my_companies())) then
    return json_build_object('error', 'not_ours');
  end if;
  if p_paid_on is null or p_paid_on > current_date then
    return json_build_object('error', 'future_date');
  end if;
  if p_amount is null or p_amount <= 0 then
    return json_build_object('error', 'invalid_amount');
  end if;
  if p_amount > inv.open_balance + 0.005 then
    return json_build_object('error', 'over_balance', 'balance', inv.open_balance);
  end if;
  if coalesce(p_method, '') not in ('ACH', 'Wire', 'Check', 'Card', 'Other') then
    return json_build_object('error', 'invalid_method');
  end if;

  insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference, status, created_by)
  values (inv.tenant_id, p_invoice, p_amount, p_paid_on, p_method, nullif(btrim(coalesce(p_reference, '')), ''),
          'completed', p_user)
  returning id into pay_id;

  return json_build_object('ok', true, 'payment_id', pay_id, 'invoice_id', p_invoice,
                           'tenant_id', inv.tenant_id, 'number', inv.number,
                           'amount', p_amount, 'balance', inv.open_balance - p_amount);
end $$;
revoke all on function mytrakin.client_record_payment(uuid, numeric, date, text, text, uuid) from public;
grant execute on function mytrakin.client_record_payment(uuid, numeric, date, text, text, uuid) to mytrakin_api;

-- Who to tell on the placing side that money was recorded (their finance/admin team).
create or replace function mytrakin.client_payable_recipients(p_invoice uuid) returns table(email text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select distinct p.email
    from mytrakin.invoices i
    join mytrakin.memberships m on m.tenant_id = i.tenant_id and m.status = 'active'
                               and m.role in ('finance', 'account_manager', 'tenant_admin')
    join mytrakin.profiles p on p.id = m.user_id
   where i.id = p_invoice
     and i.direction = 'ar' and i.status <> 'void'
     and i.tenant_id is distinct from mytrakin.ctx_tenant()
     and i.company_id = any (mytrakin.ts_my_companies())
     and p.email is not null
$$;
revoke all on function mytrakin.client_payable_recipients(uuid) from public;
grant execute on function mytrakin.client_payable_recipients(uuid) to mytrakin_api;
