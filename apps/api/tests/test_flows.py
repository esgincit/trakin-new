"""End-to-end business flows through the API, as each role would use them."""

from __future__ import annotations

import io
from datetime import date, timedelta

from fpdf import FPDF
from sqlalchemy import text

from app.db import get_engine
from app.utils import sha256_hex

THIS_WEEK = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)


def small_pdf(title: str = "Master Services Agreement") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, title)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------- dashboards
async def test_dashboard_for_every_role(client, auth):
    for who in ("admin", "finance"):
        response = await client.get("/dashboard", headers=auth(who))
        assert response.status_code == 200, (who, response.text)
    # Vendors and consultants have their own home pages instead.
    assert (await client.get("/dashboard", headers=auth("vendor"))).status_code == 403
    assert (await client.get("/me/consultant", headers=auth("consultant"))).status_code == 200


async def test_every_list_screen_loads(client, auth):
    for path in ("/companies", "/consultants", "/projects", "/placements", "/agreements", "/sows", "/contracts/missing",
                 "/timesheets", "/invoices?direction=ar", "/invoices?direction=ap", "/payments", "/payment-flow",
                 "/envelopes", "/compliance/documents", "/compliance/work-authorization", "/policies", "/registrations",
                 "/reminder-rules", "/notifications", "/users", "/audit", "/workspace", "/data/templates", "/insights",
                 "/network/me", "/network/people", "/network/feed", "/network/connections", "/network/messages"):
        response = await client.get(path, headers=auth("admin"))
        assert response.status_code == 200, (path, response.text)


# ---------------------------------------------------------------------------- timesheet → invoice → payment
async def test_timesheet_to_invoice_to_payment(client, auth):
    consultant, finance = auth("consultant"), auth("finance")

    week = (await client.get("/timesheets/mine", headers=consultant)).json()
    assert len(week["projects"]) == 2
    rows = [{"placement_id": p["placement_id"], "hours": [0, 5, 5, 5, 5, 4, 0] if i == 0 else [0, 3, 3, 3, 3, 4, 0]}
            for i, p in enumerate(week["projects"])]
    saved = await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(THIS_WEEK), "rows": rows})
    assert saved.status_code == 200, saved.text
    submitted = await client.post("/timesheets/mine/submit", params={"week": str(THIS_WEEK)}, headers=consultant, json={})
    assert submitted.json()["status"] == "submitted"

    # Locked once submitted.
    again = await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(THIS_WEEK), "rows": rows})
    assert again.status_code == 409

    review = (await client.get(f"/timesheets/{submitted.json()['id']}", headers=finance)).json()
    assert "checks" in review
    approved = await client.post(f"/timesheets/{submitted.json()['id']}/approve", headers=finance)
    assert approved.status_code == 200, approved.text

    generated = await client.post("/invoices/generate", headers=finance,
                                  json={"period_start": str(THIS_WEEK), "period_end": str(THIS_WEEK + timedelta(days=6))})
    assert generated.status_code == 200, generated.text
    created = generated.json()["created"]
    assert created, "approved hours should produce invoices"

    ar = [r for r in (await client.get("/invoices", params={"direction": "ar"}, headers=finance)).json()
          if r["period_start"] == str(THIS_WEEK) and r["consultant"] == "Ravi Kumar"]
    assert ar
    invoice = ar[0]
    paid = await client.post(f"/invoices/{invoice['id']}/payments", headers=finance,
                             json={"amount": invoice["amount"], "paid_on": str(date.today()), "method": "ACH", "reference": "T-1"})
    assert paid.status_code == 201, paid.text
    detail = (await client.get(f"/invoices/{invoice['id']}", headers=finance)).json()
    assert detail["live_status"] == "paid" and len(detail["payments"]) == 1

    # The vendor sees its AP invoice for the same week but never the AR side.
    vendor_ap = (await client.get("/invoices", params={"direction": "ap"}, headers=auth("vendor"))).json()
    mine = [r for r in vendor_ap if r["period_start"] == str(THIS_WEEK)]
    assert mine and all(r["party"] == "BrightPath Tech LLC" for r in mine)
    vendor_detail = (await client.get(f"/invoices/{mine[0]['id']}", headers=auth("vendor"))).json()
    assert vendor_detail["match"]["billed_to_customer_hours"] is None
    assert vendor_detail["waits_for"] is None


async def test_vendor_sees_the_same_ap_status_as_finance(client, auth):
    """Pay-when-paid: a vendor can't read the client invoice, but must still see "held", never "ready to pay"."""
    finance = {r["id"]: r["live_status"] for r in (await client.get("/invoices", params={"direction": "ap"}, headers=auth("finance"))).json()}
    vendor = (await client.get("/invoices", params={"direction": "ap"}, headers=auth("vendor"))).json()
    assert any(r["live_status"] == "held" for r in vendor), "seed has a held BrightPath invoice"
    for row in vendor:
        assert row["live_status"] == finance[row["id"]], (row["number"], row["live_status"], finance[row["id"]])


async def test_reject_requires_reason_and_returns_week(client, auth):
    finance = auth("finance")
    week = (await client.get("/timesheets", headers=finance)).json()
    anita = next(r for r in week["rows"] if r["full_name"] == "Anita Desai")
    assert anita["status"] == "submitted" and anita["checks"] is not None
    assert (await client.post(f"/timesheets/{anita['id']}/reject", headers=finance, json={})).status_code == 400
    rejected = await client.post(f"/timesheets/{anita['id']}/reject", headers=finance, json={"reason": "Friday is a holiday"})
    assert rejected.json()["status"] == "rejected"


async def test_consultant_can_fix_and_resubmit_a_returned_week(client, auth):
    """A returned (rejected) week must be editable and submittable again by the consultant."""
    consultant, finance = auth("consultant"), auth("finance")
    week = THIS_WEEK + timedelta(days=7)
    mine = (await client.get("/timesheets/mine", params={"week": str(week)}, headers=consultant)).json()
    rows = [{"placement_id": p["placement_id"], "hours": [0, 14, 8, 8, 8, 8, 0] if i == 0 else [0, 0, 0, 0, 0, 0, 0]}
            for i, p in enumerate(mine["projects"])]
    assert (await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(week), "rows": rows})).status_code == 200
    submitted = await client.post("/timesheets/mine/submit", params={"week": str(week)}, headers=consultant, json={})
    assert submitted.status_code == 200, submitted.text
    returned = await client.post(f"/timesheets/{submitted.json()['id']}/reject", headers=finance,
                                 json={"reason": "Monday shows 14 hours"})
    assert returned.json()["status"] == "rejected"

    rows[0]["hours"] = [0, 8, 8, 8, 8, 8, 0]
    fixed = await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(week), "rows": rows})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["status"] == "rejected" and fixed.json()["reject_reason"] == "Monday shows 14 hours"
    again = await client.post("/timesheets/mine/submit", params={"week": str(week)}, headers=consultant, json={})
    assert again.status_code == 200, again.text
    after = (await client.get("/timesheets/mine", params={"week": str(week)}, headers=consultant)).json()
    assert after["status"] == "submitted" and after["reject_reason"] is None
    assert sum(sum(r["hours"]) for r in after["rows"]) == 40

    # Approved and invoiced, the new AR invoices start as drafts: the daily job must not remind the customer
    # about an invoice nobody has sent them yet — only once it is sent.
    assert (await client.post(f"/timesheets/{submitted.json()['id']}/approve", headers=finance)).status_code == 200
    generated = await client.post("/invoices/generate", headers=finance,
                                  json={"period_start": str(week), "period_end": str(week + timedelta(days=6))})
    assert generated.status_code == 200, generated.text
    async with get_engine().begin() as conn:
        draft_id = (await conn.execute(text(
            """select id from mytrakin.invoices where direction = 'ar' and status = 'draft' and period_start = :w limit 1"""),
            {"w": week})).scalar()
        assert draft_id is not None
        await conn.execute(text("update mytrakin.invoices set due_on = current_date + 7 where id = :id"), {"id": draft_id})

    async def reminders() -> int:
        async with get_engine().begin() as conn:
            return (await conn.execute(text(
                "select count(*) from mytrakin.notifications where kind = 'ar_reminder' and ref_id = :id"), {"id": draft_id})).scalar()

    cron = {"Authorization": "Bearer cron-test-secret"}
    assert (await client.get("/cron/daily", headers=cron)).status_code == 200
    assert await reminders() == 0, "a draft invoice must not trigger a customer reminder"
    assert (await client.post(f"/invoices/{draft_id}/send", headers=finance)).status_code == 200
    assert (await client.get("/cron/daily", headers=cron)).status_code == 200
    assert await reminders() == 1


# ---------------------------------------------------------------------------- e-signature with IP capture
async def _signing_token(envelope_id: str, position: int) -> str:
    """Tests can't read the e-mail, so put a known token on the signer (as send_to_signer does)."""
    token = f"test-token-{envelope_id}-{position}"
    async with get_engine().begin() as conn:
        await conn.execute(text("update mytrakin.envelope_signers set token_hash = :h where envelope_id = :e and position = :p"),
                           {"h": sha256_hex(token), "e": envelope_id, "p": position})
    return token


async def _otp(envelope_id: str, position: int) -> str:
    async with get_engine().begin() as conn:
        signer = (await conn.execute(text("select id from mytrakin.envelope_signers where envelope_id = :e and position = :p"),
                                     {"e": envelope_id, "p": position})).scalar()
        await conn.execute(text("update mytrakin.envelope_signers set otp_hash = :h where id = :id"),
                           {"h": sha256_hex(f"{signer}:123456"), "id": signer})
    return "123456"


async def test_esignature_end_to_end(client, auth):
    admin = auth("admin")
    agreement = (await client.post("/agreements", headers=admin, json={
        "code": "MSA-TEST-01", "kind": "msa",
        "company_id": next(c["id"] for c in (await client.get("/companies", headers=admin)).json() if c["name"] == "Atlas Foods Corp."),
        "tenant_side": "supplier", "effective_on": str(date.today()), "status": "draft"})).json()

    created = await client.post("/envelopes", headers=admin, data={
        "title": "MSA for signature", "agreement_id": agreement["id"],
        "signers": '[{"name": "Pat Client", "email": "pat@client.example", "company": "Client"},'
                   ' {"name": "Madhavi G", "email": "madhavi@esg.example", "company": "ESG"}]'},
        files={"file": ("msa.pdf", small_pdf(), "application/pdf")})
    assert created.status_code == 201, created.text
    env_id = created.json()["id"]
    assert (await client.post(f"/envelopes/{env_id}/send", headers=admin)).json()["status"] == "sent"
    assert (await client.get(f"/agreements/{agreement['id']}", headers=admin)).json()["status"] == "out_for_signature"

    browser = {"x-vercel-forwarded-for": "198.51.100.23", "user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0",
               "x-vercel-ip-city": "Dallas", "x-vercel-ip-country-region": "TX", "x-vercel-ip-country": "US"}

    # Second signer can't jump the queue.
    second = await _signing_token(env_id, 2)
    view2 = (await client.get(f"/public/sign/{second}", headers=browser)).json()
    assert view2["my_turn"] is False

    first = await _signing_token(env_id, 1)
    view = (await client.get(f"/public/sign/{first}", headers=browser)).json()
    assert view["my_turn"] and view["your_ip"] == "198.51.100.23"
    assert (await client.get(f"/public/sign/{first}/document", headers=browser)).status_code == 400   # not verified yet
    assert (await client.post(f"/public/sign/{first}/code", headers=browser)).status_code == 200
    assert (await client.post(f"/public/sign/{first}/verify", headers=browser, json={"code": "000000"})).status_code == 400
    code = await _otp(env_id, 1)
    assert (await client.post(f"/public/sign/{first}/verify", headers=browser, json={"code": code})).status_code == 200
    pdf = await client.get(f"/public/sign/{first}/document", headers=browser)
    assert pdf.headers["content-type"] == "application/pdf"
    assert (await client.post(f"/public/sign/{first}/consent", headers=browser)).status_code == 200
    signed = await client.post(f"/public/sign/{first}/sign", headers=browser,
                               json={"signature_type": "typed", "signature_data": "Pat Client", "agree": True})
    assert signed.json()["status"] == "signed", signed.text

    second = await _signing_token(env_id, 2)          # the real link was e-mailed; replace it with a known one
    await client.post(f"/public/sign/{second}/code", headers=browser)
    await client.post(f"/public/sign/{second}/verify", headers=browser, json={"code": await _otp(env_id, 2)})
    await client.post(f"/public/sign/{second}/consent", headers=browser)
    done = await client.post(f"/public/sign/{second}/sign", headers=browser,
                             json={"signature_type": "typed", "signature_data": "Madhavi G", "agree": True})
    assert done.json()["status"] == "completed", done.text

    envelope = (await client.get(f"/envelopes/{env_id}", headers=admin)).json()
    assert envelope["status"] == "completed" and envelope["signed_sha256"]
    assert all(s["signed_ip"] == "198.51.100.23" and s["signed_location"] == "Dallas, TX, US" for s in envelope["signers"])
    assert {"created", "sent", "viewed", "verified", "consented", "signed", "completed"} <= {e["event"] for e in envelope["events"]}
    # A company MSA signed through e-signature is accepted by its counterparty.
    assert (await client.get(f"/agreements/{agreement['id']}", headers=admin)).json()["status"] == "accepted"
    # The used link no longer works.
    assert (await client.get(f"/public/sign/{second}", headers=browser)).status_code == 404


# ---------------------------------------------------------------------------- registration and approval
async def test_public_registration_and_approval(client, auth):
    tenant_id = (await client.get("/session", headers=auth("admin"))).json()["tenant"]["id"]
    page = await client.get(f"/public/workspaces/{tenant_id}")
    assert page.json()["name"] == "Executive Software Guild Inc."
    response = await client.post(f"/public/workspaces/{tenant_id}/registrations",
                                 data={"kind": "vendor", "name": "Acme Talent LLC", "contact": "Ann Lee",
                                       "email": "ann@acmetalent.example", "state": "tx", "ein": "12-3456789"},
                                 files=[("files", ("w9.pdf", small_pdf("W-9"), "application/pdf"))])
    assert response.status_code == 201, response.text
    reg_id = response.json()["id"]
    detail = (await client.get(f"/registrations/{reg_id}", headers=auth("admin"))).json()
    assert detail["state"] == "TX" and len(detail["files"]) == 1
    assert (await client.post(f"/registrations/{reg_id}/decision", headers=auth("admin"),
                              json={"decision": "rejected"})).status_code == 400          # needs a note
    approved = (await client.post(f"/registrations/{reg_id}/decision", headers=auth("admin"),
                                  json={"decision": "approved"})).json()
    assert approved["created"]["name"] == "Acme Talent LLC"


# ---------------------------------------------------------------------------- import / export
async def test_templates_import_and_export(client, auth):
    admin = auth("admin")
    template = await client.get("/data/templates/consultants.csv", headers=admin)
    assert template.text.lstrip("﻿").startswith("Full name,Email")

    csv = ("Full name,Email,Engagement type,Start date,Status,End date (former only),Reason for leaving,Eligible for rehire (Y/N)\n"
           "Old Timer,old.timer@example.com,1099,2020-01-06,Former,2023-03-31,Contract ended,Y\n"
           "Bad Row,not-an-email,W-2 contract,2026-01-01,,,,\n")
    dry = (await client.post("/data/import/consultants", params={"dry_run": True}, headers=admin,
                             files={"file": ("c.csv", csv.encode(), "text/csv")})).json()
    assert dry["valid"] == 1 and dry["errors"][0]["line"] == 3
    real = (await client.post("/data/import/consultants", headers=admin, files={"file": ("c.csv", csv.encode(), "text/csv")})).json()
    assert real["created"] == 1 and len(real["errors"]) == 1
    former = (await client.get("/consultants", params={"status": "former"}, headers=admin)).json()
    assert any(c["full_name"] == "Old Timer" for c in former)

    exported = await client.get("/data/export/consultants.csv", headers=admin)
    assert "Old Timer" in exported.text
    assert (await client.get("/data/export/ap_invoices.csv", headers=auth("vendor"))).status_code == 403


# ---------------------------------------------------------------------------- compliance, users, audit
async def test_expiring_document_and_renewal(client, auth):
    admin = auth("admin")
    consultants = (await client.get("/consultants", headers=admin)).json()
    anita = next(c for c in consultants if c["full_name"] == "Anita Desai")
    doc = (await client.post("/compliance/documents", headers=admin, json={
        "consultant_id": anita["id"], "doc_type": "passport", "label": "Passport", "expires_on": str(date.today() + timedelta(days=30))})).json()
    renewed = (await client.post(f"/compliance/documents/{doc['id']}/renew", headers=admin,
                                 json={"expires_on": str(date.today() + timedelta(days=3650))})).json()
    assert renewed["status"] == "valid"


async def test_invite_user_and_audit_trail(client, auth):
    admin = auth("admin")
    invited = await client.post("/users", headers=admin, json={"email": "new.hr@example.com", "role": "hr", "title": "HR generalist"})
    assert invited.status_code == 201, invited.text
    assert (await client.post("/users", headers=auth("finance"), json={"email": "x@example.com", "role": "viewer"})).status_code == 403
    me = (await client.get("/session", headers=admin)).json()
    demote = await client.patch(f"/users/{me['membership_id']}", headers=admin, json={"role": "viewer"})
    assert demote.status_code == 400
    trail = (await client.get("/audit", params={"entity": "memberships"}, headers=admin)).json()
    invite_row = next(row for row in trail if row["action"] == "insert" and row["changes"].get("invited_email") == "new.hr@example.com")
    assert invite_row["ip"] == "203.0.113.7" and invite_row["actor_role"] == "tenant_admin"


# ---------------------------------------------------------------------------- network
async def test_profile_photo_post_and_message(client, auth, user_ids):
    admin, consultant = auth("admin"), auth("consultant")
    updated = await client.patch("/network/me", headers=consultant, json={
        "headline": "SAP GRC Consultant", "skills": ["SAP GRC", "S/4 Security"],
        "experience": [{"title": "GRC Consultant", "company": "BrightPath", "start": "2024"}]})
    assert updated.status_code == 200, updated.text
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    photo = await client.post("/network/me/photo", headers=consultant, files={"file": ("me.png", png, "image/png")})
    assert photo.status_code == 200 and photo.json()["url"]
    bad = await client.post("/network/me/photo", headers=consultant, files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 400

    post = await client.post("/network/posts", headers=consultant, json={"body": "Wrapped up the SoD clean-up!", "kind": "update"})
    assert post.status_code == 201
    assert any(p["body"].startswith("Wrapped") for p in (await client.get("/network/feed", headers=admin)).json())
    assert (await client.post("/network/posts", headers=consultant,
                              json={"body": "Policy change", "kind": "announcement"})).status_code == 403

    ravi = user_ids["consultant"]
    sent = await client.post(f"/network/messages/{ravi}", headers=admin, json={"body": "Great work this week."})
    assert sent.status_code == 201
    threads = (await client.get("/network/messages", headers=consultant)).json()
    assert threads[0]["unread"] == 1
    assert (await client.post(f"/network/connections/{user_ids['admin']}", headers=consultant)).json()["status"] == "pending"
    assert (await client.post(f"/network/connections/{ravi}/respond", params={"accept": True}, headers=admin)).json()["status"] == "accepted"


# ---------------------------------------------------------------------------- automation
async def test_smart_suggestions(client, auth):
    items = (await client.get("/insights", headers=auth("admin"))).json()
    assert items and items == sorted(items, key=lambda s: s["priority"], reverse=True)
    assert any(s["area"] == "Compliance" for s in items)
    assert (await client.get("/insights", headers=auth("vendor"))).json() == []
    assert (await client.post("/insights/ask", headers=auth("admin"), json={"question": "What first?"})).status_code == 501


async def test_daily_cron_is_protected_and_idempotent(client):
    assert (await client.get("/cron/daily")).status_code == 401
    headers = {"Authorization": "Bearer cron-test-secret"}
    first = (await client.get("/cron/daily", headers=headers)).json()
    assert first["tenants"] >= 1 and not any(v.get("error") for v in first["summary"].values())
    second = (await client.get("/cron/daily", headers=headers)).json()
    for counts in second["summary"].values():
        assert counts["documents"] == 0 and counts["invoices"] == 0     # deduplicated


async def test_upload_and_soft_delete_file(client, auth):
    admin = auth("admin")
    company = (await client.get("/companies", headers=admin)).json()[0]
    uploaded = await client.post("/files", headers=admin, data={"owner_type": "company", "owner_id": company["id"]},
                                 files={"file": ("coi.pdf", io.BytesIO(small_pdf("COI")), "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    assert (await client.delete(f"/files/{file_id}", headers=admin)).status_code == 200
    files = (await client.get("/files", params={"owner_type": "company", "owner_id": company["id"]}, headers=admin)).json()
    assert all(f["id"] != file_id for f in files)


# ---------------------------------------------------------------------------- payroll, referrals, 1099
async def test_payroll_referrals_and_1099(client, auth):
    finance = auth("finance")
    lines = (await client.get("/payroll", headers=finance)).json()
    assert {line["full_name"] for line in lines} == {"Anita Desai", "Grace Okafor", "Priya Nair"}
    daniel = next(c for c in (await client.get("/consultants", headers=finance)).json() if c["full_name"] == "Daniel Cho")
    not_w2 = await client.post("/payroll", headers=finance, json={
        "consultant_id": daniel["id"], "period_start": "2026-09-01", "period_end": "2026-09-15", "pay_date": "2026-09-20", "gross": 100})
    assert not_w2.status_code == 400

    referrals = (await client.get("/referrals", headers=finance)).json()
    kiran = next(r for r in referrals if r["referrer_name"] == "Kiran Patel")
    assert float(kiran["earned"]) > 0 and float(kiran["paid"]) == 120
    too_much = await client.post(f"/referrals/{kiran['id']}/payments", headers=finance,
                                 json={"amount": float(kiran["balance"]) + 1, "paid_on": str(date.today())})
    assert too_much.status_code == 400
    grace = next(r for r in referrals if r["referrer_name"] == "Grace Okafor")
    assert float(grace["earned"]) == 0          # one-time fee isn't due until the eligibility date

    summary = (await client.get("/form-1099", params={"year": date.today().year}, headers=finance)).json()
    assert float(summary["threshold"]) == (2000 if date.today().year >= 2026 else 600)
    assert any(r["payee"] == "Kiran Patel" for r in summary["rows"])
    assert (await client.get("/form-1099", params={"year": 2026}, headers=auth("vendor"))).status_code == 403


async def test_expense_and_time_off_approvals(client, auth):
    admin = auth("admin")
    expense = (await client.get("/expenses", params={"status": "submitted"}, headers=admin)).json()[0]
    assert (await client.post(f"/expenses/{expense['id']}/decision", headers=admin, json={"decision": "reimbursed"})).status_code == 409
    assert (await client.post(f"/expenses/{expense['id']}/decision", headers=admin, json={"decision": "approved"})).json()["status"] == "approved"
    request = (await client.get("/time-off", params={"status": "requested"}, headers=admin)).json()[0]
    assert (await client.post(f"/time-off/{request['id']}/decision", headers=admin, json={"decision": "approved"})).json()["status"] == "approved"


async def test_send_draft_invoice_emails_customer(client, auth):
    finance = auth("finance")
    week = THIS_WEEK - timedelta(days=7)
    await client.post("/invoices/generate", headers=finance, json={"period_start": str(week), "period_end": str(week + timedelta(days=6))})
    drafts = [r for r in (await client.get("/invoices", params={"direction": "ar"}, headers=finance)).json() if r["status"] == "draft"]
    assert drafts, "last week's approved hours should give draft invoices"
    sent = (await client.post(f"/invoices/{drafts[0]['id']}/send", headers=finance)).json()
    assert sent["status"] == "sent" and sent["emailed"] is True
    assert (await client.post(f"/invoices/{drafts[0]['id']}/send", headers=finance)).status_code == 409
    log = (await client.get("/notifications", params={"kind": "invoice"}, headers=finance)).json()
    assert log and log[0]["status"] == "sent"


async def test_large_file_direct_upload(client, auth):
    """Files over 4 MB go straight to storage (here: the local stand-in), then get confirmed."""
    admin = auth("admin")
    company = (await client.get("/companies", headers=admin)).json()[0]
    big = b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024)
    too_big = await client.post("/files", headers=admin, data={"owner_type": "company", "owner_id": company["id"]},
                                files={"file": ("scan.pdf", big, "application/pdf")})
    assert too_big.json()["error"]["code"] == "use_direct_upload"

    start = (await client.post("/uploads", headers=admin, json={
        "purpose": "attachment", "filename": "signed msa scan.pdf", "content_type": "application/pdf", "size": len(big),
        "owner_type": "company", "owner_id": company["id"]})).json()
    put = await client.put(start["upload_url"].replace("http://test/v1", ""), content=big)
    assert put.status_code == 200, put.text
    bad = await client.post("/files/confirm", headers=admin, json={"owner_type": "company", "owner_id": company["id"],
                                                                   "path": "someone-else/company/x/file.pdf", "name": "x.pdf"})
    assert bad.status_code == 403
    confirmed = await client.post("/files/confirm", headers=admin, json={
        "owner_type": "company", "owner_id": company["id"], "path": start["path"], "name": "signed msa scan.pdf",
        "content_type": "application/pdf"})
    assert confirmed.status_code == 201 and confirmed.json()["size_bytes"] == len(big)

    # The same route for an e-signature PDF.
    start = (await client.post("/uploads", headers=admin, json={
        "purpose": "esign", "filename": "msa.pdf", "content_type": "application/pdf", "size": len(big)})).json()
    await client.put(start["upload_url"].replace("http://test/v1", ""), content=big)
    env = await client.post("/envelopes", headers=admin, data={
        "title": "Large MSA", "document_path": start["path"], "signers": '[{"name": "A B", "email": "ab@example.com"}]'})
    assert env.status_code == 201, env.text

    # Consultants can't get upload URLs for someone else's record.
    other = await client.post("/uploads", headers=auth("consultant"), json={
        "purpose": "attachment", "filename": "x.pdf", "content_type": "application/pdf", "size": 10,
        "owner_type": "company", "owner_id": company["id"]})
    assert other.status_code == 403


async def test_placement_assignment_notifies_consultant(client, auth):
    """Assigning a project notifies the consultant (e-mail + notification log)."""
    admin = auth("admin")
    consultant = next(c for c in (await client.get("/consultants", params={"status": "active"}, headers=admin)).json()
                      if c["email"])
    project = (await client.get("/projects", headers=admin)).json()[0]
    created = await client.post("/placements", headers=admin, json={
        "consultant_id": consultant["id"], "project_id": project["id"], "start_date": str(date.today())})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    try:
        async with get_engine().begin() as conn:
            note = (await conn.execute(
                text("select to_address, kind, status from mytrakin.notifications "
                     "where kind = 'placement' and ref_id = :id order by sent_at desc limit 1"),
                {"id": pid})).mappings().first()
        assert note is not None, "placement assignment was not logged as a notification"
        assert consultant["email"] in note["to_address"], note
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.notifications where ref_type = 'placement' and ref_id = :id"),
                               {"id": pid})
            await conn.execute(text("delete from mytrakin.placements where id = :id"), {"id": pid})


async def test_consultant_uid_is_visible(client, auth):
    """Every consultant shows their system-wide UID (U-ID), or null before first sign-in."""
    admin = auth("admin")
    listed = await client.get("/consultants", params={"status": "active"}, headers=admin)
    assert listed.status_code == 200
    assert all("user_code" in r for r in listed.json()), listed.json()
    first = listed.json()[0]
    detail = await client.get(f"/consultants/{first['id']}", headers=admin)
    assert detail.status_code == 200 and "user_code" in detail.json(), detail.text
    # Ravi was invited by e-mail and claimed the invite at his first sign-in: his U-ID must show.
    ravi = next(r for r in listed.json() if r["full_name"] == "Ravi Kumar")
    assert ravi["user_code"] and ravi["user_code"].startswith("U"), ravi
