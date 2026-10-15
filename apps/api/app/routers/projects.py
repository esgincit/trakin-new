"""Projects and placements (who works on what, and the AR/AP terms for each)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from ..deps import TenantDb, tenant_db
from ..errors import bad_request, not_found
from ..services import numbering, workflow
from ..utils import week_start

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    code: str | None = Field(None, min_length=2, max_length=30)   # blank = auto-assigned (PRJ-01, PRJ-02, ...)
    name: str = Field(min_length=2, max_length=200)
    client_company_id: UUID | None = None
    prime_company_id: UUID | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    client_approver: str | None = None
    status: str = Field("active", pattern="^(planned|active|completed|internal)$")


class PlacementIn(BaseModel):
    consultant_id: UUID
    project_id: UUID
    role_title: str | None = None
    start_date: date
    end_date: date | None = None
    hours_per_week: Decimal = Field(Decimal(40), gt=0, le=80)
    end_client_company_id: UUID | None = None
    ar_company_id: UUID | None = None
    ar_sow_id: UUID | None = None
    bill_rate: Decimal | None = Field(None, ge=0)
    ar_terms: str | None = None
    ap_company_id: UUID | None = None
    ap_consultant_id: UUID | None = None
    ap_sow_id: UUID | None = None
    pay_rate: Decimal | None = Field(None, ge=0)
    ap_terms: str | None = None
    pay_when_paid: bool = False

    @model_validator(mode="after")
    def _one_payee(self):
        if self.ap_company_id and self.ap_consultant_id:
            raise ValueError("Choose either a vendor company or a 1099 contractor as the payee, not both")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date is before the start date")
        return self


class PlacementPatch(BaseModel):
    role_title: str | None = None
    end_date: date | None = None
    hours_per_week: Decimal | None = Field(None, gt=0, le=80)
    status: str | None = Field(None, pattern="^(onboarding|active|ending|completed|ended)$")
    bill_rate: Decimal | None = Field(None, ge=0)
    pay_rate: Decimal | None = Field(None, ge=0)
    ar_terms: str | None = None
    ap_terms: str | None = None
    pay_when_paid: bool | None = None


# ----------------------------------------------------------------------------- projects
async def _client_name(db: TenantDb, company_id) -> str | None:
    return await db.val("select name from companies where id = :id", {"id": company_id}) if company_id else None


@router.get("/projects/next-code")
async def next_project_code(db: TenantDb = Depends(tenant_db), client_company_id: UUID | None = None):
    """Suggested code for the New project form, from the tenant's numbering template (the field stays editable)."""
    return {"code": await numbering.preview_code(db, "project", CLIENT=await _client_name(db, client_company_id))}


@router.get("/projects")
async def list_projects(db: TenantDb = Depends(tenant_db)):
    show_money = db.ctx.allows("finance")
    rows = await db.all(
        """select pr.id, pr.code, pr.name, pr.status, pr.start_date, pr.end_date, pr.description, pr.client_approver,
                  cl.name as client, pm.name as prime,
                  (select count(*) from placements p where p.project_id = pr.id and p.status in ('active', 'ending', 'onboarding')) as team_size,
                  (select string_agg(c.full_name, ', ' order by c.full_name) from placements p join consultants c on c.id = p.consultant_id
                    where p.project_id = pr.id and p.status in ('active', 'ending', 'onboarding')) as team,
                  (select coalesce(sum(i.amount), 0) from invoices i join placements p on p.id = i.placement_id
                    where p.project_id = pr.id and i.direction = 'ar' and i.status <> 'void') as invoiced
             from projects pr
             left join companies cl on cl.id = pr.client_company_id
             left join companies pm on pm.id = pr.prime_company_id
            order by pr.status = 'completed', pr.name""")
    if not show_money:
        for r in rows:
            r.pop("invoiced")
    return rows


async def _activation_gate(db: TenantDb, body: ProjectIn) -> None:
    """NDA → MSA → Project (WF-03): an active project needs the customer's NDA and MSA, per the workflow switches.
    The customer is the prime when the project comes through one, otherwise the client."""
    customer = body.prime_company_id or body.client_company_id
    if body.status != "active" or customer is None:
        return
    rules = await workflow.rules(db)
    name = await _client_name(db, customer)
    if rules["requireNDA"] and not await workflow.has_active_agreement(db, kinds=("nda",), company_id=customer):
        raise workflow.blocked("nda_required", f"{name} has no signed NDA — the project can't be activated yet "
                                               "(save it as planned, or turn off 'Require NDA' in Settings → Workflow)")
    if rules["requireMSA"] and not await workflow.has_active_agreement(db, kinds=workflow.MASTER_KINDS, company_id=customer):
        raise workflow.blocked("msa_required", f"{name} has no active MSA — the project can't be activated yet "
                                               "(save it as planned, or turn off 'Require MSA' in Settings → Workflow)")


@router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("account_manager")
    await _activation_gate(db, body)
    code = (body.code or "").strip().upper() or None
    for _ in range(5):   # blank code, or a suggestion taken in the meantime: pick the next free one
        if code is None:
            code = await numbering.next_code(db, "project", CLIENT=await _client_name(db, body.client_company_id))
        try:
            # Savepoint: a colliding insert rolls back to here, not the whole request.
            async with db.conn.begin_nested():
                return await db.one(
                    """insert into projects (tenant_id, code, name, client_company_id, prime_company_id, description, start_date, end_date,
                                             client_approver, status)
                       values (:t, :code, :name, :client, :prime, :desc, :start, :end, :approver, :status) returning *""",
                    {"t": db.ctx.tenant_id, "code": code, "name": body.name, "client": body.client_company_id,
                     "prime": body.prime_company_id, "desc": body.description, "start": body.start_date, "end": body.end_date,
                     "approver": body.client_approver, "status": body.status})
        except IntegrityError:
            code = None   # collision: recompute and try again
    raise bad_request("That project code is already in use — try another")


@router.get("/projects/{project_id}")
async def get_project(project_id: UUID, db: TenantDb = Depends(tenant_db)):
    project = await db.one(
        """select pr.*, cl.name as client, pm.name as prime from projects pr
             left join companies cl on cl.id = pr.client_company_id left join companies pm on pm.id = pr.prime_company_id
            where pr.id = :id""", {"id": project_id})
    if project is None:
        raise not_found("Project")
    project["team"] = await db.all(
        """select p.id as placement_id, c.id as consultant_id, c.full_name, c.engagement, p.role_title, p.hours_per_week,
                  p.start_date, p.end_date, p.status,
                  (select t.status from timesheets t where t.consultant_id = c.id and t.week_start = :wk) as this_week
             from placements p join consultants c on c.id = p.consultant_id
            where p.project_id = :id order by p.status = 'active' desc, c.full_name""",
        {"id": project_id, "wk": week_start(date.today())})
    # WF-04: the project's SOWs and work orders, each with how many resources it covers.
    project["sows"] = await db.all(
        """select s.id, s.code, s.title, s.side, s.status, s.end_date, b.burn_pct,
                  (select count(*) from placements p where s.id in (p.ar_sow_id, p.ap_sow_id)) as resources
             from sows s left join sow_burn b on b.sow_id = s.id
            where s.project_id = :id
               or s.id in (select ar_sow_id from placements where project_id = :id)
            order by s.side, s.code""", {"id": project_id})
    project["files"] = await db.all(
        "select id, name, size_bytes, mime_type, created_at from documents where owner_type = 'project' and owner_id = :id "
        "and deleted_at is null order by created_at desc", {"id": project_id})
    return project


@router.patch("/projects/{project_id}")
async def update_project(project_id: UUID, body: ProjectIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("account_manager")
    if not (body.code or "").strip():
        raise bad_request("The project code can't be empty")
    await _activation_gate(db, body)
    row = await db.one(
        """update projects set code = :code, name = :name, client_company_id = :client, prime_company_id = :prime,
                  description = :desc, start_date = :start, end_date = :end, client_approver = :approver, status = :status
            where id = :id returning *""",
        {"id": project_id, "code": (body.code or "").strip().upper(), "name": body.name, "client": body.client_company_id,
         "prime": body.prime_company_id, "desc": body.description, "start": body.start_date, "end": body.end_date,
         "approver": body.client_approver, "status": body.status})
    if row is None:
        raise not_found("Project")
    return row


# ----------------------------------------------------------------------------- placements
def placement_view(row: dict, ctx) -> dict:
    """Only ever show the caller the rates they're allowed to see."""
    if not ctx.sees_bill_rate:
        row["bill_rate"] = None
    if not ctx.sees_pay_rate:
        row["pay_rate"] = None
    if ctx.role == "vendor_admin" and row.get("ap_company_id") != ctx.company_id:
        row["pay_rate"] = None
    if ctx.role == "client_user":
        row["pay_rate"] = None
    return row


_PLACEMENT_SQL = """
select p.*, c.full_name as consultant, c.engagement, pr.name as project, pr.code as project_code,
       ec.name as end_client, ar.name as ar_company, ap.name as ap_company, apc.full_name as ap_consultant,
       ars.code as ar_sow, aps.code as ap_sow
  from placements p
  join consultants c on c.id = p.consultant_id
  join projects pr on pr.id = p.project_id
  left join companies ec on ec.id = p.end_client_company_id
  left join companies ar on ar.id = p.ar_company_id
  left join companies ap on ap.id = p.ap_company_id
  left join consultants apc on apc.id = p.ap_consultant_id
  left join sows ars on ars.id = p.ar_sow_id
  left join sows aps on aps.id = p.ap_sow_id
"""


@router.get("/placements")
async def list_placements(db: TenantDb = Depends(tenant_db), status: str | None = None, project_id: UUID | None = None):
    rows = await db.all(_PLACEMENT_SQL + """ where (cast(:s as text) is null or p.status = :s)
                                               and (cast(:pr as uuid) is null or p.project_id = :pr)
                                             order by c.full_name, p.start_date desc""",
                        {"s": status, "pr": project_id})
    return [placement_view(r, db.ctx) for r in rows]


@router.post("/placements", status_code=201)
async def create_placement(body: PlacementIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("account_manager", "finance")
    engagement = await db.val("select engagement from consultants where id = :id", {"id": body.consultant_id})
    if engagement is None:
        raise not_found("Consultant")
    pay_model = await workflow.pay_model(db, engagement)
    if pay_model == "payroll" and (body.ap_company_id or body.ap_consultant_id):
        raise bad_request("W-2 employees are paid through payroll — leave the AP payee empty")
    if pay_model == "self":
        body.ap_consultant_id = body.ap_consultant_id or body.consultant_id
    row = await db.one(
        """insert into placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week,
                                   end_client_company_id, ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_company_id,
                                   ap_consultant_id, ap_sow_id, pay_rate, ap_terms, pay_when_paid, status)
           values (:t, :c, :p, :role, :start, :end, :hpw, :ec, :arco, :arsow, :bill, :arterms, :apco, :apcon, :apsow, :pay,
                   :apterms, :pwp, 'active') returning id""",
        {"t": db.ctx.tenant_id, "c": body.consultant_id, "p": body.project_id, "role": body.role_title,
         "start": body.start_date, "end": body.end_date, "hpw": body.hours_per_week, "ec": body.end_client_company_id,
         "arco": body.ar_company_id, "arsow": body.ar_sow_id, "bill": body.bill_rate, "arterms": body.ar_terms,
         "apco": body.ap_company_id, "apcon": body.ap_consultant_id, "apsow": body.ap_sow_id, "pay": body.pay_rate,
         "apterms": body.ap_terms, "pwp": body.pay_when_paid})
    full = await db.one(_PLACEMENT_SQL + " where p.id = :id", {"id": row["id"]})
    return placement_view(full, db.ctx)


# ----------------------------------------------------------------------------- SOW resources (WF-04)
class ResourceIn(PlacementIn):
    project_id: UUID | None = None   # taken from the SOW


@router.get("/sows/{sow_id}/resources")
async def sow_resources(sow_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Everyone working under this SOW or work order — each with their own contract, timesheets, invoices and payments."""
    rows = await db.all(_PLACEMENT_SQL + " where :id in (p.ar_sow_id, p.ap_sow_id) order by c.full_name", {"id": sow_id})
    return [placement_view(r, db.ctx) for r in rows]


@router.post("/sows/{sow_id}/resources", status_code=201)
async def add_sow_resource(sow_id: UUID, body: ResourceIn, db: TenantDb = Depends(tenant_db)):
    """Put a consultant on a SOW: one SOW can carry one or many resources (WF-04)."""
    sow = await db.one("select id, side, project_id from sows where id = :id", {"id": sow_id})
    if sow is None:
        raise not_found("SOW")
    if sow["project_id"] is None:
        raise bad_request("Link this SOW to a project first")
    if body.project_id and body.project_id != sow["project_id"]:
        raise bad_request("The resource must be on the same project as the SOW")
    body.project_id = sow["project_id"]
    if sow["side"] == "we_bill":
        body.ar_sow_id = sow_id
    else:
        body.ap_sow_id = sow_id
    return await create_placement(PlacementIn.model_validate(body.model_dump()), db)


@router.patch("/placements/{placement_id}")
async def change_placement(placement_id: UUID, body: PlacementPatch, db: TenantDb = Depends(tenant_db)):
    """Change dates, hours, status or rates. Rate changes apply to time not yet invoiced and are audited."""
    db.ctx.require("account_manager", "finance")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if ("bill_rate" in fields or "pay_rate" in fields) and not db.ctx.allows("finance"):
        raise bad_request("Only finance can change rates")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    if await db.run(f"update placements set {sets} where id = :id", {**fields, "id": placement_id}) == 0:
        raise not_found("Placement")
    return placement_view(await db.one(_PLACEMENT_SQL + " where p.id = :id", {"id": placement_id}), db.ctx)
