"""Platform dashboard: users, companies, pipeline, SaaS revenue and money moving — totals only."""

from decimal import Decimal


async def test_platform_metrics_cover_the_platform(client, auth):
    assert (await client.get("/platform/metrics", headers=auth("finance"))).status_code == 403
    m = (await client.get("/platform/metrics", headers=auth("platform"))).json()
    assert {"users", "companies", "pipeline", "revenue", "money", "activity", "growth"} <= set(m)
    assert m["users"]["total"] >= 6 and m["users"]["active_in_companies"] >= 1
    assert m["companies"]["total"] >= 1 and m["companies"]["active"] >= 1
    assert [s["stage"] for s in m["pipeline"]] == ["Wizard in progress", "Waiting for activation", "Active", "Suspended / closed"]
    assert len(m["money"]["trend"]) == 12
    money = {k: Decimal(str(v)) for k, v in m["money"].items() if k != "trend"}
    assert money["ar_outstanding"] == money["ar_invoiced"] - money["ar_collected"]
    assert money["ar_invoiced"] > 0                     # the demo company has client invoices


async def test_platform_company_rows_hold_only_totals(client, auth):
    rows = (await client.get("/platform/tenants", headers=auth("platform"))).json()
    assert rows and {"ar_invoiced", "ar_collected", "ap_billed", "ap_paid", "mrr"} <= set(rows[0])
    assert not {"number", "invoice_id", "rate", "bill_rate", "pay_rate"} & set(rows[0])   # no invoice-level data
    every = (await client.get("/platform/companies", headers=auth("platform"))).json()
    assert every and {"owner_email", "status", "w9_status"} <= set(every[0])
