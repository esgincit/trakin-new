"""Database access.

Every request runs in ONE transaction. The first statement resolves who the caller
is for the requested tenant and switches the session to the `mytrakin_api` role with
`mytrakin.begin_request(...)`, so row-level security applies to everything after it.

Queries are plain SQL (SQLAlchemy `text()`), kept next to the code that uses them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from .config import get_settings

_engine: AsyncEngine | None = None


def normalize_db_url(url: str) -> tuple[str, bool]:
    """Turn a Supabase/libpq URL into an asyncpg URL. Returns (url, needs_ssl)."""
    parts = urlsplit(url)
    scheme = "postgresql+asyncpg"
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    query.pop("pgbouncer", None)
    host = parts.hostname or ""
    needs_ssl = sslmode in {"require", "verify-ca", "verify-full"} or (
        host not in {"localhost", "127.0.0.1", ""} and sslmode != "disable"
    )
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), "")), needs_ssl


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url, needs_ssl = normalize_db_url(settings.database_url)
        connect_args: dict[str, Any] = {
            # Supabase's transaction pooler (Supavisor) does not keep prepared statements
            # between transactions, so disable asyncpg's statement cache and use unique names.
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__mt_{uuid4().hex}__",
            "server_settings": {"application_name": "mytrakin-api"},
        }
        if needs_ssl:
            connect_args["ssl"] = "require"
        pool_kwargs: dict[str, Any] = (
            {"poolclass": NullPool}
            if settings.db_pool == "none"
            else {"pool_size": settings.db_pool_size, "max_overflow": 5, "pool_pre_ping": True}
        )
        _engine = create_async_engine(url, connect_args=connect_args, **pool_kwargs)
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


class Db:
    """Thin helper around one transaction-bound connection."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn

    async def all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        result = await self.conn.execute(text(sql), dict(params or {}))
        return [dict(row) for row in result.mappings().all()]

    async def one(self, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        result = await self.conn.execute(text(sql), dict(params or {}))
        row: RowMapping | None = result.mappings().first()
        return dict(row) if row is not None else None

    async def val(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        result = await self.conn.execute(text(sql), dict(params or {}))
        return result.scalar()

    async def run(self, sql: str, params: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None) -> int:
        if isinstance(params, Sequence) and not isinstance(params, Mapping):
            result = await self.conn.execute(text(sql), [dict(p) for p in params])
        else:
            result = await self.conn.execute(text(sql), dict(params or {}))
        return result.rowcount or 0
