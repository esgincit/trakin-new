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
