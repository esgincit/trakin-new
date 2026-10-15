"""Naming engine templates (WF-08) — pure functions, no database."""

from datetime import date

import pytest

from app.services.numbering import format_code, validate


def test_templates():
    d = date(2026, 10, 15)
    assert format_code("PROJ-{YEAR}-{SEQ:3}", 7, d, {}) == "PROJ-2026-007"
    assert format_code("INV-{YYYYMM}-{SEQ}", 12, d, {}) == "INV-202610-12"
    assert format_code("MSA-{CLIENT}-{SEQ:2}", 3, d, {"CLIENT": "Northwind & Co"}) == "MSA-NORTHWINDCO-03"
    assert format_code("SOW-{PROJECT}-{SEQ:3}", 1, d, {"PROJECT": None}) == "SOW-GEN-001"
    with pytest.raises(ValueError):
        format_code("X-{NOPE}-{SEQ}", 1, d, {})


def test_validate():
    assert validate({"project": "PROJ-{YEAR}-{SEQ:3}"})
    with pytest.raises(ValueError):
        validate({"project": "PROJ-{YEAR}"})          # no sequence → duplicates
    with pytest.raises(ValueError):
        validate({"project": "PROJ-{CUSTOMER}-{SEQ}"})  # unknown placeholder
