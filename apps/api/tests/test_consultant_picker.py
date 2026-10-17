"""Onboarding a consultant picks a registered person rather than typing a name
(PLAN CON-02): the details come from their profile, so a consultant cannot be
created as a near-duplicate of somebody already here. The person may be new to
this workspace -- that is what onboarding is for."""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text

from app.db import get_engine

DEMO = {"admin": "admin@example.com", "finance": "finance@example.com", "consultant": "ravi.kumar@example.com"}


async def _new_person(key: str, name: str, email: str | None = None, phone: str | None = None) -> str:
    """A registered user with no membership anywhere -- somebody brand new to myTrakIn
    apart from having an account. Removed again by _forget()."""
    email = email or f"{key}@elsewhere.example"
    async with get_engine().begin() as conn:
        uid = (await conn.execute(
            text("""insert into auth.users (email, raw_user_meta_data)
                    values (:e, cast(:m as jsonb)) returning id"""),
            {"e": email, "m": json.dumps({"full_name": name})})).scalar()
        if phone:
            await conn.execute(text("update mytrakin.profiles set phone = :p where id = :u"), {"p": phone, "u": uid})
    return str(uid)


async def _forget(user_id: str) -> None:
    """Remove the user; their profile, membership and consultant link cascade with it."""
    async with get_engine().begin() as conn:
        await conn.execute(text("delete from mytrakin.consultants where user_id = :u"), {"u": user_id})
        await conn.execute(text("delete from auth.users where id = :u"), {"u": user_id})


async def _membership(user_id: str) -> dict | None:
    async with get_engine().begin() as conn:
        row = (await conn.execute(
            text("select tenant_id, role, status, consultant_id from mytrakin.memberships where user_id = :u"),
            {"u": user_id})).mappings().first()
    return dict(row) if row else None


async def test_candidates_are_registered_people_with_their_uid(client, auth):
    """The picker finds people by name, U-ID or e-mail, each result showing its U-ID."""
    async with get_engine().begin() as conn:
        codes = dict((await conn.execute(text(
            """select email, uc.code from mytrakin.profiles p
                 join mytrakin.user_codes uc on uc.user_id = p.id
                where email in ('admin@example.com', 'finance@example.com', 'ravi.kumar@example.com')"""),
        )).all())

    # Search by e-mail.
    by_email = (await client.get("/consultants/candidates",
                                 params={"q": DEMO["consultant"]}, headers=auth("admin"))).json()
    assert [p["user_code"] for p in by_email] == [codes[DEMO["consultant"]]], by_email

    # Search by U-ID.
    by_uid = (await client.get("/consultants/candidates",
                               params={"q": codes[DEMO["finance"]]}, headers=auth("admin"))).json()
    assert [p["email"] for p in by_uid] == [DEMO["finance"]], by_uid

    # Search by name, and every result carries a U-ID and the details onboarding needs.
    by_name = (await client.get("/consultants/candidates",
                                params={"q": "@example.com"}, headers=auth("admin"))).json()
    assert by_name, by_name
    assert all(p["user_code"] and p["user_id"] and p["email"] for p in by_name), by_name
    assert {p["email"] for p in by_name} >= set(codes), by_name

    # Nobody else.
    assert (await client.get("/consultants/candidates",
                             params={"q": "zzzz no such person"}, headers=auth("admin"))).json() == []

    # A search term is required, so this cannot page through the whole user list.
    assert (await client.get("/consultants/candidates", headers=auth("admin"))).status_code == 422
    assert (await client.get("/consultants/candidates", params={"q": "a"}, headers=auth("admin"))).status_code == 422

    # Not a role that onboards people.
    assert (await client.get("/consultants/candidates",
                             params={"q": "@example.com"}, headers=auth("consultant"))).status_code == 403


async def test_someone_from_another_workspace_can_be_onboarded(client, auth):
    """The picker searches the whole platform: a person with an account elsewhere is
    found and onboarded here, which is what gives them access to this workspace."""
    user = await _new_person("zebedee", "Zebedee Stranger", phone="+1 555 0100")
    try:
        found = (await client.get("/consultants/candidates",
                                  params={"q": "Zebedee"}, headers=auth("admin"))).json()
        assert [p["user_id"] for p in found] == [user], found
        assert found[0]["in_workspace"] is False, found          # they have no access here yet
        assert found[0]["phone"] == "+1 555 0100", found

        response = await client.post("/consultants", headers=auth("admin"), json={
            "user_id": user, "engagement": "w2_contract", "start_date": str(date.today())})
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["user_id"] == user, created

        # Their details came from the profile, not from the form.
        assert created["full_name"] == "Zebedee Stranger", created
        assert created["email"] == "zebedee@elsewhere.example", created
        assert created["phone"] == "+1 555 0100", created

        # They now have access here, as a consultant.
        again = (await client.get("/consultants/candidates",
                                  params={"q": "Zebedee"}, headers=auth("admin"))).json()
        assert again[0]["in_workspace"] is True, again
        membership = await _membership(user)
        assert membership["role"] == "consultant" and membership["status"] == "active", membership
    finally:
        await _forget(user)


async def test_a_person_cannot_be_onboarded_twice(client, auth):
    """The same person is not a second consultant here; rehire covers that."""
    user = await _new_person("twice", "Wilhelmina Twice")
    body = {"user_id": user, "engagement": "w2_contract", "start_date": str(date.today())}
    try:
        first = await client.post("/consultants", headers=auth("admin"), json=body)
        assert first.status_code == 201, first.text
        again = await client.post("/consultants", headers=auth("admin"), json=body)
        assert again.status_code == 409, again.text
        assert "already a consultant" in again.text, again.text
    finally:
        await _forget(user)


async def test_onboarding_keeps_an_existing_role(client, auth):
    """Someone who is already staff here keeps their role and gains the consultant link."""
    user = await _new_person("staffer", "Wilhelmina Staffer")
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(
            text("""select tenant_id from mytrakin.memberships
                     where user_id = (select user_id from mytrakin.profiles where email = :e) limit 1"""),
            {"e": DEMO["admin"]})).scalar()
        await conn.execute(
            text("insert into mytrakin.memberships (tenant_id, user_id, role, title, status) "
                 "values (:t, :u, 'viewer', 'Analyst', 'active')"), {"t": tenant, "u": user})
    try:
        response = await client.post("/consultants", headers=auth("admin"), json={
            "user_id": user, "engagement": "w2_contract", "start_date": str(date.today())})
        assert response.status_code == 201, response.text
        membership = await _membership(user)
        assert membership["role"] == "viewer", membership          # not demoted to consultant
        assert membership["consultant_id"] == response.json()["id"], membership
    finally:
        await _forget(user)


async def test_only_roles_that_onboard_people_may_search(client, auth):
    """HR may use the picker; finance and consultants may not."""
    async def set_role(role: str) -> None:
        async with get_engine().begin() as conn:
            await conn.execute(text("update mytrakin.memberships set role = :r where user_id = "
                                    "(select user_id from mytrakin.profiles where email = :e)"),
                               {"r": role, "e": DEMO["finance"]})

    try:
        assert (await client.get("/consultants/candidates",
                                 params={"q": "@example.com"}, headers=auth("finance"))).status_code == 403
        assert (await client.get("/consultants/candidates",
                                 params={"q": "@example.com"}, headers=auth("consultant"))).status_code == 403
        await set_role("hr")
        assert (await client.get("/consultants/candidates",
                                 params={"q": "@example.com"}, headers=auth("finance"))).status_code == 200
    finally:
        await set_role("finance")


async def test_the_old_free_text_payload_is_rejected(client, auth):
    """Name and e-mail alone are no longer enough: a consultant is a registered user."""
    response = await client.post("/consultants", headers=auth("admin"), json={
        "full_name": "Typed By Hand", "email": "typed@example.com",
        "engagement": "w2_contract", "start_date": str(date.today())})
    assert response.status_code == 422, response.text
