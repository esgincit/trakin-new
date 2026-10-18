"""Credit notes (AR-06), adjustment after invoicing (TS-07) and time off on the timesheet (TS-10)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tests.test_flows import THIS_WEEK

WEEK = THIS_WEEK - timedelta(days=63)   # before the seed's invoices (days -40…-10), inside Ravi's placements


async def test_credit_note_lowers_balance_and_releases_pay_when_paid(client, auth):
    consultant, finance = auth("consultant"), auth("finance")
    mine = (await client.get("/timesheets/mine", params={"week": str(WEEK)}, headers=consultant)).json()
    # The S/4 placement is pay-when-paid: its vendor invoice waits for the client invoice.
    rows = [{"placement_id": p["placement_id"], "hours": [0, 8, 8, 0, 0, 0, 0] if p["project"].startswith("S/4") else [0] * 7}
            for p in mine["projects"]]
    assert (await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(WEEK), "rows": rows})).status_code == 200
    ts = await client.post("/timesheets/mine/submit", params={"week": str(WEEK)}, headers=consultant, json={})
    assert ts.status_code == 200, ts.text
    assert (await client.post(f"/timesheets/{ts.json()['id']}/approve", headers=finance)).status_code == 200
    generated = (await client.post("/invoices/generate", headers=finance, json={
        "period_start": str(WEEK), "period_end": str(WEEK + timedelta(days=6))})).json()
    assert {r["direction"] for r in generated["created"]} == {"ar", "ap"}, generated
    ar = next(r for r in generated["created"] if r["direction"] == "ar")

    # TS-07: invoiced hours can't be re-opened; the message names the invoice and the way out.
    late = await client.post(f"/timesheets/{ts.json()['id']}/reject", headers=finance, json={"reason": "Tuesday was 6 hours"})
    assert late.status_code == 409 and ar["number"] in late.text and "credit note" in late.text, late.text

    url = f"/invoices/{ar['id']}/credit-notes"
    assert (await client.post(url, headers=finance, json={"amount": "10", "reason": "Draft"})).status_code == 409
    assert (await client.post(f"/invoices/{ar['id']}/send", headers=finance)).status_code == 200
    assert (await client.post(url, headers=auth("vendor"), json={"amount": "10", "reason": "Not mine"})).status_code == 403
    total = Decimal(str(ar["amount"]))
    assert (await client.post(url, headers=finance, json={"amount": str(total + 1), "reason": "Too much"})).status_code == 400

    two_hours = (total / 8).quantize(Decimal("0.01"))   # 16 h billed, Tuesday was 6 → credit 2 h
    first = await client.post(url, headers=finance, json={"amount": str(two_hours), "reason": "Tuesday was 6 hours, not 8"})
    assert first.status_code == 201, first.text
    assert first.json()["number"].startswith("CN-") and Decimal(str(first.json()["balance"])) == total - two_hours
    detail = (await client.get(f"/invoices/{ar['id']}", headers=finance)).json()
    assert Decimal(str(detail["credited"])) == two_hours and len(detail["credits"]) == 1
    assert detail["live_status"] != "paid"
    listed = {c["number"]: c for c in (await client.get("/credit-notes", headers=finance)).json()}
    assert listed[first.json()["number"]]["status"] == "open" and listed[first.json()["number"]]["invoice"] == ar["number"]
    assert (await client.post(f"/invoices/{ar['id']}/void", headers=finance, json={"body": "Wrong customer"})).status_code == 409

    # Vendor's pay-when-paid invoice is still held; crediting the rest settles the client invoice and releases it.
    ap = next(r for r in generated["created"] if r["direction"] == "ap")
    vendor_status = lambda: client.get(f"/invoices/{ap['id']}", headers=auth("vendor"))  # noqa: E731
    assert (await vendor_status()).json()["live_status"] == "held"
    rest = await client.post(url, headers=finance, json={"amount": str(total - two_hours), "reason": "Customer disputed the week"})
    assert rest.status_code == 201, rest.text
    assert Decimal(str(rest.json()["balance"])) == 0 and [r["id"] for r in rest.json()["released"]] == [ap["id"]]
    assert (await client.get(f"/invoices/{ar['id']}", headers=finance)).json()["live_status"] == "paid"
    assert (await vendor_status()).json()["live_status"] != "held"
    assert all(c["status"] == "applied" for c in (await client.get("/credit-notes", headers=finance)).json()
               if c["invoice"] == ar["number"])


async def test_approved_time_off_shows_on_timesheet(client, auth):
    week = THIS_WEEK + timedelta(days=14)
    asked = await client.post("/me/time-off", headers=auth("consultant"), json={
        "starts_on": str(week + timedelta(days=1)), "ends_on": str(week + timedelta(days=2)), "kind": "pto"})
    assert asked.status_code == 201, asked.text
    before = (await client.get("/timesheets/mine", params={"week": str(week)}, headers=auth("consultant"))).json()
    assert before["time_off"] == [None] * 7, "only approved time off is shown"
    decided = await client.post(f"/time-off/{asked.json()['id']}/decision", headers=auth("admin"), json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    after = (await client.get("/timesheets/mine", params={"week": str(week)}, headers=auth("consultant"))).json()
    assert after["time_off"] == [None, "pto", "pto", None, None, None, None]
