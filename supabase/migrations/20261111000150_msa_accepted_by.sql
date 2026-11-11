-- =============================================================================
-- myTrakIn · 20261111 0200 · Who accepted an MSA, recorded only by the acceptance itself
--
--   membership_link_ok() (20261111000100) used agreements.decided_by as proof that the
--   other company accepted an MSA. decided_by is also written by a REJECT, and the
--   sending workspace can later move the same MSA to accepted/active on its own (paper
--   acceptance, e-signature, renewal), so a stale decided_by proved nothing.
--
--   accepted_by / accepted_on are written ONLY by respond_to_agreement on 'accept'
--   (and cleared on 'reject'); nothing else sets them. membership_link_ok() now reads
--   accepted_by. Backfill: a reject always carries a note, so decided_by is copied only
--   where the MSA is accepted/active with no decision note (the last decision was
--   certainly an accept). Accepts that carried a note stay null — a re-acceptance or
--   a same-workspace company record still links normally.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.agreements
  add column if not exists accepted_by uuid,
  add column if not exists accepted_on timestamptz;

update mytrakin.agreements
   set accepted_by = decided_by, accepted_on = decided_on
 where accepted_by is null and decided_by is not null and decision_note is null
   and kind in ('msa', 'subcontract') and status in ('accepted', 'active');

create or replace function mytrakin.respond_to_agreement(p_agreement uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; v_note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'reject') then
    raise exception 'The decision must be accept or reject' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = p_agreement for update;
  if not found then raise exception 'Agreement not found' using errcode = 'MT404'; end if;
  if a.company_id is null or not (a.company_id = any (mytrakin.my_company_ids())) then
    raise exception 'Only the company this MSA was sent to can accept or reject it' using errcode = 'MT403';
  end if;
  if a.status <> 'pending' then
    raise exception 'This MSA is no longer waiting for an answer' using errcode = 'MT409';
  end if;
  if p_decision = 'reject' and v_note is null then
    raise exception 'Say why you are rejecting it' using errcode = 'MT422';
  end if;
  update mytrakin.agreements
     set status = case p_decision when 'accept' then 'accepted' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = v_note,
         accepted_by = case p_decision when 'accept' then mytrakin.ctx_user() end,
         accepted_on = case p_decision when 'accept' then now() end
   where id = p_agreement;
end $$;

create or replace function mytrakin.membership_link_ok(p_tenant uuid, p_company uuid, p_consultant uuid)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (p_company is null
          or exists (select 1 from mytrakin.companies c where c.id = p_company and c.tenant_id = p_tenant)
          or exists (
               select 1
                 from mytrakin.agreements a
                 join mytrakin.tenants at on at.id = a.tenant_id
                 join mytrakin.tenants mine on mine.id = p_tenant
                where a.kind in ('msa', 'subcontract') and a.status in ('accepted', 'active')
                  and a.accepted_by is not null
                  and (
                    -- We sent it: someone of THAT company (its member, or staff of the
                    -- workspace that is that company) accepted it.
                    (a.tenant_id = p_tenant and a.company_id = p_company
                     and (exists (select 1 from mytrakin.company_members cm
                                   where cm.company_id = p_company and cm.user_id = a.accepted_by
                                     and cm.status = 'active')
                          or exists (select 1 from mytrakin.memberships dm
                                       join mytrakin.tenants dt on dt.id = dm.tenant_id
                                      where dt.company_id = p_company and dm.user_id = a.accepted_by
                                        and dm.status = 'active'
                                        and dm.role in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr'))))
                    -- That company's own workspace sent it to our company and we accepted.
                 or (a.tenant_id <> p_tenant and at.company_id = p_company
                     and coalesce(a.initiator_company_id, p_company) = p_company
                     and a.company_id = mine.company_id))))
     and (p_consultant is null
          or exists (select 1 from mytrakin.consultants k where k.id = p_consultant and k.tenant_id = p_tenant))
$$;

-- An acceptance only proves a relationship while the agreement is in force: leaving accepted/active
-- (expiry, termination, rejection, back to draft) clears it, so no later status change can revive it.
create or replace function mytrakin.agreements_clear_acceptance() returns trigger
language plpgsql set search_path = mytrakin, public, extensions as $$
begin
  if new.status not in ('accepted', 'active') then
    new.accepted_by := null;
    new.accepted_on := null;
  end if;
  return new;
end $$;

drop trigger if exists agreements_clear_acceptance on mytrakin.agreements;
create trigger agreements_clear_acceptance
  before update of status on mytrakin.agreements
  for each row when (new.status is distinct from old.status)
  execute function mytrakin.agreements_clear_acceptance();
