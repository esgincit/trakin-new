"""Role-based access: who may answer contracts, see client bill amounts, import / export, open files."""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_engine
from app.permissions import required


async def _set_role(tenant_id, user_id, role):
    async with get_engine().begin() as conn:
        await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status) values (:t, :u, :r, 'active')
               on conflict (tenant_id, user_id) where user_id is not null do update set role = excluded.role"""),
            {"t": tenant_id, "u": user_id, "r": role})


def _rows(resp) -> list[dict]:
    assert resp.status_code == 200, resp.text
    return list(csv.DictReader(io.StringIO(resp.text.lstrip("﻿"))))


def test_credit_notes_follow_the_invoices_module():
    assert required("GET", "/v1/credit-notes") == ("invoices", "read")


# ---- contracts: answering is for admin, legal and account manager
async def test_only_contract_roles_answer_msas_renewals_and_sows(client, auth):
    body, nobody = {"decision": "accept"}, uuid.uuid4()
    for who in ("consultant", "finance"):
        h = auth(who)
        assert (await client.post(f"/agreements/{nobody}/respond", headers=h, json=body)).status_code == 403, who
        assert (await client.post(f"/agreements/renewals/{nobody}/respond", headers=h, json=body)).status_code == 403, who
        assert (await client.post(f"/agreements/{nobody}/renewals", headers=h, json={"expires_on": "2099-01-01"})).status_code == 403, who
        assert (await client.post(f"/sows/{nobody}/respond", headers=h, json={"decision": "approve"})).status_code == 403, who
    # An admin gets past the role check (the record just does not exist).
    assert (await client.post(f"/agreements/{nobody}/respond", headers=auth("admin"), json=body)).status_code == 404
    assert (await client.post(f"/sows/{nobody}/respond", headers=auth("admin"), json={"decision": "approve"})).status_code == 404


@pytest.mark.parametrize("role,allowed", [("consultant", False), ("viewer", False), ("finance", False),
                                           ("legal", True), ("account_manager", True), ("tenant_admin", True)])
async def test_contract_sql_functions_check_the_role(user_ids, role, allowed):
    async with get_engine().begin() as conn:
        await conn.execute(text("select mytrakin.begin_request(:u, null, :r)"), {"u": user_ids["admin"], "r": role})
        for call in ("mytrakin.respond_to_agreement(:i, 'accept')", "mytrakin.respond_to_sow(:i, 'approve')",
                     "mytrakin.respond_to_renewal(:i, 'accept')", "mytrakin.request_renewal(:i, date '2099-01-01')"):
            try:
                async with conn.begin_nested():
                    await conn.execute(text(f"select {call}"), {"i": uuid.uuid4()})
            except DBAPIError as e:
                refused = "Only an admin, legal or account manager" in str(e.orig)
                assert refused is not allowed, (role, call, str(e.orig))


# ---- payment flow: client bill amounts are masked
async def test_consultant_does_not_see_client_bill_amounts(client, auth):
    for path in ("/payment-flow?only_open=false", "/invoices/client-payable"):
        rows = (await client.get(path, headers=auth("consultant"))).json()
        assert all(r.get("ar_amount") is None and r.get("ar_balance") is None and r.get("hours") is None
                   and r.get("amount") is None for r in rows), path
    admin_rows = (await client.get("/payment-flow?only_open=false", headers=auth("admin"))).json()
    assert any(r.get("ar_amount") is not None for r in admin_rows)


# ---- import / export follow module permissions and masking
async def test_export_and_import_follow_the_module_permission(client, auth, user_ids):
    admin, f1 = auth("admin"), auth("finance")
    f1_membership = (await client.get("/session", headers=f1)).json()["membership_id"]
    assert (await client.get("/data/export/payments.csv", headers=f1)).status_code == 200
    try:
        assert (await client.patch(f"/users/{f1_membership}/access", headers=admin,
                                   json={"permission_overrides": {"invoices": "read", "audit": "none"}})).status_code == 200
        assert (await client.get("/data/export/ar_invoices.csv", headers=f1)).status_code == 200      # read is enough to export
        assert (await client.get("/data/export/audit.csv", headers=f1)).status_code == 403
        tpl = {t["key"]: t["can_import"] for t in (await client.get("/data/templates", headers=f1)).json()}
        assert tpl["ar_invoices"] is False and tpl["payroll"] is True
        up = await client.post("/data/import/ar_invoices?dry_run=1", headers=f1, files={"file": ("a.csv", b"x\n1\n")})
        assert up.status_code == 403 and up.json()["error"]["code"] == "no_permission"
    finally:
        await client.patch(f"/users/{f1_membership}/access", headers=admin, json={"permission_overrides": {}})
    assert (await client.get("/data/export/audit.csv", headers=f1)).status_code == 200


async def test_exports_hide_pay_rates_and_eins_from_the_same_roles_as_the_screens(client, auth, user_ids):
    tenant = (await client.get("/session", headers=auth("admin"))).json()["tenant"]["id"]
    admin_pl = _rows(await client.get("/data/export/placements.csv", headers=auth("admin")))
    assert any(r["AP pay rate"] for r in admin_pl)
    admin_co = _rows(await client.get("/data/export/companies.csv", headers=auth("admin")))
    try:
        await _set_role(tenant, user_ids["finance2"], "account_manager")
        pl = _rows(await client.get("/data/export/placements.csv", headers=auth("finance2")))
        assert pl and not any(r["AP pay rate"] for r in pl) and any(r["AR bill rate"] for r in pl)
        assert not any(r["EIN"] for r in _rows(await client.get("/data/export/companies.csv", headers=auth("finance2"))))
        await _set_role(tenant, user_ids["finance2"], "viewer")
        assert not any(r["EIN"] for r in _rows(await client.get("/data/export/companies.csv", headers=auth("finance2"))))
        await _set_role(tenant, user_ids["finance2"], "finance")
        fin_co = _rows(await client.get("/data/export/companies.csv", headers=auth("finance2")))
        assert [r["EIN"] for r in fin_co] == [r["EIN"] for r in admin_co]
    finally:
        await _set_role(tenant, user_ids["finance2"], "finance")


# ---- /me/documents/{id}/link follows the Compliance module and soft deletes
async def test_my_document_link_respects_compliance_permission_and_deletion(client, auth):
    admin, f1 = auth("admin"), auth("finance")
    tenant = (await client.get("/session", headers=admin)).json()["tenant"]["id"]
    async with get_engine().begin() as conn:
        doc = (await conn.execute(text(
            """insert into mytrakin.documents (tenant_id, owner_type, owner_id, name, storage_path, deleted_at)
               values (:t, 'company', gen_random_uuid(), 'old.pdf', 'x/old.pdf', now()) returning id"""), {"t": tenant})).scalar()
    f1_membership = (await client.get("/session", headers=f1)).json()["membership_id"]
    try:
        assert (await client.get(f"/me/documents/{doc}/link", headers=f1)).status_code == 404      # deleted stays deleted
        assert (await client.patch(f"/users/{f1_membership}/access", headers=admin,
                                   json={"permission_overrides": {"compliance": "none"}})).status_code == 200
        r = await client.get(f"/me/documents/{doc}/link", headers=f1)
        assert r.status_code == 403 and r.json()["error"]["code"] == "no_permission"
    finally:
        await client.patch(f"/users/{f1_membership}/access", headers=admin, json={"permission_overrides": {}})
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.documents where id = :d"), {"d": doc})
