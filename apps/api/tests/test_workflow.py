"""Approved workflow (owner e-mail 2026-10-15, PLAN §5.30 WF-01…11): switches, gates, SOWs under projects,
acceptance, payment confirmation. Tests restore every switch or record they change."""

from __future__ import annotations

from sqlalchemy import text

from app.db import get_engine


async def _sql(statement: str, **params) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(text(statement), params)


async def _switch(client, auth, **values: bool):
    response = await client.patch("/workspace", headers=auth("admin"), json={"settings": {"workflow": values}})
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------- WF-01 switches
async def test_workflow_switches_default_on_and_admin_can_change(client, auth):
    ws = (await client.get("/workspace/workflow", headers=auth("finance"))).json()
    assert ws == {"requireNDA": True, "requireMSA": True, "requireAcceptance": True, "requireContract": True}
    try:
        await _switch(client, auth, requireNDA=False)
        now = (await client.get("/workspace/workflow", headers=auth("finance"))).json()
        assert now["requireNDA"] is False and now["requireMSA"] is True      # the other switches are kept
    finally:
        await _switch(client, auth, requireNDA=True)
    bad = await client.patch("/workspace", headers=auth("admin"), json={"settings": {"workflow": {"requireXYZ": True}}})
    assert bad.status_code == 400, bad.text
    assert (await client.patch("/workspace", headers=auth("finance"),
                               json={"settings": {"workflow": {"requireNDA": False}}})).status_code == 403
    assert (await client.get("/workspace/workflow", headers=auth("vendor"))).status_code == 403


# ---------------------------------------------------------------------------- WF-07 engagement types
async def _company(client, auth, name: str) -> str:
    return next(c["id"] for c in (await client.get("/companies", headers=auth("admin"))).json() if c["name"] == name)


async def test_engagement_types_include_e2e(client, auth):
    types = {t["code"]: t["pay_model"] for t in (await client.get("/consultants/engagement-types", headers=auth("admin"))).json()}
    assert types["e2e"] == "vendor" and types["c2c"] == "vendor" and types["1099"] == "self"
    bright = await _company(client, auth, "BrightPath Tech LLC")
    person = {"full_name": "Esha Twoe", "email": "esha.e2e@example.com", "start_date": "2026-11-02"}
    missing = await client.post("/consultants", headers=auth("admin"), json={**person, "engagement": "e2e"})
    assert missing.status_code == 400 and "employer" in missing.text, missing.text
    unknown = await client.post("/consultants", headers=auth("admin"), json={**person, "engagement": "h1b_magic"})
    assert unknown.status_code == 400, unknown.text
    created = await client.post("/consultants", headers=auth("admin"),
                                json={**person, "engagement": "e2e", "employer_company_id": bright})
    assert created.status_code == 201, created.text
    items = [i["item"] for i in created.json()["onboarding_checklist"]]
    assert "Vendor SOW / work order signed" in items          # same checklist as C2C


# ---------------------------------------------------------------------------- WF-08 naming engine
async def test_numbering_templates_from_settings(client, auth):
    admin = auth("admin")
    atlas = await _company(client, auth, "Atlas Foods Corp.")
    bad = await client.patch("/workspace", headers=admin, json={"settings": {"numbering": {"project": "P-{YEAR}"}}})
    assert bad.status_code == 400, bad.text
    try:
        await client.patch("/workspace", headers=admin, json={"settings": {"numbering": {"project": "PROJ-{YEAR}-{SEQ:3}"}}})
        preview = (await client.get("/projects/next-code", headers=admin)).json()["code"]
        created = await client.post("/projects", headers=admin, json={"name": "Numbered", "client_company_id": atlas,
                                                                       "status": "planned"})
        assert created.status_code == 201, created.text
        code = created.json()["code"]
        assert code == preview and code.startswith("PROJ-") and len(code.split("-")[-1]) == 3, code
        templates = (await client.get("/workspace/numbering", headers=admin)).json()
        assert templates["project"]["template"] == "PROJ-{YEAR}-{SEQ:3}"
    finally:
        await client.patch("/workspace", headers=admin, json={"settings": {"numbering": {"project": "PRJ-{SEQ:2}"}}})


# ---------------------------------------------------------------------------- WF-04 SOW → project → resources
async def _consultant(client, auth, name: str) -> str:
    return next(c["id"] for c in (await client.get("/consultants", headers=auth("admin"))).json() if c["full_name"] == name)


async def _agreement(client, auth, code: str) -> str:
    return next(a["id"] for a in (await client.get("/agreements", headers=auth("admin"))).json() if a["code"] == code)


async def test_sow_under_project_with_one_or_many_resources(client, auth):
    admin = auth("admin")
    atlas = await _company(client, auth, "Atlas Foods Corp.")
    msa = await _agreement(client, auth, "MSA-AF-ESG")
    project = (await client.post("/projects", headers=admin, json={"name": "WF Multi", "client_company_id": atlas,
                                                                    "status": "active"})).json()
    other = (await client.post("/projects", headers=admin, json={"name": "WF Other", "client_company_id": atlas,
                                                                  "status": "planned"})).json()
    sow_body = {"agreement_id": msa, "side": "we_bill", "title": "Data platform", "start_date": "2026-11-02",
                "end_date": "2027-04-30", "value_cap": 200000}
    multi = await client.post(f"/projects/{project['id']}/sows", headers=admin, json=sow_body)
    assert multi.status_code == 201, multi.text
    assert multi.json()["project_id"] == project["id"] and multi.json()["code"].startswith("SOW-")
    single = (await client.post(f"/projects/{project['id']}/sows", headers=admin, json={**sow_body, "title": "QA"})).json()

    for name in ("Grace Okafor", "Priya Nair"):        # two W-2 resources on one SOW
        added = await client.post(f"/sows/{multi.json()['id']}/resources", headers=admin, json={
            "consultant_id": await _consultant(client, auth, name), "start_date": "2026-11-02", "ar_company_id": atlas,
            "bill_rate": 90})
        assert added.status_code == 201, added.text
    one = await client.post(f"/sows/{single['id']}/resources", headers=admin, json={
        "consultant_id": await _consultant(client, auth, "Grace Okafor"), "start_date": "2026-11-02"})
    assert one.status_code == 201, one.text
    assert len((await client.get(f"/sows/{multi.json()['id']}/resources", headers=admin)).json()) == 2
    assert len((await client.get(f"/sows/{single['id']}/resources", headers=admin)).json()) == 1

    wrong = await client.post(f"/sows/{single['id']}/resources", headers=admin, json={
        "consultant_id": await _consultant(client, auth, "Priya Nair"), "start_date": "2026-11-02",
        "project_id": other["id"]})
    assert wrong.status_code == 400, wrong.text
    detail = (await client.get(f"/projects/{project['id']}", headers=admin)).json()
    assert {s["id"] for s in detail["sows"]} >= {multi.json()["id"], single["id"]}


# ---------------------------------------------------------------------------- WF-02/03 NDA → MSA → project, AGR-09
async def test_nda_and_msa_gates_follow_the_switches(client, auth):
    admin = auth("admin")
    created = await client.post("/companies", headers=admin, json={
        "name": "Gatekeeper Labs LLC", "kind": "client", "domain": "gatekeeper.example", "business_type": "LLC",
        "address": "1 Main St, Austin, TX", "state": "TX", "contact_name": "G. Keeper",
        "contact_email": "g@gatekeeper.example", "contact_phone": "555-0101"})
    assert created.status_code == 201, created.text
    company = created.json()["id"]
    msa_body = {"kind": "msa", "company_id": company, "tenant_side": "supplier", "effective_on": "2026-10-01"}
    project_body = {"name": "Gated", "client_company_id": company, "status": "active"}

    no_nda = await client.post("/agreements", headers=admin, json=msa_body)
    assert no_nda.status_code == 409 and "nda_required" in no_nda.text, no_nda.text
    gated = await client.post("/projects", headers=admin, json=project_body)
    assert gated.status_code == 409 and "nda_required" in gated.text, gated.text
    assert (await client.post("/projects", headers=admin, json={**project_body, "status": "planned"})).status_code == 201
    try:
        await _switch(client, auth, requireNDA=False)
        no_msa = await client.post("/projects", headers=admin, json=project_body)
        assert no_msa.status_code == 409 and "msa_required" in no_msa.text, no_msa.text
        await _switch(client, auth, requireMSA=False)
        assert (await client.post("/projects", headers=admin, json=project_body)).status_code == 201
        msa = await client.post("/agreements", headers=admin, json=msa_body)
        assert msa.status_code == 201 and msa.json()["code"].startswith("MSA-GATEKEEPER"), msa.text
    finally:
        await _switch(client, auth, requireNDA=True, requireMSA=True)


async def test_no_active_msa_blocks_invoices_and_new_sows(client, auth):
    finance, admin = auth("finance"), auth("admin")
    ravi = next(p for p in (await client.get("/placements", headers=finance)).json()
                if p["consultant"] == "Ravi Kumar" and p["ar_company"] == "Northwind Consulting")
    await _sql("update mytrakin.agreements set status = 'terminated' where code = 'MSA-NW-ESG'")
    try:
        blocked = await client.post("/invoices", headers=finance, json={
            "placement_id": ravi["id"], "period_start": "2026-03-01", "period_end": "2026-03-07", "hours": 8, "send": False})
        assert blocked.status_code == 409 and "MSA" in blocked.text, blocked.text
    finally:
        await _sql("update mytrakin.agreements set status = 'active' where code = 'MSA-NW-ESG'")

    northwind = await _company(client, auth, "Northwind Consulting")
    old = await client.post("/agreements", headers=admin, json={
        "code": "MSA-NW-OLD", "kind": "msa", "company_id": northwind, "tenant_side": "supplier",
        "effective_on": "2024-01-01", "expires_on": "2025-12-31"})
    assert old.status_code == 201, old.text
    sow = await client.post("/sows", headers=admin, json={
        "code": "WO-NW-OLD-1", "agreement_id": old.json()["id"], "side": "we_bill", "title": "Too late",
        "start_date": "2026-11-01", "end_date": "2026-12-31"})
    assert sow.status_code == 409 and "expired" in sow.text, sow.text


# ---------------------------------------------------------------------------- WF-05/06 acceptance + resource contract
async def test_manual_acceptance_activates_and_is_kept_in_history(client, auth):
    admin = auth("admin")
    msa = await _agreement(client, auth, "MSA-AF-ESG")
    sow = (await client.post("/sows", headers=admin, json={
        "agreement_id": msa, "side": "we_bill", "title": "Paper-signed SOW", "start_date": "2026-11-02",
        "end_date": "2027-01-29", "status": "draft"})).json()
    accepted = await client.post("/acceptances", headers=admin, json={
        "entity_type": "sow", "entity_id": sow["id"], "accepted_by": "J. Brooks (Atlas Foods)", "note": "Wet ink, scanned"})
    assert accepted.status_code == 201, accepted.text
    assert (await client.get(f"/sows/{sow['id']}", headers=admin)).json()["status"] == "active"
    history = (await client.get("/acceptances", params={"entity_type": "sow", "entity_id": sow["id"]},
                                headers=admin)).json()
    assert len(history) == 1 and history[0]["method"] == "manual" and history[0]["accepted_by"].startswith("J. Brooks")
    assert (await client.post("/acceptances", headers=auth("vendor"), json={
        "entity_type": "sow", "entity_id": sow["id"], "accepted_by": "Someone"})).status_code == 403


async def test_timesheet_needs_the_resource_contract(client, auth):
    from datetime import date, timedelta
    consultant = auth("consultant")
    week = date.today() - timedelta(days=(date.today().weekday() + 1) % 7) - timedelta(weeks=20)
    finance = auth("finance")
    ravi = next(p for p in (await client.get("/placements", headers=finance)).json()
                if p["consultant"] == "Ravi Kumar" and p["ar_company"] == "Northwind Consulting")
    mine = (await client.get("/timesheets/mine", params={"week": str(week)}, headers=consultant)).json()
    rows = [{"placement_id": ravi["id"], "hours": [0, 8, 8, 0, 0, 0, 0]}]
    assert any(p["placement_id"] == ravi["id"] for p in mine["projects"]), mine
    await _sql("update mytrakin.placements set ap_sow_id = null where id = :id", id=ravi["id"])
    try:
        saved = await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(week), "rows": rows})
        assert saved.status_code == 200, saved.text
        blocked = await client.post("/timesheets/mine/submit", params={"week": str(week)}, headers=consultant, json={})
        assert blocked.status_code == 409 and "contract_required" in blocked.text, blocked.text
        await _switch(client, auth, requireContract=False)
        ok = await client.post("/timesheets/mine/submit", params={"week": str(week)}, headers=consultant, json={})
        assert ok.status_code == 200, ok.text
    finally:
        await _switch(client, auth, requireContract=True)
        await _sql("update mytrakin.placements set ap_sow_id = (select id from mytrakin.sows where code = :c) where id = :id",
                   c=ravi["ap_sow"], id=ravi["id"])
        await _sql("delete from mytrakin.timesheets where consultant_id = (select consultant_id from mytrakin.placements "
                   "where id = :id) and week_start = :w", id=ravi["id"], w=week)


# ---------------------------------------------------------------------------- WF-09 payment status + confirmation
async def _invoice(client, auth, direction: str, number: str) -> dict:
    rows = (await client.get("/invoices", params={"direction": direction}, headers=auth("finance"))).json()
    return next(r for r in rows if r["number"] == number)


async def test_payment_lifecycle_and_confirmation(client, auth):
    finance = auth("finance")
    ar = await _invoice(client, auth, "ar", "ESG-AR-0412")
    detail = lambda: client.get(f"/invoices/{ar['id']}", headers=finance)  # noqa: E731
    before = (await detail()).json()["balance"]

    recorded = await client.post(f"/invoices/{ar['id']}/payments", headers=finance, json={
        "amount": 100, "paid_on": "2026-10-01", "method": "ACH", "reference": "WF-9", "status": "processing"})
    assert recorded.status_code == 201, recorded.text
    payment = recorded.json()["payment_id"]
    assert (await detail()).json()["balance"] == before                     # in flight: not counted yet
    assert (await client.post(f"/payments/{payment}/confirm", headers=finance)).status_code == 409
    done = await client.post(f"/payments/{payment}/status", headers=finance, json={"status": "completed"})
    assert done.status_code == 200, done.text
    assert float((await detail()).json()["balance"]) == float(before) - 100
    back = await client.post(f"/payments/{payment}/status", headers=finance, json={"status": "processing"})
    assert back.status_code == 409, back.text

    assert (await client.post(f"/payments/{payment}/confirm", headers=auth("vendor"))).status_code in (403, 404)
    confirmed = await client.post(f"/payments/{payment}/confirm", headers=finance)
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed", confirmed.text
    assert confirmed.json()["confirmed_by_name"]
    assert (await client.post(f"/payments/{payment}/confirm", headers=finance)).status_code == 409

    # The vendor confirms money paid to it.
    ap = await _invoice(client, auth, "ap", "BP-INV-1187")
    await _sql("""insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference, status)
                  select tenant_id, id, 10, current_date, 'ACH', 'WF-9-AP', 'completed' from mytrakin.invoices where id = :id""",
               id=ap["id"])
    try:
        ap_payment = next(p for p in (await client.get(f"/invoices/{ap['id']}", headers=finance)).json()["payments"]
                          if p["reference"] == "WF-9-AP")
        by_vendor = await client.post(f"/payments/{ap_payment['id']}/confirm", headers=auth("vendor"))
        assert by_vendor.status_code == 200 and by_vendor.json()["status"] == "confirmed", by_vendor.text
    finally:
        await _sql("delete from mytrakin.payments where reference in ('WF-9', 'WF-9-AP')")


# ---------------------------------------------------------------------------- WF-11 end to end
async def test_verify_to_payment_confirmation_end_to_end(client, auth):
    """New client → NDA → MSA → project → SOW → resource + contract (accepted) → timesheet → invoices → payments →
    payment confirmations, with every workflow switch on."""
    from datetime import date, timedelta
    admin, finance, consultant = auth("admin"), auth("finance"), auth("consultant")
    week = date.today() - timedelta(days=(date.today().weekday() + 1) % 7) - timedelta(weeks=12)
    accept = lambda kind, rid: client.post("/acceptances", headers=admin, json={  # noqa: E731
        "entity_type": kind, "entity_id": rid, "accepted_by": "Chain Client signatory"})

    client_co = (await client.post("/companies", headers=admin, json={
        "name": "Chainline Retail Inc.", "kind": "client", "domain": "chainline.example", "state": "TX",
        "contact_name": "C. Line", "contact_email": "ap@chainline.example"})).json()["id"]
    nda = (await client.post("/agreements", headers=admin, json={
        "kind": "nda", "company_id": client_co, "tenant_side": "supplier", "effective_on": str(week), "status": "draft"})).json()
    assert (await accept("agreement", nda["id"])).status_code == 201
    msa = await client.post("/agreements", headers=admin, json={
        "kind": "msa", "company_id": client_co, "tenant_side": "supplier", "effective_on": str(week - timedelta(days=7)),
        "payment_terms": "Net 30", "status": "draft"})
    assert msa.status_code == 201, msa.text
    assert (await accept("agreement", msa.json()["id"])).status_code == 201
    project = await client.post("/projects", headers=admin, json={"name": "Chainline POS", "client_company_id": client_co,
                                                                   "status": "active"})
    assert project.status_code == 201, project.text
    pid = project.json()["id"]

    sow = (await client.post(f"/projects/{pid}/sows", headers=admin, json={
        "agreement_id": msa.json()["id"], "side": "we_bill", "title": "POS rollout", "start_date": str(week),
        "end_date": str(week + timedelta(days=6)), "value_cap": 50000, "status": "draft"})).json()
    work_order = (await client.post(f"/projects/{pid}/sows", headers=admin, json={
        "agreement_id": await _agreement(client, auth, "MSA-ESG-BP"), "side": "we_pay", "title": "R. Kumar work order",
        "start_date": str(week), "end_date": str(week + timedelta(days=6)), "status": "draft"})).json()
    assert work_order["code"].startswith("CON-"), work_order
    for kind, rid in (("sow", sow["id"]), ("sow", work_order["id"])):
        assert (await accept(kind, rid)).status_code == 201

    ravi = await _consultant(client, auth, "Ravi Kumar")
    resource = await client.post(f"/sows/{sow['id']}/resources", headers=admin, json={
        "consultant_id": ravi, "start_date": str(week), "end_date": str(week + timedelta(days=6)),
        "ar_company_id": client_co, "bill_rate": 100, "ar_terms": "Net 30",
        "ap_company_id": await _company(client, auth, "BrightPath Tech LLC"), "ap_sow_id": work_order["id"],
        "pay_rate": 80, "ap_terms": "Net 30"})
    assert resource.status_code == 201, resource.text
    placement = resource.json()["id"]

    rows = [{"placement_id": placement, "hours": [0, 8, 8, 8, 0, 0, 0]}]
    assert (await client.put("/timesheets/mine", headers=consultant,
                             json={"week_start": str(week), "rows": rows})).status_code == 200
    ts = await client.post("/timesheets/mine/submit", params={"week": str(week)}, headers=consultant, json={})
    assert ts.status_code == 200, ts.text
    assert (await client.post(f"/timesheets/{ts.json()['id']}/approve", headers=finance)).status_code == 200

    generated = (await client.post("/invoices/generate", headers=finance, json={
        "period_start": str(week), "period_end": str(week + timedelta(days=6))})).json()
    assert not generated["blocked"], generated
    mine = {i["direction"]: i for i in generated["created"]}
    assert float(mine["ar"]["amount"]) == 2400 and float(mine["ap"]["amount"]) == 1920, generated

    for direction, who in (("ar", finance), ("ap", auth("vendor"))):
        paid = await client.post(f"/invoices/{mine[direction]['id']}/payments", headers=finance, json={
            "amount": mine[direction]["amount"], "paid_on": str(date.today()), "method": "ACH", "reference": f"E2E-{direction}"})
        assert paid.status_code == 201, paid.text
        confirmed = await client.post(f"/payments/{paid.json()['payment_id']}/confirm", headers=who)
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed", (direction, confirmed.text)
    assert (await client.get(f"/invoices/{mine['ar']['id']}", headers=finance)).json()["live_status"] == "paid"


async def test_in_flight_payments_cannot_overpay(client, auth):
    finance = auth("finance")
    ar = await _invoice(client, auth, "ar", "ESG-AR-0414")
    balance = float((await client.get(f"/invoices/{ar['id']}", headers=finance)).json()["balance"])
    body = {"amount": balance, "paid_on": "2026-10-01", "method": "ACH", "reference": "WF-9-DUP", "status": "pending"}
    try:
        first = await client.post(f"/invoices/{ar['id']}/payments", headers=finance, json=body)
        assert first.status_code == 201, first.text
        second = await client.post(f"/invoices/{ar['id']}/payments", headers=finance, json=body)
        assert second.status_code == 400 and "in flight" in second.text, second.text
        done = await client.post(f"/payments/{first.json()['payment_id']}/status", headers=finance, json={"status": "completed"})
        assert done.status_code == 200, done.text           # completing re-checks and still fits
    finally:
        await _sql("delete from mytrakin.payments where reference = 'WF-9-DUP'")
        await _sql("update mytrakin.invoices set status = 'sent' where number = 'ESG-AR-0414'")
