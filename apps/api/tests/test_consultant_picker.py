"""Onboarding a consultant picks a registered person rather than typing a name
(PLAN CON-02): the details come from their profile, so a consultant cannot be
created as a near-duplicate of somebody already here."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.db import get_engine


async def _consultant_ids() -> set[str]:
    async with get_engine().begin() as conn:
        return {r[0] for r in (await conn.execute(text("select id from mytrakin.consultants"))).all()}


def _fresh_candidate(people: list[dict]) -> dict:
    """Someone registered here who is not a consultant yet."""
    fresh = [p for p in people if p["already_consultant"] == 0]
    assert fresh, f"no fresh candidate among {[(p['full_name'], p['already_consultant']) for p in people]}"
    return fresh[0]


async def test_candidates_are_registered_people_with_their_uid(client, auth):
    """The picker lists people who already have an account here, each with its U-ID."""
    people = (await client.get("/consultants/candidates", headers=auth("admin"))).json()
    assert people, people
    assert all(p["user_code"] for p in people), people           # everyone shows a U-ID
    assert all(p["user_id"] and p["email"] for p in people), people

    # Search by name.
    sample = people[0]
    one = (await client.get("/consultants/candidates", params={"q": sample["full_name"][:5]}, headers=auth("admin"))).json()
    assert any(p["user_id"] == sample["user_id"] for p in one), one

    # Search by U-ID.
    by_uid = (await client.get("/consultants/candidates",
                               params={"q": sample["user_code"]}, headers=auth("admin"))).json()
    assert [p["user_id"] for p in by_uid] == [sample["user_id"]], by_uid

    # Nobody else.
    assert (await client.get("/consultants/candidates",
                             params={"q": "zzzz no such person"}, headers=auth("admin"))).json() == []

    # Not a role that onboards people.
    assert (await client.get("/consultants/candidates", headers=auth("consultant"))).status_code == 403


async def test_onboarding_takes_their_details_from_the_profile(client, auth):
    """Picking someone fills in their name, e-mail and mobile, and links their account."""
    before = await _consultant_ids()
    person = _fresh_candidate((await client.get("/consultants/candidates", headers=auth("admin"))).json())
    response = await client.post("/consultants", headers=auth("admin"), json={
        "user_id": person["user_id"], "engagement": "w2_contract", "start_date": str(date.today())})
    assert response.status_code == 201, response.text
    created = response.json()

    async with get_engine().begin() as conn:
        row = (await conn.execute(
            text("""select c.user_id, c.full_name, c.email, c.phone, m.status
                     from mytrakin.consultants c
                     left join mytrakin.memberships m on m.consultant_id = c.id
                    where c.id = :id"""),
            {"id": created["id"]})).mappings().first()
    assert str(row["user_id"]) == person["user_id"], row
    assert row["full_name"] == person["full_name"], row
    assert row["email"] == person["email"], row
    # An account already exists, so access is active at once — nothing to claim at sign-in.
    assert row["status"] == "active", row
    assert created["user_id"] == person["user_id"], created

    for cid in await _consultant_ids() - before:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.consultants where id = :id"), {"id": cid})


async def test_a_person_cannot_be_onboarded_twice(client, auth):
    """The same person is not a second consultant here; rehire covers that."""
    person = _fresh_candidate((await client.get("/consultants/candidates", headers=auth("admin"))).json())
    body = {"user_id": person["user_id"], "engagement": "w2_contract", "start_date": str(date.today())}
    first = await client.post("/consultants", headers=auth("admin"), json=body)
    assert first.status_code == 201, first.text
    cid = first.json()["id"]
    try:
        again = await client.post("/consultants", headers=auth("admin"), json=body)
        assert again.status_code == 409, again.text
        assert "already a consultant" in again.text, again.text
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.consultants where id = :id"), {"id": cid})


async def test_someone_outside_the_workspace_cannot_be_onboarded(client, auth):
    """A user id from another workspace is refused — the picker only offers your own."""
    async with get_engine().begin() as conn:
        outsider = (await conn.execute(text(
            """insert into auth.users (email, raw_user_meta_data)
               values ('stranger@elsewhere.example', '{"full_name": "A Stranger"}'::jsonb) returning id"""))).scalar()
    try:
        response = await client.post("/consultants", headers=auth("admin"), json={
            "user_id": str(outsider), "engagement": "w2_contract", "start_date": str(date.today())})
        assert response.status_code == 400, response.text
        assert "isn't registered" in response.text, response.text
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from auth.users where id = :id"), {"id": outsider})


async def test_the_old_free_text_payload_is_rejected(client, auth):
    """Name and e-mail alone are no longer enough: a consultant is a registered user."""
    response = await client.post("/consultants", headers=auth("admin"), json={
        "full_name": "Typed By Hand", "email": "typed@example.com",
        "engagement": "w2_contract", "start_date": str(date.today())})
    assert response.status_code == 422, response.text
