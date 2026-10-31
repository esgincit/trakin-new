"""MSAs, contractor agreements, SOWs / work orders and amendments."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, not_found
from ..services import numbering, workflow

router = APIRouter(tags=["contracts"])


class AgreementIn(BaseModel):
    code: str | None = Field(None, min_length=2, max_length=40)   # blank = from the numbering template (WF-08)
    kind: str = Field(pattern="^(msa|subcontract|ica|nda|offer_letter)$")
    company_id: UUID | None = None
    consultant_id: UUID | None = None
    tenant_side: str = Field(pattern="^(supplier|buyer|employer)$")
    effective_on: date
    expires_on: date | None = None
    payment_terms: str | None = None
    renewal: str | None = None
    notice_period: str | None = None
    insurance_required: str | None = None
    status: str = Field("active", pattern="^(draft|active)$")
    signed_by: str | None = None
    source: str = Field("manual", pattern="^(myTrakIn|manual|imported)$")

    @model_validator(mode="after")
    def _party(self):
        if not self.company_id and not self.consultant_id:
            raise ValueError("Choose the company or consultant this agreement is with")
        if self.expires_on and self.expires_on < self.effective_on:
            raise ValueError("The agreement expires before it starts")
        return self


class SowIn(BaseModel):
    code: str | None = Field(None, min_length=2, max_length=40)   # blank = from the numbering template (WF-08)
    agreement_id: UUID
    project_id: UUID | None = None                                 # WF-04: the project this SOW belongs to
    side: str = Field(pattern="^(we_bill|we_pay)$")
    title: str = Field(min_length=2, max_length=200)
    start_date: date
    end_date: date
    value_cap: Decimal | None = Field(None, ge=0)
    prior_invoiced: Decimal = Field(Decimal(0), ge=0)
    prior_paid: Decimal = Field(Decimal(0), ge=0)
    flows_from_sow_id: UUID | None = None
    status: str = Field("active", pattern="^(draft|active)$")

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("The SOW ends before it starts")
        return self


class AmendmentIn(BaseModel):
    summary: str = Field(min_length=3, max_length=300)
    new_end_date: date | None = None
    value_change: Decimal | None = None


@router.get("/agreements")
async def list_agreements(db: TenantDb = Depends(tenant_db), kind: str | None = None):
    rows = await db.all(
        """select a.*, coalesce(co.name, mytrakin.company_public_name(a.company_id), c.full_name) as counterparty,
                  (a.expires_on - current_date) as days_left,
                  (select count(*) from sows s where s.agreement_id = a.id) as sow_count, false as shared
             from agreements a left join companies co on co.id = a.company_id left join consultants c on c.id = a.consultant_id
            where (cast(:k as text) is null or a.kind = :k)""",
        {"k": kind})
    # Agreements other workspaces recorded with one of our companies (read-only, counterparty's side).
    shared = await db.all(
        """select *, (expires_on - current_date) as days_left, 0 as sow_count
             from mytrakin.shared_agreements() where (cast(:k as text) is null or kind = :k)""",
        {"k": kind})
    rows += shared
    return sorted(rows, key=lambda r: (r["expires_on"] is None, r["expires_on"] or date.max))


@router.post("/agreements", status_code=201)
async def add_agreement(body: AgreementIn, db: TenantDb = Depends(tenant_db)):
    """Add an agreement — a new draft, or one already signed outside myTrakIn (attach the PDF afterwards)."""
    db.ctx.require("legal", "account_manager", "finance", "hr")
    # An agreement is between two different parties: never the company itself.
    own_company = await db.val("select company_id from tenants where id = :t", {"t": db.ctx.tenant_id})
    if body.company_id and own_company and body.company_id == own_company:
        raise bad_request("An agreement can't be with the company itself — pick the other party")
    # Verify → NDA → MSA (WF-02): a company's MSA / subcontract needs its NDA first, unless the tenant switched that off.
    if body.kind in ("msa", "subcontract") and body.company_id and (await workflow.rules(db))["requireNDA"] \
            and not await workflow.has_active_agreement(db, kinds=("nda",), company_id=body.company_id):
        note = await workflow.stale_note(db, kinds=("nda",), company_id=body.company_id)
        why = f" — {note}" if note else ""
        raise workflow.blocked("nda_required", f"An NDA in force with this company is needed first{why} "
                                               "(or turn off 'Require NDA' in Settings → Workflow)")
    counterparty = await db.val(
        """select coalesce((select name from mytrakin.company_counterparty(cast(:co as uuid))),
                           (select full_name from consultants where id = cast(:con as uuid)))""",
        {"co": body.company_id, "con": body.consultant_id})
    code = (body.code or "").strip().upper() or await numbering.next_code(db, body.kind, CLIENT=counterparty)
    # An MSA with a company is pending until that company accepts it (or rejects it).
    status = "pending" if body.kind in ("msa", "subcontract") and body.company_id else body.status
    return await db.one(
        """insert into agreements (tenant_id, code, kind, company_id, consultant_id, tenant_side, effective_on, expires_on,
                                   payment_terms, renewal, notice_period, insurance_required, status, signed_by, source)
           values (:t, :code, :kind, :co, :con, :side, :eff, :exp, :terms, :renew, :notice, :ins, :status, :by, :src)
           returning *""",
        {"t": db.ctx.tenant_id, "code": code, "kind": body.kind, "co": body.company_id, "con": body.consultant_id,
         "side": body.tenant_side, "eff": body.effective_on, "exp": body.expires_on, "terms": body.payment_terms,
         "renew": body.renewal, "notice": body.notice_period, "ins": body.insurance_required, "status": status,
         "by": body.signed_by, "src": body.source})


class RespondIn(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")
    note: str | None = Field(None, max_length=1000)


class RenewalIn(BaseModel):
    expires_on: date
    note: str | None = Field(None, max_length=1000)


class RenewalDecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept|decline)$")
    note: str | None = Field(None, max_length=1000)


@router.post("/agreements/{agreement_id}/respond")
async def respond_to_agreement(agreement_id: UUID, body: RespondIn, db: TenantDb = Depends(tenant_db)):
    """The company an MSA was sent to accepts it (it comes into force) or rejects it with a note."""
    await db.run("select mytrakin.respond_to_agreement(:a, :d, :n)",
                 {"a": agreement_id, "d": "accept" if body.decision == "accept" else "reject", "n": body.note})
    return await get_agreement(agreement_id, db)


@router.post("/agreements/{agreement_id}/renewals", status_code=201)
async def request_renewal(agreement_id: UUID, body: RenewalIn, db: TenantDb = Depends(tenant_db)):
    """Either company asks to renew an MSA until a new end date. The other company accepts or declines."""
    rid = await db.val("select mytrakin.request_renewal(:a, :e, :n)",
                       {"a": agreement_id, "e": body.expires_on, "n": body.note})
    return {"id": rid, "status": "pending"}


@router.post("/agreements/renewals/{renewal_id}/respond")
async def respond_to_renewal(renewal_id: UUID, body: RenewalDecisionIn, db: TenantDb = Depends(tenant_db)):
    """Accept a renewal (the end date moves to the one proposed) or decline it with a note."""
    await db.run("select mytrakin.respond_to_renewal(:r, :d, :n)",
                 {"r": renewal_id, "d": "accept" if body.decision == "accept" else "decline", "n": body.note})
    return {"id": renewal_id, "decision": body.decision}


@router.get("/agreements/{agreement_id}")
async def get_agreement(agreement_id: UUID, db: TenantDb = Depends(tenant_db)):
    row = await db.one(
        """select a.*, coalesce(co.name, mytrakin.company_public_name(a.company_id), c.full_name) as counterparty, false as shared
             from agreements a
              left join companies co on co.id = a.company_id left join consultants c on c.id = a.consultant_id where a.id = :id""",
        {"id": agreement_id})
    if row is None:
        # Shared with one of our companies: the counterparty sees the terms, not the sender's SOWs or signatures.
        row = await db.one("select *, (expires_on - current_date) as days_left from mytrakin.shared_agreements() where id = :id",
                           {"id": agreement_id})
        if row is None:
            raise not_found("Agreement")
        row["sows"] = []
        row["envelopes"] = []
        row["renewals"] = await db.all("select * from mytrakin.agreement_renewals_for(:a)", {"a": agreement_id})
        return row
    row["sows"] = await db.all("select s.id, s.code, s.title, s.end_date, b.burn_pct from sows s left join sow_burn b on b.sow_id = s.id "
                               "where s.agreement_id = :id order by s.end_date", {"id": agreement_id})
    row["envelopes"] = await db.all(
        """select e.id, e.number, e.title, e.status, e.completed_at, e.sent_at,
                  (select coalesce(json_agg(json_build_object('id', d.id, 'name', d.name, 'size_bytes', d.size_bytes)
                                           order by d.position), '[]'::json)
                     from mytrakin.envelope_documents d where d.envelope_id = e.id) as documents
             from envelopes e where e.agreement_id = :id order by e.created_at desc""",
        {"id": agreement_id})
    row["renewals"] = await db.all("select * from mytrakin.agreement_renewals_for(:a)", {"a": agreement_id})
    return row


class AgreementPatch(BaseModel):
    effective_on: date | None = None
    expires_on: date | None = None
    payment_terms: str | None = None
    renewal: str | None = None
    notice_period: str | None = None
    insurance_required: str | None = None
    tenant_side: str | None = Field(None, pattern="^(supplier|buyer|employer)$")


@router.patch("/agreements/{agreement_id}")
async def edit_agreement(agreement_id: UUID, body: AgreementPatch, db: TenantDb = Depends(tenant_db)):
    """Edit a draft agreement before it is sent for signature. Only drafts can be edited."""
    db.ctx.require("legal", "account_manager", "finance", "hr")
    row = await db.one(
        "select status, kind from agreements where id = :id", {"id": agreement_id})
    if row is None:
        raise not_found("Agreement")
    if row["status"] != "draft":
        raise bad_request("Only draft agreements can be edited")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise bad_request("No fields to update")
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = agreement_id
    await db.run(
        f"""update agreements set {set_clause} where id = :id""", updates)
    return await get_agreement(agreement_id, db)


@router.get("/sows")
async def list_sows(db: TenantDb = Depends(tenant_db), side: str | None = None):
    show_value = db.ctx.allows("finance", "legal", "account_manager")
    rows = await db.all(
        """select s.id, s.code, s.side, s.title, s.start_date, s.end_date, s.status, s.value_cap,
                  s.sent_on, s.decided_on, s.decision_note, coalesce(a.code, sa.code) as agreement, coalesce(co.name, mytrakin.company_public_name(s.company_id), c.full_name) as counterparty,
                  b.invoiced, b.collected_or_paid, b.burn_pct, (s.value_cap - b.invoiced) as remaining,
                  (s.end_date - current_date) as days_left, fs.code as flows_from, s.project_id, pj.code as project, pj.name as project_name,
                  (select string_agg(distinct k.full_name, ', ') from placements p join consultants k on k.id = p.consultant_id
                    where s.id in (p.ar_sow_id, p.ap_sow_id)) as consultants,
                  (select a2.code || ': ' || a2.status from sow_amendments a2 where a2.sow_id = s.id and a2.status <> 'void'
                    order by a2.created_at desc limit 1) as latest_amendment
             from sows s
             -- our SOW may sit under the other workspace's MSA (hidden by RLS): read its code via the shared view
             left join agreements a on a.id = s.agreement_id
             left join mytrakin.shared_agreements() sa on a.id is null and sa.id = s.agreement_id
             left join companies co on co.id = s.company_id
             left join consultants c on c.id = s.consultant_id
             left join sow_burn b on b.sow_id = s.id
             left join sows fs on fs.id = s.flows_from_sow_id
             left join projects pj on pj.id = s.project_id
where (cast(:side as text) is null or s.side = :side)
             order by s.end_date""",
        {"side": side})
    # SOWs another workspace created under an MSA we are a party to, and has sent for
    # approval. Shown from our side (we bill / we pay swapped), and without any money.
    incoming = await db.all(
        """select * from mytrakin.shared_sows() where (cast(:side as text) is null or side = :side)
            order by end_date""",
        {"side": side})
    for r in incoming:
        r["shared"] = True
        r["agreement"] = r["agreement_code"]   # the page reads "agreement" ("Under agreement" was blank)
        for k in ("value_cap", "invoiced", "collected_or_paid", "remaining", "burn_pct"):
            r[k] = None
    rows += incoming
    if not show_value:
        for r in rows:
            for k in ("value_cap", "invoiced", "collected_or_paid", "remaining"):
                r[k] = None
    return rows


async def _agreement_for_sow(db: TenantDb, agreement_id: Any) -> tuple[dict, bool]:
    """The agreement a SOW is raised under, from this workspace's side.

    Returns (agreement, shared). A shared one is an MSA another workspace recorded with
    one of our companies -- work under it runs from here just the same, whichever side
    sent it. Also returns the company the SOW is *with*, which is not simply the
    agreement's company_id when we are the counterparty: seen from here that would be
    our own company.
    """
    row = await db.one("select * from agreements where id = :id", {"id": agreement_id})
    if row is not None:
        return row, False
    shared = await db.one(
        "select *, (expires_on - current_date) as days_left from mytrakin.shared_agreements() where id = :id",
        {"id": agreement_id})
    if shared is None:
        raise not_found("Agreement")
    return shared, True


@router.post("/sows", status_code=201)
async def add_sow(body: SowIn, db: TenantDb = Depends(tenant_db)):
    """Add a SOW / work order — new, or already signed outside myTrakIn with what was invoiced before.

    The agreement may be one this workspace recorded or one another workspace recorded
    with one of our companies: work under an MSA runs both ways.
    """
    db.ctx.require("legal", "account_manager")
    agreement, shared = await _agreement_for_sow(db, body.agreement_id)
    # AGR-09: no new SOWs under an agreement that has ended.
    if agreement["status"] in ("expired", "terminated") or (agreement["expires_on"] and agreement["expires_on"] < date.today()):
        raise conflict("This agreement has expired — renew it before adding SOWs under it")
    if agreement["status"] == "rejected":
        raise conflict("This MSA was turned down — agree it again before adding SOWs under it")
    if agreement["status"] not in ("accepted", "active", "draft", "out_for_signature", "pending"):
        raise conflict("This agreement is not in force yet — get it accepted before adding SOWs under it")
    # The company this SOW is with: the other party, whichever workspace recorded the MSA.
    company = await db.val("select mytrakin.agreement_peer_company(:a)", {"a": body.agreement_id})
    if company is None:
        raise bad_request("This agreement has no other company on it — a SOW needs a company on both sides")
    project_code = None
    if body.project_id:
        project_code = await db.val("select code from projects where id = :id", {"id": body.project_id})
        if project_code is None:
            raise not_found("Project")
    if body.flows_from_sow_id:
        upstream = await db.one("select end_date from sows where id = :id", {"id": body.flows_from_sow_id})
        if upstream and body.end_date > upstream["end_date"]:
            raise bad_request("A vendor SOW can't run past the client SOW it supports")
    # Client SOWs and vendor / contractor work orders (the resource contract) have their own numbering.
    code = (body.code or "").strip().upper() or await numbering.next_code(
        db, "sow" if body.side == "we_bill" else "contract", PROJECT=project_code)
    return await db.one(
        """insert into sows (tenant_id, code, agreement_id, project_id, side, company_id, consultant_id, title, start_date,
                             end_date, value_cap, prior_invoiced, prior_paid, flows_from_sow_id, status)
           values (:t, :code, :ag, :pr, :side, :co, :con, :title, :start, :end, :cap, :pi, :pp, :from, :status) returning *""",
        {"t": db.ctx.tenant_id, "code": code, "ag": body.agreement_id, "pr": body.project_id, "side": body.side,
         "co": company, "con": None if shared else agreement["consultant_id"], "title": body.title,
         "start": body.start_date, "end": body.end_date, "cap": body.value_cap, "pi": body.prior_invoiced,
         "pp": body.prior_paid, "from": body.flows_from_sow_id, "status": body.status})


@router.post("/projects/{project_id}/sows", status_code=201)
async def add_project_sow(project_id: UUID, body: SowIn, db: TenantDb = Depends(tenant_db)):
    """Add a SOW (or a vendor / contractor work order) under a project (WF-04)."""
    body.project_id = project_id
    return await add_sow(body, db)


@router.get("/sows/{sow_id}")
async def get_sow(sow_id: UUID, db: TenantDb = Depends(tenant_db)):
    rows = [r for r in await list_sows(db) if r["id"] == sow_id]
    if not rows:
        raise not_found("SOW")
    sow = rows[0]
    if sow.get("shared"):
        # Another workspace's SOW: terms to approve, nothing of ours to change, no money.
        sow["amendments"] = []
        sow["flows_to"] = []
        sow["envelopes"] = []
        sow["invoices"] = []
        return sow
    sow["amendments"] = await db.all("select * from sow_amendments where sow_id = :id order by created_at desc", {"id": sow_id})
    sow["flows_to"] = await db.all("select id, code, end_date from sows where flows_from_sow_id = :id", {"id": sow_id})
    sow["envelopes"] = await db.all(
        """select e.id, e.number, e.title, e.status, e.completed_at from envelopes e
            where e.sow_id = :id or e.amendment_id in (select id from sow_amendments where sow_id = :id)
            order by e.created_at desc""", {"id": sow_id})
    if db.ctx.allows("finance", "legal", "account_manager"):
        sow["invoices"] = await db.all(
            "select id, number, direction, period_start, amount, balance, live_status from invoice_balances where sow_id = :id "
            "order by period_start desc", {"id": sow_id})
    return sow


class SowDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(None, max_length=1000)


@router.post("/sows/{sow_id}/submit")
async def submit_sow(sow_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Send a draft SOW to the other company for approval. Until this is done it is a
    draft and the other company cannot see it."""
    db.ctx.require("legal", "account_manager")
    await db.run("select mytrakin.submit_sow_for_approval(:s)", {"s": sow_id})
    return await get_sow(sow_id, db)


@router.post("/sows/{sow_id}/respond")
async def respond_to_sow(sow_id: UUID, body: SowDecisionIn, db: TenantDb = Depends(tenant_db)):
    """The company a SOW was sent to approves it (it comes into force) or turns it down
    with a reason."""
    await db.run("select mytrakin.respond_to_sow(:s, :d, :n)",
                 {"s": sow_id, "d": body.decision, "n": body.note})
    return await get_sow(sow_id, db)


@router.post("/sows/{sow_id}/amendments", status_code=201)
async def add_amendment(sow_id: UUID, body: AmendmentIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("legal", "account_manager")
    sow = await db.one("select code from sows where id = :id", {"id": sow_id})
    if sow is None:
        raise not_found("SOW")
    count = await db.val("select count(*) from sow_amendments where sow_id = :id", {"id": sow_id})
    return await db.one(
        """insert into sow_amendments (tenant_id, sow_id, code, summary, new_end_date, value_change)
           values (:t, :s, :code, :summary, :end, :value) returning *""",
        {"t": db.ctx.tenant_id, "s": sow_id, "code": f"AMD-{sow['code']}-{count + 1}", "summary": body.summary,
         "end": body.new_end_date, "value": body.value_change})


@router.get("/contracts/missing")
async def missing_items(db: TenantDb = Depends(tenant_db)):
    """What is missing or expiring: agreements, NDAs, offers, policies, documents."""
    if not db.ctx.internal:
        return []
    return await db.all(
        """select * from (
             select 'agreement' as category, 'bad' as tone, c.name as who, 'No MSA on file' as what, 'company' as ref_type, c.id::text as ref_id
               from companies c
               where c.status <> 'inactive' and c.kinds && array['client', 'prime_vendor', 'vendor']
                and not exists (select 1 from agreements a where a.company_id = c.id and a.status in ('active', 'accepted', 'out_for_signature')
                                 and (a.expires_on is null or a.expires_on >= current_date))
             union all
             select 'agreement', 'bad', k.full_name,
                    case k.engagement when '1099' then 'Independent contractor agreement missing' else 'Offer letter not signed' end,
                    'consultant', k.id::text
               from consultants k
              where k.status <> 'former' and k.engagement in ('1099', 'w2_fulltime', 'w2_contract')
                and not exists (select 1 from agreements a where a.consultant_id = k.id
                                 and a.kind = case k.engagement when '1099' then 'ica' else 'offer_letter' end and a.status = 'active')
             union all
             select 'agreement', 'bad', k.full_name, 'NDA not signed', 'consultant', k.id::text
               from consultants k
              where k.status <> 'former'
                and not exists (select 1 from agreements a where a.consultant_id = k.id and a.kind = 'nda' and a.status = 'active'
                                 and (a.expires_on is null or a.expires_on >= current_date))
             union all
             select 'policy', 'warn', k.full_name, 'Not accepted: ' || string_agg(po.name || ' ' || po.version, ', '), 'consultant', k.id::text
               from consultants k join policies po on po.active and k.engagement = any (po.applies_to)
              where k.status = 'active'
                and not exists (select 1 from policy_acceptances pa where pa.policy_id = po.id and pa.consultant_id = k.id)
              group by k.id
             union all
             select 'document', case when d.status = 'missing' or d.expires_on - current_date <= 30 then 'bad' else 'warn' end,
                    coalesce(k.full_name, co.name), d.label || coalesce(' — expires ' || to_char(d.expires_on, 'Mon DD, YYYY'), ' — missing'),
                    'tracked_document', d.id::text
               from tracked_documents d left join consultants k on k.id = d.consultant_id left join companies co on co.id = d.company_id
              where d.active and (d.status = 'missing' or d.expires_on <= current_date + 120)
           ) x order by tone, category, who""")
