"""Outbound e-mail: Resend API first, plain SMTP (e.g. Zoho) as fallback.
Every message is logged in `mytrakin.notifications`; a `dedupe_key` stops
the same reminder going out twice."""

from __future__ import annotations

import asyncio
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

import httpx

from ..config import get_settings
from ..db import Db

log = logging.getLogger("mytrakin.email")


def _send_via_smtp(*, host: str, port: int, user: str, password: str, use_tls: bool,
                   sender: str, recipients: list[str], subject: str, html_body: str) -> None:
    """Blocking SMTP send (run in a worker thread). Raises on failure."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    # Plain-text fallback for clients that ignore HTML.
    msg.set_content("This message is best viewed in an HTML-capable e-mail client.")
    msg.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=context)
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)


def render(title: str, paragraphs: list[str], button: tuple[str, str] | None = None, footer: str | None = None) -> str:
    """A small, accessible HTML e-mail. Paragraph text is escaped."""
    body = "".join(f'<p style="margin:0 0 14px">{html.escape(p)}</p>' for p in paragraphs)
    action = ""
    if button:
        label, url = button
        action = (f'<p style="margin:22px 0"><a href="{html.escape(url)}" style="background:#1f4fd6;color:#fff;'
                  f'padding:11px 18px;border-radius:8px;text-decoration:none;font-weight:600">{html.escape(label)}</a></p>')
    foot = html.escape(footer or "You receive this because you work with a company that uses myTrakIn.")
    return (f'<div style="font-family:Inter,Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.5;color:#14181f;'
            f'max-width:560px;margin:auto"><p style="font-weight:700;font-size:17px;margin:0 0 16px">{html.escape(title)}</p>'
            f'{body}{action}<p style="color:#5b6472;font-size:12.5px;margin-top:28px">{foot}</p></div>')


async def send_email(
    db: Db | None,
    *,
    to: str | list[str],
    subject: str,
    html_body: str,
    kind: str,
    tenant_id: Any = None,
    ref_type: str | None = None,
    ref_id: Any = None,
    dedupe_key: str | None = None,
) -> bool:
    """Send (or log) one e-mail. Returns False when it was skipped as a duplicate."""
    settings = get_settings()
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    if not recipients:
        return False

    inserted = None
    if db is not None:
        inserted = await db.val(
            "select mytrakin.log_notification(:tenant, :to, :subject, :kind, :ref_type, :ref_id, :dedupe)",
            {"tenant": tenant_id, "to": ", ".join(recipients), "subject": subject, "kind": kind,
             "ref_type": ref_type, "ref_id": ref_id, "dedupe": dedupe_key},
        )
        if inserted is None:
            return False    # this reminder already went out

    status = "sent"
    if settings.resend_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                    json={"from": settings.email_from, "to": recipients, "subject": subject, "html": html_body},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            log.exception("e-mail to %s failed (resend)", recipients)
            status = "failed"
    elif settings.email_host:
        try:
            await asyncio.to_thread(
                _send_via_smtp,
                host=settings.email_host,
                port=settings.email_port,
                user=settings.email_host_user,
                password=settings.email_host_password,
                use_tls=settings.email_use_tls,
                sender=settings.email_from,
                recipients=recipients,
                subject=subject,
                html_body=html_body,
            )
        except (smtplib.SMTPException, OSError):
            log.exception("e-mail to %s failed (smtp %s)", recipients, settings.email_host)
            status = "failed"
    else:
        log.info("E-MAIL (not sent, no RESEND_API_KEY / EMAIL_HOST) to=%s subject=%s", recipients, subject)

    if db is not None and inserted is not None:
        await db.run("select mytrakin.mark_notification(:id, :s)", {"s": status, "id": inserted})
    return status == "sent"
