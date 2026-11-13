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


async def test_policy_names_are_plain_text_and_files_must_be_pdfs(client, auth):
    """F4: a policy's name and version may only hold letters, numbers, spaces, dashes and dots."""
    admin = auth("admin")
    form = {"effective_on": "2026-11-11", "applies_to": "w2_fulltime"}
    pdf = ("p.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")
    bad = await client.post("/policies", headers=admin, data={**form, "name": "x/../../y", "version": "1"},
                            files={"file": pdf})
    assert bad.status_code == 400 and "letters, numbers" in bad.text, bad.text
    not_pdf = await client.post("/policies", headers=admin, data={**form, "name": "Leave Policy", "version": "2.0"},
                                files={"file": ("p.pdf", b"<html>", "application/pdf")})
    assert not_pdf.status_code == 400, not_pdf.text
    ok = await client.post("/policies", headers=admin, data={**form, "name": "Leave Policy", "version": "2.0"},
                           files={"file": pdf})
    assert ok.status_code == 201 and ok.json()["file_path"].endswith("/policies/leave-policy-2.0.pdf"), ok.text
