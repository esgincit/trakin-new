"""Small helpers shared across routers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Request


def client_ip(request: Request) -> str | None:
    """The caller's public IP address.

    Behind Vercel the platform sets `x-vercel-forwarded-for` / `x-real-ip`; elsewhere we
    take the first address in `x-forwarded-for`. Falls back to the socket address.
    """
    for header in ("x-vercel-forwarded-for", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def approx_location(request: Request) -> str | None:
    """Approximate location from Vercel's geo headers (city, region, country)."""
    city = request.headers.get("x-vercel-ip-city")
    region = request.headers.get("x-vercel-ip-country-region")
    country = request.headers.get("x-vercel-ip-country")
    parts = [p for p in (city and _unquote(city), region, country) if p]
    return ", ".join(parts) if parts else None


def _unquote(value: str) -> str:
    from urllib.parse import unquote

    return unquote(value)


def user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:300] if ua else None


def device_label(ua: str | None) -> str:
    """'Chrome on Windows' style label for audit trails and certificates."""
    if not ua:
        return "Unknown device"
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"),
                                            ("Firefox/", "Firefox"), ("Safari/", "Safari")) if key in ua), "Browser")
    system = next((name for key, name in (("iPhone", "iOS"), ("iPad", "iOS"), ("Android", "Android"),
                                           ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if key in ua),
                  "unknown OS")
    return f"{browser} on {system}"


def money(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def week_start(day: date) -> date:
    """The Sunday on or before `day` (timesheet weeks run Sunday–Saturday)."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def parse_terms_days(terms: str | None, default: int = 30) -> int:
    """'Net 45' -> 45. Pay-when-paid and unknown terms fall back to the default."""
    if not terms:
        return default
    digits = "".join(ch for ch in terms if ch.isdigit())
    return int(digits) if digits else default
