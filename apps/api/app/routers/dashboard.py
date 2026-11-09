"""Home dashboard: money owed both ways, a 6-week cash forecast, and what needs attention."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends

from ..deps import TenantDb, tenant_db
from ..errors import forbidden
from ..utils import week_start

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(db: TenantDb = Depends(tenant_db)):
    ctx = db.ctx
    # Staff see the whole workspace; an end client's representative sees the same
    # figures scoped by RLS to their company's invoices (AR only, no AP).
    if not (ctx.internal or ctx.role == "client_user"):
        raise forbidden("The dashboard is for staff. Vendors and consultants have their own pages.")
    show_ap = ctx.allows("finance")

    kpis = await db.one(
        """select
             coalesce(sum(balance) filter (where direction = 'ar' and balance > 0 and status <> 'void'), 0)            as ar_outstanding,
             count(*)             filter (where direction = 'ar' and balance > 0 and status <> 'void')                 as ar_open_count,
             coalesce(sum(balance) filter (where direction = 'ar' and live_status like 'overdue%'), 0)                as ar_overdue,
             count(*)             filter (where direction = 'ar' and live_status like 'overdue%')                     as ar_overdue_count,
             max(days_late)       filter (where direction = 'ar' and live_status like 'overdue%')                     as ar_oldest_days,
             coalesce(sum(balance) filter (where direction = 'ap' and balance > 0 and status <> 'void'), 0)            as ap_outstanding,
             count(*)             filter (where direction = 'ap' and balance > 0 and status <> 'void')                 as ap_open_count,
             coalesce(sum(balance) filter (where direction = 'ap' and live_status in ('held', 'exception')), 0)       as ap_held
           from invoice_balances"""
    )
    collected = await db.val(
        """select coalesce(sum(p.amount), 0) from payments p join invoices i on i.id = p.invoice_id
            where i.direction = 'ar' and p.paid_on >= current_date - 30 and p.status in ('completed', 'confirmed')"""
    )
    expiring = await db.val(
        """select (select count(*) from sows where end_date between current_date and current_date + 60 and status = 'active')
                + (select count(*) from agreements where expires_on between current_date and current_date + 90 and status = 'active')"""
    )
    kpis = {**kpis, "collected_30d": collected, "contracts_expiring": expiring}
    if not show_ap:
        kpis = {k: v for k, v in kpis.items() if not k.startswith("ap_")}

    # Cash forecast: open AR by due week, open AP by expected payment week.
    this_week = week_start(date.today())
    rows = await db.all(
        """select direction,
                  case when coalesce(scheduled_on, due_on) < current_date then 'past_due'
                       else to_char(coalesce(scheduled_on, due_on) - ((extract(dow from coalesce(scheduled_on, due_on))::int) * interval '1 day'), 'YYYY-MM-DD')
                  end as bucket,
                  sum(balance) as amount
             from invoice_balances
            where balance > 0 and status <> 'void' and live_status not in ('exception')
              and coalesce(scheduled_on, due_on) is not null
            group by 1, 2"""
    )
    buckets = ["past_due"] + [(this_week + timedelta(weeks=i)).isoformat() for i in range(6)]
    forecast = []
    for b in buckets:
        cash_in = sum((r["amount"] for r in rows if r["bucket"] == b and r["direction"] == "ar"), 0)
        cash_out = sum((r["amount"] for r in rows if r["bucket"] == b and r["direction"] == "ap"), 0) if show_ap else None
        forecast.append({"bucket": b, "in": cash_in, "out": cash_out})

    attention = await db.all(
        """select * from (
             select 'overdue' as kind, 'bad' as tone, number as title,
                    c.name || ' · ' || to_char(balance, 'FM$999,999,990.00') || ' open · ' || days_late || ' days late' as detail,
                    'invoice' as ref_type, b.id::text as ref_id, 1 as sort
               from invoice_balances b left join companies c on c.id = b.company_id
              where direction = 'ar' and live_status like 'overdue%'
             union all
             select 'exception', 'bad', number, 'Invoiced ' || hours || ' h, approved ' || coalesce(approved_hours, 0) || ' h',
                    'invoice', id::text, 2 from invoice_balances where direction = 'ap' and live_status = 'exception'
                    and :show_ap
             union all
             select 'held', 'warn', number, 'Pay-when-paid: waiting for the client invoice to be paid', 'invoice', id::text, 3
               from invoice_balances where direction = 'ap' and live_status = 'held' and :show_ap
             union all
             select 'sow_ceiling', 'warn', s.code, b.burn_pct || '% of the value invoiced', 'sow', s.id::text, 4
               from sows s join sow_burn b on b.sow_id = s.id where s.status = 'active' and b.burn_pct >= 90
             union all
             select 'agreement_expiry', 'warn', code, 'Expires ' || to_char(expires_on, 'Mon DD, YYYY'), 'agreement', id::text, 5
                from agreements where status in ('active', 'accepted') and expires_on between current_date and current_date + 90
             union all
             select 'document_expiry', case when expires_on - current_date <= 30 then 'bad' else 'warn' end, label,
                    coalesce((select full_name from consultants where id = d.consultant_id), (select name from companies where id = d.company_id))
                      || ' · ' || coalesce('expires ' || to_char(expires_on, 'Mon DD'), status),
                    'tracked_document', id::text, 6
               from tracked_documents d where active and (status = 'missing' or expires_on <= current_date + 60)
           ) x order by sort, title limit 30""",
        {"show_ap": show_ap},
    )
    missing_ts = await db.all(
        """select c.id, c.full_name from consultants c
            where c.status = 'active'
              and exists (select 1 from placements p where p.consultant_id = c.id and p.status in ('active', 'ending'))
              and not exists (select 1 from timesheets t where t.consultant_id = c.id
                               and t.week_start = :wk and t.status in ('submitted', 'approved'))""",
        {"wk": week_start(date.today()) - timedelta(days=7)},
    ) if ctx.internal else []
    return {"kpis": kpis, "forecast": forecast, "attention": attention, "missing_timesheets_last_week": missing_ts,
            "show_ap": show_ap, "staff": ctx.internal}
