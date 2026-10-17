"""E-signature helpers: signing links, one-time codes, and the sealed PDF with its
certificate of completion (who signed, when, from which IP address and device)."""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

from ..config import get_settings
from ..db import Db
from ..utils import new_token, sha256_hex
from .email import render, send_email

ESIGN_DISCLOSURE = (
    "By continuing you agree to receive and sign documents electronically. Electronic signatures and records "
    "have the same legal effect as handwritten ones under the U.S. ESIGN Act and the Uniform Electronic "
    "Transactions Act (UETA). You may ask the sender for a paper copy at any time and may withdraw this "
    "consent for future documents by contacting the sender."
)


def signing_link(token: str) -> str:
    return f"{get_settings().web_origin.rstrip('/')}/sign/{token}"


async def log_event(db: Db, *, tenant_id: Any, envelope_id: Any, signer_id: Any, event: str,
                    ip: str | None = None, user_agent: str | None = None, location: str | None = None,
                    detail: dict | None = None) -> None:
    import orjson

    await db.run(
        """insert into signature_events (tenant_id, envelope_id, signer_id, event, ip, user_agent, location, detail)
           values (:t, :e, :s, :ev, :ip, :ua, :loc, cast(:detail as jsonb))""",
        {"t": tenant_id, "e": envelope_id, "s": signer_id, "ev": event, "ip": ip, "ua": user_agent, "loc": location,
         "detail": orjson.dumps(detail or {}).decode()},
    )


async def send_to_signer(db: Db, *, envelope: dict, signer: dict, sender_name: str, is_reminder: bool = False) -> None:
    """Create a fresh signing link for the signer and e-mail it."""
    token = new_token()
    await db.run(
        """update envelope_signers set token_hash = :h, status = case when status = 'waiting' then 'sent' else status end,
                  last_reminded_at = case when :rem then now() else last_reminded_at end
            where id = :id""",
        {"h": sha256_hex(token), "id": signer["id"], "rem": is_reminder},
    )
    await log_event(db, tenant_id=envelope["tenant_id"], envelope_id=envelope["id"], signer_id=signer["id"],
                    event="reminded" if is_reminder else "sent", detail={"to": signer["email"]})
    subject = f"{'Reminder: ' if is_reminder else ''}Please sign: {envelope['title']}"
    html_body = render(
        f"{sender_name} sent you a document to sign",
        [envelope["title"], envelope.get("message") or "Please review and sign.",
         "You'll confirm your e-mail with a one-time code before signing. The link is personal — please don't forward it."],
        button=("Review and sign", signing_link(token)),
    )
    await send_email(db, to=signer["email"], subject=subject, html_body=html_body, kind="esign",
                     tenant_id=envelope["tenant_id"], ref_type="envelope", ref_id=envelope["id"])


def link_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().signing_link_days)


# ----------------------------------------------------------------------------- PDF
def _latin1(text: Any) -> str:
    """fpdf's built-in fonts are Latin-1 only; swap typographic characters for plain ones."""
    value = "" if text is None else str(text)
    for a, b in (("—", "-"), ("–", "-"), ("→", "->"), ("“", '"'), ("”", '"'),
                 ("‘", "'"), ("’", "'"), ("·", "-"), ("…", "...")):
        value = value.replace(a, b)
    return value.encode("latin-1", "replace").decode("latin-1")


def _fmt(ts: Any) -> str:
    if not ts:
        return "-"
    if isinstance(ts, datetime):
        return ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(ts)


def build_certificate(envelope: dict, signers: list[dict], events: list[dict], document_sha256: str | None) -> bytes:
    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Certificate of completion", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Envelope", envelope["number"]),
        ("Document", envelope["title"]),
        ("Sent by", envelope.get("sent_by_name") or "-"),
        ("Sent", _fmt(envelope.get("sent_at"))),
        ("Completed", _fmt(envelope.get("completed_at"))),
        ("Original document SHA-256", document_sha256 or "-"),
        ("Legal framework", "U.S. ESIGN Act and UETA"),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 7, _latin1(label))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 7, _latin1(value), new_x="LMARGIN", new_y="NEXT")

    by_signer: dict[Any, list[dict]] = {}
    for event in events:
        by_signer.setdefault(event["signer_id"], []).append(event)

    for signer in signers:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _latin1(f"{signer['position']}. {signer['name']} - {signer.get('company') or ''}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _latin1(f"E-mail: {signer['email']}   Status: {signer['status']}"), new_x="LMARGIN", new_y="NEXT")
        if signer.get("signature_type") == "drawn" and str(signer.get("signature_data", "")).startswith("data:image/png;base64,"):
            try:
                raw = base64.b64decode(signer["signature_data"].split(",", 1)[1])
                pdf.image(io.BytesIO(raw), h=16)
            except Exception:  # an unreadable drawing must not block the certificate
                pdf.cell(0, 8, "[drawn signature]", new_x="LMARGIN", new_y="NEXT")
        elif signer.get("signature_data"):
            pdf.set_font("Times", "I", 18)
            pdf.cell(0, 10, _latin1(signer["signature_data"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _latin1(f"Signed: {_fmt(signer.get('signed_at'))}   IP address: {signer.get('signed_ip') or '-'}"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, _latin1(f"Device: {signer.get('signed_user_agent') or '-'}   Location: {signer.get('signed_location') or '-'}"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        for head, width in (("Event", 32), ("Time (UTC)", 48), ("IP address", 36), ("Device / detail", 0)):
            pdf.cell(width, 6, head, border="B", new_x="RIGHT" if width else "LMARGIN", new_y="TOP" if width else "NEXT")
        pdf.set_font("Helvetica", "", 9)
        for event in by_signer.get(signer["id"], []):
            pdf.cell(32, 6, _latin1(event["event"]))
            pdf.cell(48, 6, _latin1(_fmt(event["at"])))
            pdf.cell(36, 6, _latin1(event.get("ip") or "-"))
            pdf.cell(0, 6, _latin1((event.get("user_agent") or "")[:60]), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4.5, _latin1(ESIGN_DISCLOSURE))
    return bytes(pdf.output())


def merge_documents(blobs: list[bytes]) -> bytes:
    """Concatenate an envelope's PDFs, in order, into the one document that gets signed.

    A packet (an MSA plus its SOW, a contract and its exhibits) is one envelope:
    every signer sees the same pages in the same order, and the certificate of
    completion is appended to the result when the last signature lands.
    """
    writer = PdfWriter()
    for blob in blobs:
        for page in PdfReader(io.BytesIO(blob)).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def combined_document(blobs: list[bytes]) -> bytes:
    """The PDF an envelope asks to be signed: a single document is stored as it is,
    several are merged so every signer sees them in the same order."""
    if len(blobs) == 1:
        return blobs[0]
    return merge_documents(blobs)


def seal(original: bytes | None, certificate: bytes) -> bytes:
    """Append the certificate pages to the original PDF (or return the certificate alone)."""
    writer = PdfWriter()
    for blob in (original, certificate):
        if blob:
            for page in PdfReader(io.BytesIO(blob)).pages:
                writer.add_page(page)
    writer.add_metadata({"/Producer": "myTrakIn e-signature"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
