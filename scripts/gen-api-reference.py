#!/usr/bin/env python3
"""Writes docs/api-reference.md from the API's OpenAPI schema.

    cd apps/api && .venv/bin/python ../../scripts/gen-api-reference.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/unused")
os.environ.setdefault("ENVIRONMENT", "development")

from app.main import app  # noqa: E402

spec = app.openapi()
schemas = spec.get("components", {}).get("schemas", {})


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def type_of(prop: dict) -> str:
    if "$ref" in prop:
        return ref_name(prop["$ref"])
    if "anyOf" in prop:
        return " or ".join(type_of(p) for p in prop["anyOf"] if p.get("type") != "null") + " (optional)"
    if prop.get("type") == "array":
        return f"list of {type_of(prop.get('items', {}))}"
    t = prop.get("type", "any")
    if prop.get("format") in {"date", "uuid", "email", "date-time", "binary"}:
        t = prop["format"]
    if "pattern" in prop and prop["pattern"].startswith("^("):
        t = "one of " + prop["pattern"][2:-2].replace("|", ", ")
    return t


def fields(schema: dict) -> list[str]:
    if "$ref" in schema:
        schema = schemas.get(ref_name(schema["$ref"]), {})
    required = set(schema.get("required", []))
    return [f"| `{name}` | {type_of(p)} | {'yes' if name in required else ''} |" for name, p in schema.get("properties", {}).items()]


by_tag: dict[str, list[str]] = {}
for path, methods in spec["paths"].items():
    for method, op in methods.items():
        lines = [f"### `{method.upper()} /{path.lstrip('/')}`", ""]
        doc = (op.get("description") or op.get("summary") or "").strip()
        if doc:
            lines += [doc, ""]
        params = [p for p in op.get("parameters", []) if p["in"] in ("query", "path")]
        if params:
            lines += ["| Parameter | In | Type | Required |", "|---|---|---|---|"]
            lines += [f"| `{p['name']}` | {p['in']} | {type_of(p.get('schema', {}))} | {'yes' if p.get('required') else ''} |" for p in params]
            lines.append("")
        body = op.get("requestBody", {}).get("content", {})
        for media, content in body.items():
            rows = fields(content.get("schema", {}))
            if rows:
                lines += [f"Body (`{media}`):", "", "| Field | Type | Required |", "|---|---|---|", *rows, ""]
        by_tag.setdefault((op.get("tags") or ["other"])[0], []).extend(lines)

out = [
    "# myTrakIn API reference",
    "",
    "Generated from the code by `scripts/gen-api-reference.py` — do not edit by hand.",
    "",
    "Base URL: `https://<your-api-domain>/v1`. Every call except `/public/*`, `/health` and `/cron/*` needs",
    "`Authorization: Bearer <Supabase access token>` and, for workspace data, `X-Tenant-Id: <workspace id>`",
    "(optional when the person belongs to one workspace).",
    "",
    'Errors always look like `{"error": {"code": "...", "message": "..."}}`. Common codes: `unauthorized` (401), `forbidden`,',
    '`no_access` (403), `not_found` (404), `duplicate`, `conflict` (409), `invalid` (400/422).',
    "",
    "In development the interactive docs are at `/docs` (Swagger) and `/redoc`. They are switched off in production.",
    "",
    "## Contents",
    "",
    *[f"- [{tag}](#{tag.replace(' ', '-').replace('&', '').replace('--', '-').lower()})" for tag in by_tag],
    "",
]
for tag, lines in by_tag.items():
    out += [f"## {tag}", "", *lines]
target = ROOT / "docs" / "api-reference.md"
target.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"wrote {target} ({sum(len(m) for m in spec['paths'].values())} operations)")
