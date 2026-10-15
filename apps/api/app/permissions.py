"""Owner-configurable permissions: per module none / read / write, on top of the base role.

Base roles still decide which rows a user sees and which amounts are masked (RLS, RULE-01/02);
a permission can only narrow that. Missing entries mean "write" (= whatever the base role allows).
ponytail: URL-prefix → module map; widening beyond the base role needs the role checks rewritten (P-12).
"""

from __future__ import annotations

from .errors import ApiError

LEVELS = ("none", "read", "write")

# key: (label shown to the owner, URL prefixes after /v1)
MODULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "dashboard": ("Dashboard & insights", ("/dashboard", "/insights")),
    "companies": ("Clients & vendors", ("/companies",)),
    "contracts": ("Contracts, SOWs & e-signatures", ("/agreements", "/contracts", "/sows", "/acceptances", "/envelopes")),
    "projects": ("Projects & placements", ("/projects", "/placements")),
    "consultants": ("Consultants", ("/consultants",)),
    "timesheets": ("Timesheets", ("/timesheets",)),
    "invoices": ("Invoices & payments", ("/invoices", "/vendor-invoices", "/payment-flow", "/payment-runs", "/payments")),
    "pay": ("Payroll, expenses, time off & 1099", ("/expenses", "/form-1099", "/payroll", "/referrals", "/time-off")),
    "compliance": ("Compliance & policies", ("/compliance", "/files", "/policies", "/registrations", "/reminder-rules")),
    "data": ("Import & export", ("/data",)),
    "users": ("Users", ("/users",)),
    "settings": ("Company settings", ("/workspace",)),
    "audit": ("Audit log", ("/audit",)),
}
READ_POSTS = ("/insights/ask",)   # POSTs that only read


def effective(role_perms: dict | None, overrides: dict | None) -> dict[str, str]:
    role_perms, overrides = role_perms or {}, overrides or {}
    return {m: overrides.get(m) or role_perms.get(m) or "write" for m in MODULES}


def required(method: str, path: str) -> tuple[str, str] | None:
    p = path.removeprefix("/v1")
    for key, (_, prefixes) in MODULES.items():
        if any(p == x or p.startswith(x + "/") for x in prefixes):
            return key, "read" if method in ("GET", "HEAD", "OPTIONS") or p in READ_POSTS else "write"
    return None


def check(perms: dict[str, str], method: str, path: str, *, is_owner: bool) -> None:
    need = required(method, path)
    if need is None or is_owner:
        return
    module, action = need
    have = perms.get(module, "write")
    if LEVELS.index(have) < LEVELS.index(action):
        label = MODULES[module][0]
        raise ApiError(403, "no_permission",
                       f"You have view-only access to {label}." if have == "read" else f"You don't have access to {label}.")
