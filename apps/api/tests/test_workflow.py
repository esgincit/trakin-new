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
