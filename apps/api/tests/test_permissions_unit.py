"""Permission core, no database: pytest tests/test_permissions_unit.py --noconftest"""

import pytest

from app.errors import ApiError
from app.permissions import MODULES, check, effective, required


def test_default_is_full_access_within_the_base_role():
    eff = effective(None, None)
    assert set(eff) == set(MODULES) and set(eff.values()) == {"write"}


def test_override_beats_role_beats_default():
    eff = effective({"invoices": "read", "users": "none"}, {"invoices": "write"})
    assert eff["invoices"] == "write" and eff["users"] == "none" and eff["timesheets"] == "write"


@pytest.mark.parametrize("method,path,want", [
    ("GET", "/v1/invoices", ("invoices", "read")),
    ("POST", "/v1/invoices/abc/payments", ("invoices", "write")),
    ("GET", "/v1/vendor-invoices", ("invoices", "read")),
    ("PATCH", "/v1/sows/1", ("contracts", "write")),
    ("POST", "/v1/insights/ask", ("dashboard", "read")),
    ("GET", "/v1/session", None),
    ("GET", "/v1/notifications", None),
    ("GET", "/v1/invoicesx", None),
])
def test_required(method, path, want):
    assert required(method, path) == want


def test_read_only_blocks_write_but_not_read():
    perms = effective({"invoices": "read"}, None)
    check(perms, "GET", "/v1/invoices", is_owner=False)
    with pytest.raises(ApiError) as e:
        check(perms, "POST", "/v1/invoices", is_owner=False)
    assert e.value.code == "no_permission" and "view-only" in e.value.message


def test_hidden_blocks_reading_and_owner_is_never_blocked():
    perms = effective({"users": "none"}, None)
    with pytest.raises(ApiError) as e:
        check(perms, "GET", "/v1/users", is_owner=False)
    assert "don't have access" in e.value.message
    check(perms, "GET", "/v1/users", is_owner=True)
