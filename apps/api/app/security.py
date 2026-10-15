"""Verifies Supabase access tokens (JWTs) sent as `Authorization: Bearer <token>`.

Supabase projects sign tokens either with a shared secret (legacy, HS256) or with
asymmetric signing keys published at /auth/v1/.well-known/jwks.json (ES256/RS256).
Both are supported; the token header decides which path is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Request

from .config import get_settings
from .errors import ApiError


@dataclass(frozen=True)
class Claims:
    user_id: UUID
    email: str | None
    aal: str           # "aal1" = password/OTP only, "aal2" = MFA completed
    raw: dict


# A fresh token is "issued" by Supabase's clock; a server a few seconds behind would see it as not valid yet.
CLOCK_SKEW = 30   # seconds


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def decode_token(token: str) -> Claims:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")
        options = {"require": ["exp", "sub"]}
        issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None
        if alg.startswith("HS"):
            if not settings.supabase_jwt_secret:
                raise ApiError(401, "unauthorized", "Token signing method is not configured")
            payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"],
                                 audience=settings.jwt_audience, issuer=issuer, options=options, leeway=CLOCK_SKEW)
        else:
            if not settings.supabase_url:
                raise ApiError(401, "unauthorized", "SUPABASE_URL is required to verify tokens")
            key = _jwks_client(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token)
            payload = jwt.decode(token, key.key, algorithms=["ES256", "RS256"],
                                 audience=settings.jwt_audience, issuer=issuer, options=options, leeway=CLOCK_SKEW)
    except ApiError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "token_expired", "Your session has expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "Invalid sign-in token") from exc

    return Claims(user_id=UUID(payload["sub"]), email=payload.get("email"), aal=payload.get("aal", "aal1"), raw=payload)


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "unauthorized", "Sign in to continue")
    return token
