"""Security review fixes (scan 2026-11-07, team decisions 2026-11-11)."""

from __future__ import annotations


async def test_five_wrong_codes_cancel_the_company_email_code(client, auth):
    """F14: the wrong-code counter used to be rolled back with the error, so guessing never stopped."""
    admin = auth("admin")
    sid = (await client.post("/onboarding/sessions", headers=admin, json={"country": "IN"})).json()["id"]
    assert (await client.patch(f"/onboarding/sessions/{sid}", headers=admin, json={
        "kind": "vendor", "legal_name": "Guess Labs Pvt Ltd", "cin": "U72900MH2020PTC654321",
        "street": "1 Linking Road", "city": "Mumbai", "state": "Maharashtra", "pin": "400050",
        "domain": "guesslabs.example", "company_email": "hello@guesslabs.example", "dba": "Guess Labs"})).status_code == 200
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=admin, json={})).json()["test_code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin, json={"code": wrong})
        assert r.status_code == 400 and r.json()["error"]["code"] == "code_wrong", r.text
    locked = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin, json={"code": code})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts", locked.text
