"""myTrakIn API — FastAPI application.

Run locally:   uvicorn app.main:app --reload --port 8000
On Vercel:     detected automatically (pyproject.toml → [tool.vercel] entrypoint).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from .config import get_settings
from .db import get_engine
from .errors import install_error_handlers
from .responses import AppJSONResponse
from .routers import (
    acceptances,
    admin,
    companies,
    compliance,
    consultants,
    contracts,
    cron,
    dashboard,
    data,
    esign,
    insights,
    invoices,
    me,
    network,
    onboarding,
    people_pay,
    platform,
    projects,
    public,
    timesheets,
    uploads,
)

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="myTrakIn API",
    version="1.0.0",
    description="Vendor-chain payments, timesheets, contracts and compliance for US staffing companies.",
    default_response_class=AppJSONResponse,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,          # the web app sends a bearer token, not cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "x-upsert"],
    expose_headers=["Content-Disposition", "Server-Timing"],
    max_age=86400,
)
install_error_handlers(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


v1 = APIRouter(prefix="/v1")
for module in (me, dashboard, companies, contracts, projects, timesheets, invoices, people_pay, esign, compliance, data,
               admin, network, insights, platform, public, cron, uploads, onboarding, acceptances):
    v1.include_router(module.router)
v1.include_router(consultants.router)
app.include_router(v1)


@app.get("/v1/health", tags=["health"])
async def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/v1/health/db", tags=["health"])
async def health_db():
    started = time.perf_counter()
    async with get_engine().connect() as conn:
        await conn.execute(text("select 1"))
    return {"status": "ok", "db_ms": round((time.perf_counter() - started) * 1000, 1)}
