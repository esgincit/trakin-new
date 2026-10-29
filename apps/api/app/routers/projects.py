"""Projects and placements (who works on what, and the AR/AP terms for each)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import bad_request, not_found
from ..services import numbering, workflow
from ..services.email import render, send_email
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
    # The other company may live in another workspace (row security hides it there); its name is public.
    return await db.val("select coalesce((select name from companies where id = :id), mytrakin.company_public_name(:id))",
                        {"id": company_id}) if company_id else None


@router.get("/projects/next-code")
async def next_project_code(db: TenantDb = Depends(tenant_db), client_company_id: UUID | None = None):
    """Suggested code for the New project form, from the tenant's numbering template (the field stays editable)."""
    return {"code": await numbering.preview_code(db, "project", CLIENT=await _client_name(db, client_company_id))}


@router.get("/projects/counterparties")
async def project_counterparties(db: TenantDb = Depends(tenant_db)):
    """Companies we have an MSA in force with, whichever side sent it (T011303-1049). They live in their own
    workspace, so they are not in our company list — the New project form offers them as client or prime."""
    return await db.all(
        """select * from mytrakin.project_peer_companies() order by name""")


@router.get("/projects/shared")
async def shared_projects(db: TenantDb = Depends(tenant_db)):
    """Other companies' live projects we were sent a SOW / work order for (T011303-1047). No money."""
    rows = await db.all("select * from mytrakin.shared_projects() order by name")
    linked = {r["source_project_id"]: r["id"] for r in await db.all(
        "select id, source_project_id from projects where source_project_id is not null")}
    for r in rows:
        r["local_project_id"] = linked.get(r["id"])
    return rows


@router.get("/projects")
async def list_projects(db: TenantDb = Depends(tenant_db)):
    show_money = db.ctx.allows("finance")
    rows = await db.all(
        """select pr.id, pr.code, pr.name, pr.status, pr.start_date, pr.end_date, pr.description, pr.client_approver,
                  coalesce(cl.name, mytrakin.company_public_name(pr.client_company_id)) as client,
                  coalesce(pm.name, mytrakin.company_public_name(pr.prime_company_id)) as prime,
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
    # Projects another company assigned to us by SOW (no local copy yet) — so they show in
    # Projects & placements and can be picked. Placing someone creates our own copy.
    locals_ = {r["source_project_id"] for r in await db.all(
        "select source_project_id from projects where source_project_id is not null")}
    for s in await db.all("select * from mytrakin.shared_projects() order by name"):
        if s["id"] in locals_ or any(r.get("name") == s["name"] for r in rows):
            continue
        rows.append({"id": s["id"], "code": s["code"], "name": s["name"], "status": s["status"],
                     "start_date": s["start_date"], "end_date": s["end_date"], "description": s["description"],
                     "client": s["client"], "prime": s["assigned_by"], "team_size": 0, "team": None,
                     "invoiced": 0, "assigned_from": s["assigned_by"]})
    rows.sort(key=lambda r: (r["status"] == "completed", r.get("assigned_from") is not None, r["name"]))
    return rows


async def _activation_gate(db: TenantDb, body: ProjectIn) -> None:
    """NDA → MSA → Project (WF-03): an active project needs the customer's NDA and MSA, per the workflow switches.
    The customer is the prime when the project comes through one, otherwise the client."""
    customer = body.prime_company_id or body.client_company_id
    if body.status != "active" or customer is None:
        return
    rules = await workflow.rules(db)
    name = await _client_name(db, customer) or "The counterparty"
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
        """select pr.*, coalesce(cl.name, mytrakin.company_public_name(pr.client_company_id)) as client,
                  coalesce(pm.name, mytrakin.company_public_name(pr.prime_company_id)) as prime from projects pr
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


async def _local_project(db: TenantDb, project_id: UUID) -> UUID:
    """The project in this workspace to place someone on. A project another company assigned to us gets our own
    copy the first time (prime = that company), so timesheets, invoices and rates stay on our side (RULE-01)."""
    if await db.val("select id from projects where id = :id", {"id": project_id}):
        return project_id
    local = await db.val("select id from projects where source_project_id = :id", {"id": project_id})
    if local:
        return local
    src = await db.one("select * from mytrakin.shared_projects() where id = :id", {"id": project_id})
    if src is None:
        raise not_found("Project")
    db.ctx.require("account_manager")   # adding the project here is a project write
    body = ProjectIn(name=src["name"], client_company_id=src["client_company_id"], prime_company_id=src["assigned_by_company_id"],
                     description=src["description"], start_date=src["start_date"], end_date=src["end_date"],
                     status=src["status"])
    await _activation_gate(db, body)
    code = await numbering.next_code(db, "project", CLIENT=src["client"])
    return await db.val(
        """insert into projects (tenant_id, code, name, client_company_id, prime_company_id, description, start_date, end_date,
                                 status, source_project_id)
           values (:t, :code, :name, :client, :prime, :desc, :start, :end, :status, :src) returning id""",
        {"t": db.ctx.tenant_id, "code": code, "name": body.name, "client": body.client_company_id,
         "prime": body.prime_company_id, "desc": body.description, "start": body.start_date, "end": body.end_date,
         "status": body.status, "src": project_id})


# ----------------------------------------------------------------------------- placements
def placement_view(row: dict, ctx) -> dict:
    """Only ever show the caller the rates they're allowed to see."""
    if not ctx.sees_bill_rate:
        row["bill_rate"] = None
    if not ctx.sees_pay_rate:
        row["pay_rate"] = None
    if ctx.role == "vendor_admin" and row.get("ap_company_id") is not None and row.get("ap_company_id") != ctx.company_id:
        row["pay_rate"] = None
    if ctx.role == "client_user":
        row["pay_rate"] = None
    return row


_PLACEMENT_SQL = """
select p.*, c.full_name as consultant, c.engagement, pr.name as project, pr.code as project_code,
       coalesce(ec.name, mytrakin.company_public_name(p.end_client_company_id)) as end_client,
       coalesce(ar.name, mytrakin.company_public_name(p.ar_company_id)) as ar_company,
       coalesce(ap.name, mytrakin.company_public_name(p.ap_company_id)) as ap_company, apc.full_name as ap_consultant,
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
    # WF-05: resource contract → acceptance → timesheet. A W-2 consultant needs an active
    # offer letter; a C2C/E2E consultant needs an active MSA/subcontract with the AR customer.
    if pay_model == "payroll":
        has_contract = await workflow.has_active_agreement(db, kinds=("offer_letter",), consultant_id=body.consultant_id)
        if not has_contract:
            raise workflow.blocked("contract_required", f"This consultant has no active offer letter — assign one before creating the placement (or turn off 'Require resource contract' in Settings → Workflow)")
    else:
        ar_co = body.ar_company_id
        if ar_co is None:
            ar_co = await db.val("select prime_company_id from projects where id = :id and source_project_id is not null",
                                 {"id": body.project_id})
        if ar_co is not None:
            has_contract = await workflow.has_active_agreement(db, kinds=workflow.MASTER_KINDS, company_id=ar_co)
            if not has_contract:
                raise workflow.blocked("contract_required", f"No active MSA with the AR customer — sign one before creating the placement (or turn off 'Require resource contract' in Settings → Workflow)")
    body.project_id = await _local_project(db, body.project_id)
    # The end client is the original company that initiated the project chain
    # (the project's client), whichever workspace places the consultant. It is
    # never the placing company's own company.
    proj = await db.one("select client_company_id from projects where id = :id", {"id": body.project_id})
    body.end_client_company_id = proj["client_company_id"]
    if body.ar_company_id is None:   # on a project another company assigned to us, we bill that company
        body.ar_company_id = await db.val("select prime_company_id from projects where id = :id and source_project_id is not null",
                                          {"id": body.project_id})
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
    consultant = await db.one("select email, full_name from consultants where id = :id", {"id": body.consultant_id})
    if consultant and consultant.get("email"):
        tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
        when = f"{full['start_date']}" + (f" to {full['end_date']}" if full.get("end_date") else "")
        await send_email(db, to=consultant["email"], subject=f"New project assignment: {full['project']}",
                         kind="placement", tenant_id=db.ctx.tenant_id, ref_type="placement", ref_id=row["id"],
                         html_body=render(f"You've been assigned to {full['project']}",
                                          [f"Role: {full['role_title'] or 'Consultant'}. Period: {when}. "
                                           f"{full['hours_per_week']} hours per week."
                                           + (f" Work order: {full['ar_sow'] or full['ap_sow']}." if (full.get("ar_sow") or full.get("ap_sow")) else ""),
                                           f"{tenant} manages timesheets, documents and payment status in myTrakIn."],
                                          button=("Open myTimesheet", f"{get_settings().web_origin.rstrip('/')}/my/timesheet")))
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
