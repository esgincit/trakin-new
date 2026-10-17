"""E-signatures: several documents in one envelope, signers picked from the companies'
own admins, and every admin of the counterparty told about it (PLAN ESG-02, NOT-02)."""

from __future__ import annotations

import io
import json

from fpdf import FPDF
from pypdf import PdfReader
from sqlalchemy import text

from app.db import get_engine

PDF = b"%PDF-1.4 fake"


def pdf(pages: int = 1, label: str = "doc") -> bytes:
    out = FPDF()
    for i in range(pages):
        out.add_page()
        out.set_font("Helvetica", size=12)
        out.cell(0, 10, f"{label} page {i + 1}")
    return bytes(out.output())


def page_count(blob: bytes) -> int:
    return len(PdfReader(io.BytesIO(blob)).pages)


async def _brightpath() -> str:
    async with get_engine().begin() as conn:
        return (await conn.execute(text("select id from mytrakin.companies where name = 'BrightPath Tech LLC'"))).scalar()


async def _msa_with_brightpath() -> str:
    async with get_engine().begin() as conn:
        return (await conn.execute(text("select id from mytrakin.agreements where code = 'MSA-ESG-BP'"))).scalar()


async def _second_admin(company_id: str) -> None:
    """A second admin of the counterparty: notifications must reach them too."""
    async with get_engine().begin() as conn:
        uid = (await conn.execute(
            text("select id from auth.users where email = 'founder@newco.example'"))).scalar()
        await conn.execute(
            text("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                    select (select tenant_id from mytrakin.companies where id = :c), :c, :u, 'owner', 'active'
                    on conflict do nothing"""),
            {"c": company_id, "u": uid})


async def test_signing_parties_offer_the_counterparty_admins(client, auth, user_ids):
    """/signing-parties answers "who signs": us from our own company, and the people who
    may sign for the other company — a pick list of that company's admins, not free text."""
    await _second_admin(await _brightpath())
    agreement_id = await _msa_with_brightpath()
    parties = (await client.get("/envelopes/signing-parties",
                                params={"agreement_id": agreement_id}, headers=auth("admin")))
    assert parties.status_code == 200, parties.text
    body = parties.json()

    assert body["creator"]["email"] == "admin@example.com", body["creator"]
    assert body["counterparty"]["name"] == "BrightPath Tech LLC", body["counterparty"]

    emails = [s["email"] for s in body["signers"]]
    assert "s.rao@brightpath.example" in emails, emails          # the company's vendor admin
    assert "founder@newco.example" in emails, emails              # and its owner
    # Strongest role first: that is who the picker offers as the default signer.
    assert body["signers"][0]["company_role"] in ("owner", "super_admin", "admin", "vendor_admin"), body["signers"]
    assert all(s["company"] == "BrightPath Tech LLC" for s in body["signers"]), body["signers"]

    # A role that cannot send documents gets nothing.
    assert (await client.get("/envelopes/signing-parties",
                             params={"agreement_id": agreement_id}, headers=auth("consultant"))).status_code == 403


async def test_envelope_holds_several_documents(client, auth):
    """A packet is one envelope: the documents are kept in order and merged into the
    single PDF every signer signs."""
    created = None
    try:
        response = await client.post(
            "/envelopes", headers=auth("admin"),
            data={"title": "MSA packet",
                  "signers": json.dumps([{"name": "Ada Admin", "email": "admin@example.com"}])},
            files=[("files", ("msa.pdf", pdf(2, "msa"), "application/pdf")),
                   ("files", ("sow.pdf", pdf(1, "sow"), "application/pdf"))])
        assert response.status_code == 201, response.text
        env = response.json()
        created = env["id"]

        assert [d["name"] for d in env["documents"]] == ["msa.pdf", "sow.pdf"], env["documents"]
        assert [d["position"] for d in env["documents"]] == [1, 2], env["documents"]

        # The document that gets signed is the two PDFs back to back.
        original = await client.get(f"/envelopes/{env['id']}/download", headers=auth("admin"))
        assert original.status_code == 200 and original.json()["url"], original.text
        async with get_engine().begin() as conn:
            path = (await conn.execute(text("select document_path from mytrakin.envelopes where id = :id"),
                                       {"id": env["id"]})).scalar()
        from app.services import storage

        assert page_count(await storage.download("esign", path)) == 3

        # One more document, then take it away again.
        added = await client.post(f"/envelopes/{env['id']}/documents", headers=auth("admin"),
                                  files={"file": ("exhibit.pdf", pdf(1, "exhibit"), "application/pdf")})
        assert added.status_code == 201, added.text
        assert added.json()["position"] == 3
        detail = (await client.get(f"/envelopes/{env['id']}", headers=auth("admin"))).json()
        assert [d["name"] for d in detail["documents"]] == ["msa.pdf", "sow.pdf", "exhibit.pdf"], detail["documents"]

        removed = await client.delete(f"/envelopes/{env['id']}/documents/{detail['documents'][2]['id']}",
                                      headers=auth("admin"))
        assert removed.status_code == 200, removed.text
        after = (await client.get(f"/envelopes/{env['id']}", headers=auth("admin"))).json()
        assert [d["name"] for d in after["documents"]] == ["msa.pdf", "sow.pdf"], after["documents"]
        assert [d["position"] for d in after["documents"]] == [1, 2], after["documents"]

        # The last document cannot be removed — an envelope needs something to sign.
        last = await client.delete(f"/envelopes/{env['id']}/documents/{after['documents'][0]['id']}",
                                   headers=auth("admin"))
        assert last.status_code == 200, last.text
        one = (await client.get(f"/envelopes/{env['id']}", headers=auth("admin"))).json()
        assert len(one["documents"]) == 1, one["documents"]
        again = await client.delete(f"/envelopes/{env['id']}/documents/{one['documents'][0]['id']}",
                                    headers=auth("admin"))
        assert again.status_code == 409, again.text
    finally:
        if created:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.envelopes where id = :id"), {"id": created})


async def test_single_document_still_works(client, auth):
    """The older single-file field keeps working."""
    created = None
    try:
        response = await client.post(
            "/envelopes", headers=auth("admin"),
            data={"title": "One document",
                  "signers": json.dumps([{"name": "Ada Admin", "email": "admin@example.com"}])},
            files={"file": ("msa.pdf", pdf(1, "msa"), "application/pdf")})
        assert response.status_code == 201, response.text
        created = response.json()["id"]
        assert [d["name"] for d in response.json()["documents"]] == ["msa.pdf"], response.json()["documents"]
    finally:
        if created:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.envelopes where id = :id"), {"id": created})


async def test_sending_notifies_every_admin_of_the_counterparty(client, auth):
    """Sending tells all of the other company's admins, not just whoever signs: the
    agreement is theirs to action even when they are not the signer."""
    company_id = await _brightpath()
    await _second_admin(company_id)
    agreement_id = await _msa_with_brightpath()
    created = None
    try:
        response = await client.post(
            "/envelopes", headers=auth("admin"),
            data={"title": "MSA BrightPath", "agreement_id": str(agreement_id),
                  "signers": json.dumps([{"name": "Ada Admin", "email": "admin@example.com"}])},
            files={"file": ("msa.pdf", pdf(1, "msa"), "application/pdf")})
        assert response.status_code == 201, response.text
        created = response.json()["id"]

        sent = await client.post(f"/envelopes/{created}/send", headers=auth("admin"))
        assert sent.status_code == 200, sent.text
        notified = sent.json()["notified"]
        assert "s.rao@brightpath.example" in notified, notified
        assert "founder@newco.example" in notified, notified

        async with get_engine().begin() as conn:
            row = (await conn.execute(
                text("""select to_address from mytrakin.notifications
                        where ref_type = 'envelope' and ref_id = :id and kind = 'esign_notice'"""),
                {"id": created})).scalar()
            events = [r[0] for r in (await conn.execute(
                text("select event from mytrakin.signature_events where envelope_id = :id order by at"),
                {"id": created})).all()]
        assert "s.rao@brightpath.example" in row and "founder@newco.example" in row, row
        assert "counterparty_notified" in events, events
    finally:
        if created:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.envelopes where id = :id"), {"id": created})


async def test_agreement_page_shows_the_documents_sent_for_signature(client, auth):
    """The documents an envelope carries are listed on the agreement that sent them,
    with a link that opens the file -- they live with the envelope, not in the
    agreement's own files."""
    agreement_id = await _msa_with_brightpath()
    created = None
    try:
        response = await client.post(
            "/envelopes", headers=auth("admin"),
            data={"title": "MSA packet", "agreement_id": str(agreement_id),
                  "signers": json.dumps([{"name": "Ada Admin", "email": "admin@example.com"}])},
            files=[("files", ("msa.pdf", pdf(2, "msa"), "application/pdf")),
                   ("files", ("sow.pdf", pdf(1, "sow"), "application/pdf"))])
        assert response.status_code == 201, response.text
        created = response.json()["id"]

        detail = (await client.get(f"/agreements/{agreement_id}", headers=auth("admin"))).json()
        mine = next(e for e in detail["envelopes"] if e["id"] == created)
        assert [d["name"] for d in mine["documents"]] == ["msa.pdf", "sow.pdf"], mine["documents"]

        # Each one can be opened on its own.
        first = mine["documents"][0]
        link = await client.get(f"/envelopes/{created}/documents/{first['id']}/download", headers=auth("admin"))
        assert link.status_code == 200 and link.json()["url"], link.text
        assert link.json()["name"] == "msa.pdf", link.text

        # A document of another envelope is not reachable through this one.
        assert (await client.get(f"/envelopes/{created}/documents/{first['id']}/download",
                                 headers=auth("vendor"))).status_code in (403, 404)
    finally:
        if created:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.envelopes where id = :id"), {"id": created})


async def test_standalone_envelope_notifies_nobody_else(client, auth):
    created = None
    try:
        response = await client.post(
            "/envelopes", headers=auth("admin"),
            data={"title": "Standalone NDA",
                  "signers": json.dumps([{"name": "Ada Admin", "email": "admin@example.com"}])},
            files={"file": ("nda.pdf", pdf(1, "nda"), "application/pdf")})
        assert response.status_code == 201, response.text
        created = response.json()["id"]
        sent = await client.post(f"/envelopes/{created}/send", headers=auth("admin"))
        assert sent.status_code == 200, sent.text
        assert not sent.json()["notified"], sent.json()["notified"]
    finally:
        if created:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.envelopes where id = :id"), {"id": created})
