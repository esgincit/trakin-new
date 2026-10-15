"""Company onboarding: Business IDs, W-9 upload + extraction, strict activation gates,
TIN shielding, company members, and the associated-businesses list."""

from __future__ import annotations

import itertools

from fpdf import FPDF


def w9_pdf(ein: str = "12-3456789", name: str = "Acme Staffing LLC") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10,
        "Form W-9 (Rev. 2018) Request for Taxpayer Identification Number\n"
        f"1 Name (as shown on your income tax return): {name}\n"
        "2 Business name/disregarded entity name: Acme Staffing\n"
        "3a Check appropriate box: Limited liability company\n"
        "5 Address (number, street): 4100 Commerce Street\n"
        "6 City, state, and ZIP code: Dallas, TX 75207\n"
        "Part I Taxpayer Identification Number\n"
        f"Employer identification number: {ein}")
    return bytes(pdf.output())


_counter = itertools.count(1)


async def _new_company(client, auth) -> dict:
    n = next(_counter)
    response = await client.post("/companies", headers=auth("admin"), json={
        "name": f"Acme Staffing {n} LLC", "kind": "vendor", "domain": f"acme{n}.example",
        "business_type": "LLC", "dba": "Acme Staffing", "address": "4100 Commerce Street, Dallas, TX",
        "state": "TX", "contact_name": "A. Owner", "contact_email": f"owner@acme{n}.example",
        "contact_phone": "555-0100"})
    assert response.status_code == 201, response.text
    company = response.json()
    assert company["business_code"].startswith("C-"), company
    assert company["status"] == "onboarding"
    return company


async def test_company_gets_business_id_and_owner(client, auth):
    company = await _new_company(client, auth)
    members = (await client.get(f"/companies/{company['id']}/members", headers=auth("admin"))).json()
    assert [m for m in members if m["company_role"] in ("owner", "super_admin") and m["status"] == "active"], members


async def test_activation_is_blocked_until_verified(client, auth):
    company = await _new_company(client, auth)
    response = await client.post(f"/companies/{company['id']}/activate", headers=auth("admin"), json={})
    assert response.status_code == 422, response.text
    assert "verification_failed" in response.text


async def test_w9_upload_extract_verify_activate(client, auth):
    admin, finance = auth("admin"), auth("finance")
    company = await _new_company(client, auth)
    cid = company["id"]

    uploaded = await client.post(f"/companies/{cid}/w9", headers=admin,
                                 files={"file": ("w9.pdf", w9_pdf(), "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    extraction = uploaded.json()["extraction"]
    assert extraction["engine"] == "pdf-text", extraction
    assert extraction["legal_name"] == "Acme Staffing LLC", extraction
    assert extraction["tin"] == "12-3456789", extraction
    assert uploaded.json()["w9_status"] == "submitted"

    # Correct + confirm the tax details (the review step).
    tax = await client.patch(f"/companies/{cid}/tax", headers=finance, json={
        "tax_classification": "Limited liability company", "tin": "12-3456789", "tin_type": "ein",
        "tax_address": "4100 Commerce Street, Dallas, TX 75207", "ein": "12-3456789"})
    assert tax.status_code == 200, tax.text
    assert tax.json()["tin"] == "12-3456789"

    # Staff verify the W-9, then activation passes every gate.
    decided = await client.post(f"/companies/{cid}/w9/decision", headers=finance,
                                json={"decision": "verified"})
    assert decided.status_code == 200, decided.text
    activated = await client.post(f"/companies/{cid}/activate", headers=admin, json={})
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["business_code"] == company["business_code"]


async def test_tin_is_shielded_from_non_privileged(client, auth):
    admin, finance = auth("admin"), auth("finance")
    companies = (await client.get("/companies", headers=admin)).json()
    bright = next(c for c in companies if c["name"] == "BrightPath Tech LLC")
    patched = await client.patch(f"/companies/{bright['id']}/tax", headers=finance,
                                 json={"tin": "98-7654321", "tin_type": "ein"})
    assert patched.status_code == 200, patched.text

    consultant = await client.get(f"/companies/{bright['id']}", headers=auth("consultant"))
    assert consultant.status_code == 200, consultant.text
    body = consultant.json()
    assert body["tin"] is not None and body["tin"].endswith("4321") and "98" not in body["tin"], body["tin"]
    assert body["w9_data"] == {}

    vendor = await client.get(f"/companies/{bright['id']}", headers=auth("vendor"))
    assert vendor.json()["tin"] == "98-7654321"   # their own company: full view


async def test_last_owner_is_protected_and_members_managed(client, auth):
    admin = auth("admin")
    company = await _new_company(client, auth)
    cid = company["id"]
    owner = next(m for m in (await client.get(f"/companies/{cid}/members", headers=admin)).json()
                 if m["company_role"] == "owner")

    # A second owner with an account is active immediately (a bare e-mail invite stays
    # "invited" until they sign up, and pending invites don't satisfy the owner rule).
    invited = await client.post(f"/companies/{cid}/members", headers=admin,
                                json={"email": "finance@example.com", "company_role": "owner"})
    assert invited.status_code == 201, invited.text

    # Demoting the invited owner is fine while the creator (Super Admin) remains;
    # removing the last privileged member is not.
    demote = await client.patch(f"/companies/{cid}/members/{owner['id']}", headers=admin,
                                json={"company_role": "member"})
    assert demote.status_code == 200, demote.text
    members = (await client.get(f"/companies/{cid}/members", headers=admin)).json()
    creator = next(m for m in members if m["company_role"] == "super_admin")
    remove_last = await client.delete(f"/companies/{cid}/members/{creator['id']}", headers=admin)
    assert remove_last.status_code == 400, remove_last.text


async def test_my_businesses_lists_every_role(client, auth):
    vendor_businesses = (await client.get("/my/businesses", headers=auth("vendor"))).json()
    assert any(b["company_name"] == "BrightPath Tech LLC" for b in vendor_businesses), vendor_businesses
    consultant_businesses = (await client.get("/my/businesses", headers=auth("consultant"))).json()
    assert any(b["company_name"] == "BrightPath Tech LLC" for b in consultant_businesses), consultant_businesses
    outsider = await client.get("/my/businesses", headers=auth("outsider"))
    assert outsider.status_code == 200 and outsider.json() == []


async def _us_company(client, auth, n: int, ein: str = "22-3334401") -> dict:
    """Full US flow: session → W-9 → details → OTP → authorize → created."""
    admin = auth("admin")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "US"})).json()
    sid = session["id"]
    uploaded = await client.post(f"/onboarding/sessions/{sid}/w9", headers=admin,
                                 files={"file": ("w9.pdf", w9_pdf(ein, f"Flow {n} Staffing LLC"), "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    body = {"kind": "vendor", "domain": f"flow{n}.example", "company_email": f"billing@flow{n}.example",
            "dba": "Flow", "ein": ein}
    details = await client.patch(f"/onboarding/sessions/{sid}", headers=admin, json=body)
    assert details.status_code == 200, details.text
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=admin, json={})).json()
    assert "test_code" in code, code
    verified = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin,
                                 json={"code": code["test_code"]})
    assert verified.status_code == 200, verified.text
    created = await client.post(f"/onboarding/sessions/{sid}/complete", headers=admin,
                                json={"authorized": True})
    assert created.status_code == 201, created.text
    return created.json()


async def test_us_flow_creates_company_and_super_admin(client, auth):
    company = await _us_company(client, auth, 1)
    assert company["business_code"].startswith("C-"), company
    assert company["status"] == "onboarding"
    assert company["company_role"] == "super_admin"
    members = (await client.get(f"/companies/{company['id']}/members", headers=auth("admin"))).json()
    assert any(m["company_role"] == "super_admin" and m["status"] == "active" for m in members), members
    businesses = (await client.get("/my/businesses", headers=auth("admin"))).json()
    assert any(b["company_id"] == company["id"] and b["company_role"] == "super_admin" for b in businesses)


async def test_us_flow_rejects_duplicate_ein(client, auth):
    admin = auth("admin")
    await _us_company(client, auth, 2, ein="22-3334407")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "US"})).json()
    dup = await client.post(f"/onboarding/sessions/{session['id']}/w9", headers=admin,
                            files={"file": ("w9.pdf", w9_pdf("22-3334407"), "application/pdf")})
    assert dup.status_code == 409 and "already registered" in dup.text, dup.text


async def test_india_step1_saves_without_email(client, auth):
    """Step 1 (MCA details) has no e-mail field — e-mail becomes mandatory at step 2."""
    admin = auth("admin")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "IN"})).json()
    step1 = await client.patch(f"/onboarding/sessions/{session['id']}", headers=admin, json={
        "step": 1, "kind": "vendor", "legal_name": "Step One Labs Pvt Ltd", "cin": "U72902MH2021PTC654322",
        "street": "3 Main Road", "city": "Pune", "state": "Maharashtra", "pin": "411001"})
    assert step1.status_code == 200, step1.text
    step2 = await client.patch(f"/onboarding/sessions/{session['id']}", headers=admin, json={
        "step": 2, "kind": "vendor", "domain": "stepone.example", "dba": "Step One"})
    assert step2.status_code == 422 and "company_email" in step2.text, step2.text


async def test_india_flow_moa_cin_otp(client, auth):
    admin = auth("admin")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "IN"})).json()
    sid = session["id"]

    bad = await client.patch(f"/onboarding/sessions/{sid}", headers=admin, json={
        "kind": "vendor", "legal_name": "Mumbai Labs Pvt Ltd", "cin": "bogus",
        "street": "1 Linking Road", "city": "Mumbai", "state": "Maharashtra", "pin": "400050"})
    assert bad.status_code == 422, bad.text

    good = await client.patch(f"/onboarding/sessions/{sid}", headers=admin, json={
        "kind": "vendor", "legal_name": "Mumbai Labs Pvt Ltd", "cin": "U72900MH2020PTC123456",
        "street": "1 Linking Road", "city": "Mumbai", "state": "Maharashtra", "pin": "400050",
        "domain": "mumbailabs.example", "company_email": "hello@mumbailabs.example", "dba": "Mumbai Labs"})
    assert good.status_code == 200, good.text

    # MOA is mandatory (checked after the e-mail gate).
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=admin, json={})).json()
    wrong = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin,
                              json={"code": "000000"})
    assert wrong.status_code == 400, wrong.text
    verified = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin,
                                 json={"code": code["test_code"]})
    assert verified.status_code == 200, verified.text
    no_moa = await client.post(f"/onboarding/sessions/{sid}/complete", headers=admin,
                               json={"authorized": True})
    assert no_moa.status_code == 422 and "MOA" in no_moa.text, no_moa.text
    moa = await client.post(f"/onboarding/sessions/{sid}/moa", headers=admin,
                            files={"file": ("moa.pdf", w9_pdf(), "application/pdf")})
    assert moa.status_code == 200, moa.text

    refused = await client.post(f"/onboarding/sessions/{sid}/complete", headers=admin,
                                json={"authorized": False})
    assert refused.status_code == 400, refused.text
    created = await client.post(f"/onboarding/sessions/{sid}/complete", headers=admin,
                                json={"authorized": True})
    assert created.status_code == 201, created.text
    body = created.json()
    detail = (await client.get(f"/companies/{body['id']}", headers=admin)).json()
    assert detail["country"] == "IN" and detail["cin"] == "U72900MH2020PTC123456", detail
    assert body["company_role"] == "super_admin"


def w9_form_pdf() -> bytes:
    """IRS-layout W-9 with real AcroForm values: filled fields, a blank field, per-digit
    TIN boxes and a checked classification box."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 60

    def label(text: str):
        nonlocal y
        page.insert_text((72, y), text, fontsize=9)
        y += 14

    def field(name: str, value: str):
        nonlocal y
        widget = pymupdf.Widget()
        widget.field_name = name
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = value
        widget.rect = pymupdf.Rect(72, y, 512, y + 16)
        page.add_widget(widget)
        y += 34

    label("1 Name (as shown on your income tax return)")
    field("f_name", "Acme Staffing LLC")
    label("2 Business name/disregarded entity name, if different from above")
    field("f_dba", "")   # blank: must come back null, not the next label
    label("3a Check appropriate box for federal tax classification")
    page.insert_text((86, y + 11), "S Corporation", fontsize=9)
    box = pymupdf.Widget()
    box.field_name = "c_scorp"
    box.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
    box.field_value = "Yes"
    box.rect = pymupdf.Rect(72, y, 82, y + 10)
    page.add_widget(box)
    y += 34
    label("5 Address (number, street, and apt. or suite no.)")
    field("f_addr", "4100 Commerce Street")
    label("6 City, state, and ZIP code")
    field("f_city", "Dallas, TX 75207")
    label("Employer identification number")
    x = 72
    for i, digit in enumerate("123456789"):
        widget = pymupdf.Widget()
        widget.field_name = f"f_ein_{i}"
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = digit
        widget.rect = pymupdf.Rect(x, y, x + 14, y + 16)
        page.add_widget(widget)
        x += 16
    raw = doc.tobytes()
    doc.close()
    return raw


async def test_w9_form_fields_map_exactly(client, auth):
    admin = auth("admin")
    company = await _new_company(client, auth)
    uploaded = await client.post(f"/companies/{company['id']}/w9", headers=admin,
                                 files={"file": ("w9.pdf", w9_form_pdf(), "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    extraction = uploaded.json()["extraction"]
    assert extraction["engine"] == "form-fields", extraction
    assert extraction["legal_name"] == "Acme Staffing LLC", extraction
    assert extraction["dba"] is None, extraction                       # blank stays blank
    assert extraction["tax_classification"] == "S Corporation", extraction
    assert extraction["tin"] == "12-3456789" and extraction["tin_type"] == "ein", extraction
    assert extraction["address"] == "4100 Commerce Street", extraction
    assert (extraction["city"], extraction["state"], extraction["zip"]) == ("Dallas", "TX", "75207"), extraction
    assert extraction["needs_review"] == [], extraction


async def test_company_member_without_workspace_can_start_onboarding(client, auth):
    """A freelancer whose only tie is a company membership (no workspace invite)
    can still start — and list — an onboarding session (used to 403 no_access)."""
    from sqlalchemy import text

    from app.db import get_engine

    async with get_engine().begin() as conn:
        uid = (await conn.execute(
            text("select id from auth.users where email = 'someone@else.example'"))).scalar()
        company = (await conn.execute(
            text("select id, tenant_id from mytrakin.companies where name = 'BrightPath Tech LLC'"))).mappings().first()
        await conn.execute(
            text("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                    values (:t, :c, :u, 'member', 'active')"""),
            {"t": company["tenant_id"], "c": company["id"], "u": uid})
    try:
        created = await client.post("/onboarding/sessions", headers=auth("outsider"), json={"country": "IN"})
        assert created.status_code == 201, created.text
        mine = await client.get("/onboarding/sessions", headers=auth("outsider"))
        assert mine.status_code == 200 and any(s["id"] == created.json()["id"] for s in mine.json()), mine.text
        businesses = await client.get("/my/businesses", headers=auth("outsider"))
        assert any(b["company_name"] == "BrightPath Tech LLC" and b["company_role"] == "member"
                   for b in businesses.json()), businesses.text
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.onboarding_sessions where created_by = :u"), {"u": uid})
            await conn.execute(text("delete from mytrakin.company_members where user_id = :u"), {"u": uid})


async def test_w9_spaced_digit_ein_parses(client, auth):
    """Digit-box renderings ("22 333 4409") must still yield the EIN."""
    admin = auth("admin")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "US"})).json()
    uploaded = await client.post(f"/onboarding/sessions/{session['id']}/w9", headers=admin,
                                 files={"file": ("w9.pdf", w9_pdf("22 333 4409"), "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    extraction = uploaded.json()["extraction"]
    assert extraction["tin"] == "22-3334409" and extraction["tin_type"] == "ein", extraction


async def test_us_manual_entry_completes_without_upload(client, auth):
    """Unparseable W-9s fall back to typed details (manual: true) — still gated on OTP."""
    admin = auth("admin")
    session = (await client.post("/onboarding/sessions", headers=admin, json={"country": "US"})).json()
    sid = session["id"]
    details = await client.patch(f"/onboarding/sessions/{sid}", headers=admin, json={
        "manual": True, "kind": "vendor", "legal_name": "Manual Entry LLC", "business_type": "LLC",
        "tin_type": "ein", "ein": "22-3334411", "address": "9 Manual Rd", "city": "Dallas",
        "state": "TX", "zip": "75207", "domain": "manualentry.example",
        "company_email": "billing@manualentry.example", "dba": "Manual"})
    assert details.status_code == 200, details.text
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=admin, json={})).json()
    verified = await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=admin,
                                 json={"code": code["test_code"]})
    assert verified.status_code == 200, verified.text
    created = await client.post(f"/onboarding/sessions/{sid}/complete", headers=admin,
                                json={"authorized": True})
    assert created.status_code == 201, created.text
    assert created.json()["company_role"] == "super_admin"
    detail = (await client.get(f"/companies/{created.json()['id']}", headers=admin)).json()
    assert detail["tin"] == "22-3334411" and detail["w9_status"] == "submitted", detail
