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
