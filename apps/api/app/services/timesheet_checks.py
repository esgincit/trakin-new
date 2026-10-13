"""Automatic checks an admin sees before approving a timesheet.

Pure functions (no database) so they are easy to test and reuse.
Each check returns "pass", "review" (allowed, but look first) or "fail".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Entry:
    placement_id: str | None
    work_date: date
    hours: Decimal


@dataclass(frozen=True)
class PlacementInfo:
    id: str
    hours_per_week: Decimal
    start_date: date
    end_date: date | None
    bill_rate: Decimal | None
    sow_code: str | None
    sow_remaining: Decimal | None


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    result: str          # pass | review | fail
    detail: str

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "result": self.result, "detail": self.detail}


MAX_HOURS_PER_DAY = Decimal(12)
OVERTIME_AFTER = Decimal(40)


def run_checks(
    *,
    status: str,
    week_start: date,
    entries: list[Entry],
    placements: dict[str, PlacementInfo],
    engagement: str,
    show_money: bool,
) -> list[Check]:
    checks: list[Check] = []
    total = sum((e.hours for e in entries), Decimal(0))

    checks.append(Check("submitted", "Submitted by consultant",
                        "fail" if status == "draft" else "pass",
                        "Not submitted yet" if status == "draft" else "Submitted"))

    per_day: dict[date, Decimal] = defaultdict(Decimal)
    for e in entries:
        per_day[e.work_date] += e.hours
    busiest = max(per_day.values(), default=Decimal(0))
    checks.append(Check("daily_max", f"No day over {MAX_HOURS_PER_DAY} hours",
                        "fail" if busiest > MAX_HOURS_PER_DAY else "pass", f"Highest day: {busiest:g} h"))

    allocated = sum((p.hours_per_week for p in placements.values()), Decimal(0))
    checks.append(Check("allocation", "Within weekly allocation",
                        "review" if allocated and total > allocated else "pass",
                        f"{total:g} h logged vs {allocated:g} h allocated"))

    weekend = sum((e.hours for e in entries if e.work_date.weekday() >= 5), Decimal(0))
    checks.append(Check("weekend", "No weekend hours", "review" if weekend else "pass",
                        f"{weekend:g} h on the weekend — confirm the client asked for it" if weekend else "None"))

    if engagement in {"w2_fulltime", "w2_contract"}:
        overtime = max(Decimal(0), total - OVERTIME_AFTER)
        checks.append(Check("overtime", "Overtime (non-exempt W-2)", "review" if overtime else "pass",
                            f"{overtime:g} h overtime at 1.5x pay" if overtime else "None"))

    hours_by_placement: dict[str, Decimal] = defaultdict(Decimal)
    for e in entries:
        if e.placement_id:
            hours_by_placement[e.placement_id] += e.hours

    for pid, hours in hours_by_placement.items():
        p = placements.get(pid)
        if p is None:
            checks.append(Check("placement", "Hours are on an assigned project", "fail", "Unknown placement"))
            continue
        outside = [e for e in entries if e.placement_id == pid and
                   (e.work_date < p.start_date or (p.end_date and e.work_date > p.end_date)) and e.hours > 0]
        checks.append(Check(f"term:{pid}", "Placement active on every day worked",
                            "fail" if outside else "pass",
                            f"{len(outside)} day(s) outside the placement dates" if outside else "All days inside the term"))
        if p.bill_rate is not None and p.sow_remaining is not None:
            needed = hours * p.bill_rate
            ok = needed <= p.sow_remaining
            detail = (f"${needed:,.2f} needed, ${p.sow_remaining:,.2f} left" if show_money
                      else ("Enough value left" if ok else "Not enough value left"))
            checks.append(Check(f"sow:{pid}", f"Fits remaining SOW value ({p.sow_code})", "pass" if ok else "fail", detail))
    return checks


def summarize(checks: list[Check]) -> dict:
    fails = sum(1 for c in checks if c.result == "fail")
    reviews = sum(1 for c in checks if c.result == "review")
    if fails:
        return {"result": "fail", "label": f"{fails} failed"}
    if reviews:
        return {"result": "review", "label": f"{reviews} to review"}
    return {"result": "pass", "label": "All checks pass"}
