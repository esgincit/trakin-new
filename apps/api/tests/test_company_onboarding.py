"""Company onboarding: Business IDs, W-9 upload + extraction, strict activation gates,
TIN shielding, company members, and the associated-businesses list."""

from __future__ import annotations

import itertools

from fpdf import FPDF


def w9_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10,
        "Form W-9 (Rev. 2018) Request for Taxpayer Identification Number\n"
        "1 Name (as shown on your income tax return): Acme Staffing LLC\n"
        "2 Business name/disregarded entity name: Acme Staffing\n"
        "3a Check appropriate box: Limited liability company\n"
        "5 Address (number, street): 4100 Commerce Street\n"
        "6 City, state, and ZIP code: Dallas, TX 75207\n"
        "Part I Taxpayer Identification Number\n"
        "Employer identification number: 12-3456789")
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
    assert [m for m in members if m["company_role"] == "owner" and m["status"] == "active"], members


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

    # Demoting the only *other* owner down to one is fine; removing the last one is not.
    demote = await client.patch(f"/companies/{cid}/members/{owner['id']}", headers=admin,
                                json={"company_role": "member"})
    assert demote.status_code == 200, demote.text
    second = (await client.get(f"/companies/{cid}/members", headers=admin)).json()
    second_owner = next(m for m in second if m["company_role"] == "owner")
    remove_last = await client.delete(f"/companies/{cid}/members/{second_owner['id']}", headers=admin)
    assert remove_last.status_code == 400, remove_last.text


async def test_my_businesses_lists_every_role(client, auth):
    vendor_businesses = (await client.get("/my/businesses", headers=auth("vendor"))).json()
    assert any(b["company_name"] == "BrightPath Tech LLC" for b in vendor_businesses), vendor_businesses
    consultant_businesses = (await client.get("/my/businesses", headers=auth("consultant"))).json()
    assert any(b["company_name"] == "BrightPath Tech LLC" for b in consultant_businesses), consultant_businesses
    outsider = await client.get("/my/businesses", headers=auth("outsider"))
    assert outsider.status_code == 200 and outsider.json() == []


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
