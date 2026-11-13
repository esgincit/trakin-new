"""A user's company / consultant link must be one the workspace works with, the cross-workspace
helpers only trust such links, the two timesheet approvals stay separate, and only finance
records payments on another workspace's invoices (security review, team decisions 2026-11-11)."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_engine
from tests.conftest import token_for


async def _q(sql: str, **params):
    async with get_engine().begin() as conn:
        return (await conn.execute(text(sql), params)).scalar()


async def _home() -> uuid.UUID:
    return await _q("select tenant_id from mytrakin.memberships where invited_email = 'admin@example.com'")


async def _other_workspace(name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Another workspace with its own company and a consultant record."""
    tag = uuid.uuid4().hex[:6]
    async with get_engine().begin() as conn:
        t = (await conn.execute(text("insert into mytrakin.tenants (name, status) values (:n, 'active') returning id"),
                                {"n": f"{name} {tag}"})).scalar()
        co = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, business_code, name, kind, kinds, status)
               values (:t, mytrakin.next_business_code(), :n, 'client', array['client'], 'active') returning id"""),
            {"t": t, "n": f"{name} Co {tag}"})).scalar()
        await conn.execute(text("update mytrakin.tenants set company_id = :c where id = :t"), {"c": co, "t": t})
        k = (await conn.execute(text(
            """insert into mytrakin.consultants (tenant_id, full_name, engagement, status)
               values (:t, 'Elsewhere Person', '1099', 'active') returning id"""), {"t": t})).scalar()
    return t, co, k


async def _local_company(name: str) -> uuid.UUID:
    return await _q(
        """insert into mytrakin.companies (tenant_id, business_code, name, kind, kinds, status)
           values (:t, mytrakin.next_business_code(), :n, 'client', array['client'], 'active') returning id""",
        t=await _home(), n=f"{name} {uuid.uuid4().hex[:6]}")


async def _user(role: str, company_id=None) -> dict[str, str]:
    """A signed-in member of the demo workspace with the given role."""
    email = f"{role}-{uuid.uuid4().hex[:8]}@links.example"
    async with get_engine().begin() as conn:
        await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, invited_email, role, company_id)
               values (:t, :e, :r, :c)"""), {"t": await _home(), "e": email, "r": role, "c": company_id})
        uid = (await conn.execute(text("insert into auth.users (email) values (:e) returning id"), {"e": email})).scalar()
    return {"Authorization": f"Bearer {token_for(uid, email)}"}


# ----------------------------------------------------------------------------- invite / DB guard
async def test_invite_links_only_companies_and_consultants_of_this_workspace(client):
    _, foreign_co, foreign_consultant = await _other_workspace("Invite Target")
    admin = await _user("tenant_admin")
    refused = await client.post("/users", headers=admin, json={
        "email": f"rep-{uuid.uuid4().hex[:6]}@links.example", "role": "client_user", "company_id": str(foreign_co)})
    assert refused.status_code == 400, refused.text
    refused = await client.post("/users", headers=admin, json={
        "email": f"k-{uuid.uuid4().hex[:6]}@links.example", "role": "consultant",
        "consultant_id": str(foreign_consultant)})
    assert refused.status_code == 400, refused.text

    own = await _local_company("Own Client")
    ok = await client.post("/users", headers=admin, json={
        "email": f"rep-{uuid.uuid4().hex[:6]}@links.example", "role": "client_user", "company_id": str(own)})
    assert ok.status_code == 201, ok.text
    own_consultant = await _q("select consultant_id from mytrakin.memberships where invited_email = 'ravi.kumar@example.com'")
    ok = await client.post("/users", headers=admin, json={
        "email": f"k-{uuid.uuid4().hex[:6]}@links.example", "role": "consultant", "consultant_id": str(own_consultant)})
    assert ok.status_code == 201, ok.text


async def test_database_refuses_a_link_to_a_company_the_workspace_does_not_work_with():
    _, foreign_co, _ = await _other_workspace("Guarded")
    with pytest.raises(DBAPIError):
        await _q("""insert into mytrakin.memberships (tenant_id, invited_email, role, company_id)
                    values (:t, 'guard@links.example', 'client_user', :c) returning id""", t=await _home(), c=foreign_co)
    # Changing an existing link is checked too.
    mid = await _q("""insert into mytrakin.memberships (tenant_id, invited_email, role, company_id)
                      values (:t, 'guard2@links.example', 'client_user', :c) returning id""",
                   t=await _home(), c=await _local_company("Guard Local"))
    with pytest.raises(DBAPIError):
        await _q("update mytrakin.memberships set company_id = :c where id = :m returning id", c=foreign_co, m=mid)


async def test_a_company_with_an_accepted_msa_can_be_linked():
    other, foreign_co, _ = await _other_workspace("Partner")
    home = await _home()
    own_co = await _q("select company_id from mytrakin.tenants where id = :t", t=home)
    # The partner's workspace sent our company an MSA; pending is not enough, accepted is.
    aid = await _q("""insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, status)
                      values (:t, :code, 'msa', :c, 'buyer', 'pending') returning id""",
                   t=other, code=f"MSA-{uuid.uuid4().hex[:6]}", c=own_co)
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is False
    await _q("""update mytrakin.agreements set status = 'accepted',
                       accepted_by = (select id from auth.users where email = 'admin@example.com')
                 where id = :a returning id""", a=aid)
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is True


async def test_an_msa_the_other_company_never_confirmed_does_not_count():
    """An MSA we record ourselves (imported / 'active', or 'accepted' by one of our own
    people) is no proof that the other company works with us."""
    _, foreign_co, _ = await _other_workspace("Unconfirmed")
    home = await _home()
    admin = await _q("select id from auth.users where email = 'admin@example.com'")
    aid = await _q("""insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, status, source)
                      values (:t, :code, 'msa', :c, 'supplier', 'active', 'imported') returning id""",
                   t=home, code=f"MSA-{uuid.uuid4().hex[:6]}", c=foreign_co)
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is False
    await _q("update mytrakin.agreements set status = 'accepted', accepted_by = :d where id = :a returning id",
             d=admin, a=aid)
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is False
    # Accepted by a member of that company: now it counts.
    member = await _q("insert into auth.users (email) values (:e) returning id", e=f"cp-{uuid.uuid4().hex[:6]}@links.example")
    await _q("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                select tenant_id, id, :u, 'admin', 'active' from mytrakin.companies where id = :c returning id""",
             u=member, c=foreign_co)
    await _q("update mytrakin.agreements set accepted_by = :d where id = :a returning id", d=member, a=aid)
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is True


async def test_a_rejected_msa_later_marked_accepted_by_the_sender_does_not_count(client):
    """The other company rejected our MSA; recording a paper acceptance on our side
    afterwards is no proof that it works with us."""
    _, foreign_co, _ = await _other_workspace("Rejecting")
    home = await _home()
    member = await _q("insert into auth.users (email) values (:e) returning id", e=f"rj-{uuid.uuid4().hex[:6]}@links.example")
    await _q("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                select tenant_id, id, :u, 'admin', 'active' from mytrakin.companies where id = :c returning id""",
             u=member, c=foreign_co)
    aid = await _q("""insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, status)
                      values (:t, :code, 'msa', :c, 'supplier', 'pending') returning id""",
                   t=home, code=f"MSA-{uuid.uuid4().hex[:6]}", c=foreign_co)
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(text("select tenant_id from mytrakin.companies where id = :c"), {"c": foreign_co})).scalar()
        await conn.execute(text("select mytrakin.begin_request(:u, :t, 'legal')"), {"u": member, "t": tenant})
        await conn.execute(text("select mytrakin.respond_to_agreement(:a, 'reject', 'Not working with you')"), {"a": aid})
    assert await _q("select status from mytrakin.agreements where id = :a", a=aid) == "rejected"

    paper = await client.post("/acceptances", headers=await _user("legal"), json={
        "entity_type": "agreement", "entity_id": str(aid), "accepted_by": "Someone (on paper)"})
    assert paper.status_code == 201, paper.text
    assert await _q("select status from mytrakin.agreements where id = :a", a=aid) == "accepted"
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is False

    # A real accept by that company's own person does count.
    await _q("update mytrakin.agreements set status = 'terminated' where id = :a returning id", a=aid)
    aid2 = await _q("""insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, status)
                       values (:t, :code, 'subcontract', :c, 'buyer', 'pending') returning id""",
                    t=home, code=f"SUB-{uuid.uuid4().hex[:6]}", c=foreign_co)
    async with get_engine().begin() as conn:
        await conn.execute(text("select mytrakin.begin_request(:u, :t, 'legal')"), {"u": member, "t": tenant})
        await conn.execute(text("select mytrakin.respond_to_agreement(:a, 'accept')"), {"a": aid2})
    assert await _q("select mytrakin.membership_link_ok(:t, :c, null)", t=home, c=foreign_co) is True


async def test_signer_rows_typed_by_a_sender_do_not_unlock_a_companys_admins():
    _, foreign_co, _ = await _other_workspace("Signers Of")
    home = await _home()
    member = await _q("insert into auth.users (email) values (:e) returning id", e=f"adm-{uuid.uuid4().hex[:6]}@links.example")
    await _q("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                select tenant_id, id, :u, 'admin', 'active' from mytrakin.companies where id = :c returning id""",
             u=member, c=foreign_co)
    env = await _q("""insert into mytrakin.envelopes (tenant_id, number, title, status)
                      values (:t, :n, 'Typed signer', 'completed') returning id""", t=home, n=f"ENV-{uuid.uuid4().hex[:6]}")
    await _q("""insert into mytrakin.envelope_signers (tenant_id, envelope_id, position, name, email, company_id, status)
                values (:t, :e, 1, 'Anyone', 'anyone@links.example', :c, 'signed') returning id""",
             t=home, e=env, c=foreign_co)
    async with get_engine().connect() as conn:
        uid = (await conn.execute(text("select id from auth.users where email = 'admin@example.com'"))).scalar()
        await conn.execute(text("select mytrakin.begin_request(:u, :t, 'legal')"), {"u": uid, "t": home})
        rows = (await conn.execute(text("select * from mytrakin.company_signing_admins(:c)"), {"c": foreign_co})).all()
        local = (await conn.execute(text(
            "select count(*) from mytrakin.company_signing_admins((select id from mytrakin.companies where name = 'BrightPath Tech LLC'))"))).scalar()
        await conn.rollback()
    assert rows == []
    assert local > 0          # a company record of our own workspace still lists its admins


async def test_consultant_login_link_never_touches_another_workspaces_record():
    _, _, foreign_consultant = await _other_workspace("Consultant Owner")
    home = await _home()
    async with get_engine().connect() as conn:
        # Even with the link guard switched off, the login trigger stays inside the workspace.
        await conn.execute(text("alter table mytrakin.memberships disable trigger memberships_link_guard"))
        uid = (await conn.execute(text("insert into auth.users (email) values (:e) returning id"),
                                  {"e": f"k-{uuid.uuid4().hex[:6]}@links.example"})).scalar()
        await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, consultant_id, status)
               values (:t, :u, 'consultant', :k, 'active')"""), {"t": home, "u": uid, "k": foreign_consultant})
        linked = (await conn.execute(text("select user_id from mytrakin.consultants where id = :k"),
                                     {"k": foreign_consultant})).scalar()
        await conn.rollback()
    assert linked is None


# ----------------------------------------------------------------------------- SQL helpers
async def _helper_sets(role: str, company) -> tuple[list, list]:
    async with get_engine().connect() as conn:
        uid = (await conn.execute(text("select id from auth.users where email = 'admin@example.com'"))).scalar()
        await conn.execute(text("select mytrakin.begin_request(:u, :t, :r, :c)"),
                           {"u": uid, "t": await _home(), "r": role, "c": company})
        ts = (await conn.execute(text("select mytrakin.ts_my_companies()"))).scalar()
        mine = (await conn.execute(text("select mytrakin.my_company_ids()"))).scalar()
        await conn.rollback()
    return [str(x) for x in ts], [str(x) for x in mine]


async def test_cross_workspace_helpers_trust_only_this_workspaces_companies():
    _, foreign_co, _ = await _other_workspace("Helper Target")
    ts, mine = await _helper_sets("client_user", foreign_co)
    assert str(foreign_co) not in ts and str(foreign_co) not in mine
    # The workspace's own company is for its staff, not for outside representatives.
    own_co = str(await _q("select company_id from mytrakin.tenants where id = :t", t=await _home()))
    assert own_co not in ts and own_co not in mine
    local = await _local_company("Helper Local")
    ts, mine = await _helper_sets("client_user", local)
    assert str(local) in ts and str(local) in mine
    ts, mine = await _helper_sets("finance", None)
    assert own_co in ts and own_co in mine


# ----------------------------------------------------------------------------- payments
async def test_only_finance_records_a_payment_on_another_workspaces_invoice(client):
    invoice = uuid.uuid4()
    for role in ("viewer", "approver", "hr"):
        r = await client.post(f"/invoices/{invoice}/client-payment", headers=await _user(role),
                              json={"amount": "10", "paid_on": date.today().isoformat(), "method": "ACH"})
        assert r.status_code == 403, (role, r.text)
    rep = await _user("client_user", await _local_company("Paying Client"))
    r = await client.post(f"/invoices/{invoice}/client-payment", headers=rep,
                          json={"amount": "10", "paid_on": date.today().isoformat(), "method": "ACH"})
    assert r.status_code == 403, r.text
    # Finance gets past the role check (this invoice simply doesn't exist).
    r = await client.post(f"/invoices/{invoice}/client-payment", headers=await _user("finance"),
                          json={"amount": "10", "paid_on": date.today().isoformat(), "method": "ACH"})
    assert r.status_code == 404, r.text


async def test_payment_function_refuses_non_finance_roles():
    async with get_engine().connect() as conn:
        uid = (await conn.execute(text("select id from auth.users where email = 'admin@example.com'"))).scalar()
        await conn.execute(text("select mytrakin.begin_request(:u, :t, 'viewer')"), {"u": uid, "t": await _home()})
        res = (await conn.execute(text(
            "select mytrakin.client_record_payment(:i, 10, current_date, 'ACH', null, :u)"),
            {"i": uuid.uuid4(), "u": uid})).scalar()
        await conn.rollback()
    res = res if isinstance(res, dict) else json.loads(res)
    assert res["error"] == "forbidden"


# ----------------------------------------------------------------------------- timesheets
async def _week_for(end_client, other_end_client=None, placed_by_approved=False) -> uuid.UUID:
    """A submitted week whose hours are on a placement with `end_client`. With
    `other_end_client`, the consultant also has a placement (no hours this week) there."""
    home = await _home()
    sunday = date.today() - timedelta(days=(date.today().isoweekday() % 7) + 21)
    async with get_engine().begin() as conn:
        k = (await conn.execute(text(
            """insert into mytrakin.consultants (tenant_id, full_name, engagement, status)
               values (:t, 'Two Clients', 'w2_contract', 'active') returning id"""), {"t": home})).scalar()
        placements = {}
        for ec in filter(None, (end_client, other_end_client)):
            pj = (await conn.execute(text(
                """insert into mytrakin.projects (tenant_id, code, name, client_company_id)
                   values (:t, :code, 'Links project', :c) returning id"""),
                {"t": home, "code": f"PJ-{uuid.uuid4().hex[:8]}", "c": ec})).scalar()
            placements[ec] = (await conn.execute(text(
                """insert into mytrakin.placements (tenant_id, consultant_id, project_id, start_date, end_client_company_id,
                                                  ar_company_id, status)
                   values (:t, :k, :p, :s, :ec, :ec, 'active') returning id"""),
                {"t": home, "k": k, "p": pj, "s": sunday - timedelta(days=60), "ec": ec})).scalar()
        ts = (await conn.execute(text(
            """insert into mytrakin.timesheets (tenant_id, consultant_id, week_start, status, submitted_at, placed_by_approved)
               values (:t, :k, :w, 'submitted', now(), :pb) returning id"""),
            {"t": home, "k": k, "w": sunday, "pb": placed_by_approved})).scalar()
        for d in range(1, 6):
            await conn.execute(text(
                """insert into mytrakin.timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
                   values (:t, :ts, :p, :d, 8)"""),
                {"t": home, "ts": ts, "p": placements[end_client], "d": sunday + timedelta(days=d)})
    return ts


async def test_end_client_approval_never_counts_as_the_placing_companys(client):
    end_client = await _local_company("Approving End Client")
    rep = await _user("client_user", end_client)
    ts = await _week_for(end_client)
    r = await client.post(f"/timesheets/{ts}/approve", headers=rep)
    assert r.status_code == 409 and r.json()["error"]["code"] == "awaiting_placed_by", r.text
    assert await _q("select placed_by_approved from mytrakin.timesheets where id = :i", i=ts) is False
    # A representative of a company that isn't this week's end client can't approve it at all.
    stranger = await _user("client_user", await _local_company("Unrelated Client"))
    assert (await client.post(f"/timesheets/{ts}/approve", headers=stranger)).status_code in (403, 404)


async def test_end_client_acts_only_on_weeks_of_its_own_placements(client):
    worked_for, also_placed_with = await _local_company("Worked For"), await _local_company("Old Client")
    ts = await _week_for(worked_for, also_placed_with, placed_by_approved=True)
    other_rep = await _user("client_user", also_placed_with)
    assert (await client.post(f"/timesheets/{ts}/client-link", headers=other_rep)).status_code == 403
    refused = await client.post(f"/timesheets/{ts}/client-decision", headers=other_rep, json={"decision": "approve"})
    assert refused.status_code == 403, refused.text
    assert str(ts) not in {str(r["timesheet_id"]) for r in (await client.get("/timesheets/client-queue", headers=other_rep)).json()}

    rep = await _user("client_user", worked_for)
    assert str(ts) in {str(r["timesheet_id"]) for r in (await client.get("/timesheets/client-queue", headers=rep)).json()}
    link = await client.post(f"/timesheets/{ts}/client-link", headers=rep)
    assert link.status_code == 200, link.text


async def test_an_acceptance_stops_counting_once_the_agreement_leaves_force():
    """Leaving accepted/active clears who accepted it, so a later status change can't bring the acceptance back."""
    home = await _home()
    co = await _local_company(f"Clears {uuid.uuid4().hex[:6]}")
    aid = await _q("""insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, status)
                      values (:t, :code, 'msa', :c, 'buyer', 'pending') returning id""",
                   t=home, code=f"MSA-{uuid.uuid4().hex[:6]}", c=co)
    user = await _q("select id from auth.users limit 1")
    await _q("update mytrakin.agreements set status = 'accepted', accepted_by = :u, accepted_on = now() where id = :a returning id",
             u=user, a=aid)
    assert await _q("select accepted_by from mytrakin.agreements where id = :a", a=aid) == user
    await _q("update mytrakin.agreements set status = 'terminated' where id = :a returning id", a=aid)
    await _q("update mytrakin.agreements set status = 'accepted' where id = :a returning id", a=aid)
    assert await _q("select accepted_by from mytrakin.agreements where id = :a", a=aid) is None
