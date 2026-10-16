"""MSAs, contractor agreements, SOWs / work orders and amendments."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
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
    return await db.all(
        """select a.*, coalesce(co.name, mytrakin.company_public_name(a.company_id), c.full_name) as counterparty,
                  (a.expires_on - current_date) as days_left,
                  (select count(*) from sows s where s.agreement_id = a.id) as sow_count
             from agreements a left join companies co on co.id = a.company_id left join consultants c on c.id = a.consultant_id
            where (cast(:k as text) is null or a.kind = :k)
            order by a.expires_on nulls last""",
        {"k": kind})


@router.post("/agreements", status_code=201)
async def add_agreement(body: AgreementIn, db: TenantDb = Depends(tenant_db)):
    """Add an agreement — a new draft, or one already signed outside myTrakIn (attach the PDF afterwards)."""
    db.ctx.require("legal", "account_manager", "finance", "hr")
    # Verify → NDA → MSA (WF-02): a company's MSA / subcontract needs its NDA first, unless the tenant switched that off.
    if body.kind in ("msa", "subcontract") and body.company_id and (await workflow.rules(db))["requireNDA"] \
            and not await workflow.has_active_agreement(db, kinds=("nda",), company_id=body.company_id):
        raise workflow.blocked("nda_required", "Sign an NDA with this company before its MSA "
                                               "(or turn off 'Require NDA' in Settings → Workflow)")
    counterparty = await db.val(
        """select coalesce((select name from mytrakin.company_counterparty(cast(:co as uuid))),
                           (select full_name from consultants where id = cast(:con as uuid)))""",
        {"co": body.company_id, "con": body.consultant_id})
    code = (body.code or "").strip().upper() or await numbering.next_code(db, body.kind, CLIENT=counterparty)
    return await db.one(
        """insert into agreements (tenant_id, code, kind, company_id, consultant_id, tenant_side, effective_on, expires_on,
                                   payment_terms, renewal, notice_period, insurance_required, status, signed_by, source)
           values (:t, :code, :kind, :co, :con, :side, :eff, :exp, :terms, :renew, :notice, :ins, :status, :by, :src)
           returning *""",
        {"t": db.ctx.tenant_id, "code": code, "kind": body.kind, "co": body.company_id, "con": body.consultant_id,
         "side": body.tenant_side, "eff": body.effective_on, "exp": body.expires_on, "terms": body.payment_terms,
         "renew": body.renewal, "notice": body.notice_period, "ins": body.insurance_required, "status": body.status,
         "by": body.signed_by, "src": body.source})


@router.get("/agreements/{agreement_id}")
async def get_agreement(agreement_id: UUID, db: TenantDb = Depends(tenant_db)):
    row = await db.one(
        """select a.*, coalesce(co.name, mytrakin.company_public_name(a.company_id), c.full_name) as counterparty from agreements a
              left join companies co on co.id = a.company_id left join consultants c on c.id = a.consultant_id where a.id = :id""",
        {"id": agreement_id})
    if row is None:
        raise not_found("Agreement")
    row["sows"] = await db.all("select s.id, s.code, s.title, s.end_date, b.burn_pct from sows s left join sow_burn b on b.sow_id = s.id "
                               "where s.agreement_id = :id order by s.end_date", {"id": agreement_id})
    row["envelopes"] = await db.all("select id, number, title, status, completed_at from envelopes where agreement_id = :id "
                                    "order by created_at desc", {"id": agreement_id})
    return row


@router.get("/sows")
async def list_sows(db: TenantDb = Depends(tenant_db), side: str | None = None):
    show_value = db.ctx.allows("finance", "legal", "account_manager")
    rows = await db.all(
        """select s.id, s.code, s.side, s.title, s.start_date, s.end_date, s.status, s.value_cap,
                  a.code as agreement, coalesce(co.name, mytrakin.company_public_name(s.company_id), c.full_name) as counterparty,
                  b.invoiced, b.collected_or_paid, b.burn_pct, (s.value_cap - b.invoiced) as remaining,
                  (s.end_date - current_date) as days_left, fs.code as flows_from, s.project_id, pj.code as project,
                  (select string_agg(distinct k.full_name, ', ') from placements p join consultants k on k.id = p.consultant_id
                    where s.id in (p.ar_sow_id, p.ap_sow_id)) as consultants,
                  (select a2.code || ': ' || a2.status from sow_amendments a2 where a2.sow_id = s.id and a2.status <> 'void'
                    order by a2.created_at desc limit 1) as latest_amendment
             from sows s
             join agreements a on a.id = s.agreement_id
             left join companies co on co.id = s.company_id
             left join consultants c on c.id = s.consultant_id
             left join sow_burn b on b.sow_id = s.id
             left join sows fs on fs.id = s.flows_from_sow_id
             left join projects pj on pj.id = s.project_id
            where (cast(:side as text) is null or s.side = :side)
            order by s.end_date""",
        {"side": side})
    if not show_value:
        for r in rows:
            for k in ("value_cap", "invoiced", "collected_or_paid", "remaining"):
                r[k] = None
    return rows


@router.post("/sows", status_code=201)
async def add_sow(body: SowIn, db: TenantDb = Depends(tenant_db)):
    """Add a SOW / work order — new, or already signed outside myTrakIn with what was invoiced before."""
    db.ctx.require("legal", "account_manager")
    agreement = await db.one("select company_id, consultant_id, expires_on, status from agreements where id = :id",
                             {"id": body.agreement_id})
    if agreement is None:
        raise not_found("Agreement")
    # AGR-09: no new SOWs under an agreement that has ended.
    if agreement["status"] in ("expired", "terminated") or (agreement["expires_on"] and agreement["expires_on"] < date.today()):
        raise conflict("This agreement has expired — renew it before adding SOWs under it")
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
         "co": agreement["company_id"], "con": agreement["consultant_id"], "title": body.title, "start": body.start_date,
         "end": body.end_date, "cap": body.value_cap, "pi": body.prior_invoiced, "pp": body.prior_paid,
         "from": body.flows_from_sow_id, "status": body.status})


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
                and not exists (select 1 from agreements a where a.company_id = c.id and a.status in ('active', 'out_for_signature'))
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
                and not exists (select 1 from agreements a where a.consultant_id = k.id and a.kind = 'nda' and a.status = 'active')
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
