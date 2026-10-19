-- =============================================================================
-- myTrakIn · 20261019 0100 · Projects another company assigned to us (T011303-1047)
--
-- Company A puts Company B on one of A's projects by sending B a SOW / work order
-- for it. Projects live in their own workspace, so B never saw that project when
-- placing a consultant. Now:
--   - shared_projects(): A's live projects that have a SOW sent to one of our
--     companies (visibility = shared_sows()). Names and dates only — no money.
--   - projects.source_project_id: B's own copy of such a project, created the
--     first time B places someone on it. Timesheets, invoices and rates stay in
--     B's workspace (AR/AP only, RULE-01).
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.projects
  add column if not exists source_project_id uuid references mytrakin.projects (id) on delete set null;
create unique index if not exists projects_source_once on mytrakin.projects (tenant_id, source_project_id)
  where source_project_id is not null;

create or replace function mytrakin.shared_projects()
returns table (id uuid, code text, name text, status text, start_date date, end_date date, description text,
               client_company_id uuid, client text, assigned_by_company_id uuid, assigned_by text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select distinct on (p.id)
         p.id, p.code, p.name, p.status, p.start_date, p.end_date, p.description,
         p.client_company_id, cl.name,
         mytrakin.agreement_peer_company(s.agreement_id), mytrakin.company_public_name(mytrakin.agreement_peer_company(s.agreement_id))
    from mytrakin.shared_sows() ss
    join mytrakin.sows s on s.id = ss.id
    join mytrakin.projects p on p.id = s.project_id
    left join mytrakin.companies cl on cl.id = p.client_company_id
   where ss.status not in ('rejected', 'ended', 'terminated')
     and p.status in ('active', 'planned')
     and p.tenant_id is distinct from mytrakin.ctx_tenant()
   order by p.id
$$;

revoke all on function mytrakin.shared_projects() from public;
grant execute on function mytrakin.shared_projects() to mytrakin_api;
