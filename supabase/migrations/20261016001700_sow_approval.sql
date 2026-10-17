-- =============================================================================
-- myTrakIn · 20261016 1700 · SOWs run both ways under one MSA, with approval
--
--   An MSA between two companies is one agreement whichever workspace recorded it,
--   so work under it must be possible from either side. Two things were in the way:
--
--   1. Creating a SOW under the other workspace's MSA was impossible. POST /sows read
--      the agreement with a plain SELECT, and the restrictive tenant_isolation policy
--      hides another workspace's agreement rows, so the counterparty got a 404 for an
--      MSA they could plainly see in GET /agreements.
--   2. Even with the row visible, a SOW copied `company_id` from the agreement. Seen
--      from the counterparty's side that is *their own* company, so the SOW would have
--      pointed back at the wrong party. agreement_peer_company() resolves the other
--      company from wherever you are standing.
--
--   Approval, mirroring the MSA lifecycle (01500):
--     draft     created, not sent -- invisible to the other company
--     pending   sent to the other company for approval
--     active    approved by them, or recorded as already signed
--     rejected  turned down, with the reason kept on the row
--
--   A sent SOW is shared read-only and without money: the other company sees the
--   reference, title, term and status, never the value ceiling, invoiced or paid
--   amounts. Only the workspace that created it can see those, and only it can amend.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- 1. Statuses and the decision --------------------------------------------------
do $$ declare c record; begin
  for c in select conname from pg_constraint
            where conrelid = 'mytrakin.sows'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) ilike '%status%' loop
    execute format('alter table mytrakin.sows drop constraint %I', c.conname);
  end loop;
end $$;
alter table mytrakin.sows add constraint sows_status_check
  check (status in ('draft', 'pending', 'out_for_signature', 'active', 'rejected', 'ended', 'terminated'));

alter table mytrakin.sows
  add column if not exists decided_on    timestamptz,
  add column if not exists decided_by    uuid,
  add column if not exists decision_note text,
  add column if not exists sent_on       timestamptz;

-- 2. The other company, from where you stand -------------------------------------
-- I am the sender  -> the peer is the agreement's company_id.
-- I am the counterparty -> the peer is whoever sent it.
-- Null when the other side is not a company (1099 work orders have no company peer).
create or replace function mytrakin.agreement_peer_company(p_agreement uuid) returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select case when a.id is null then null
              when a.tenant_id = mytrakin.ctx_tenant()
                or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = any (mytrakin.my_company_ids())
                then a.company_id
              else mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)
         end
    from mytrakin.agreements a
   where a.id = p_agreement
     and exists (select 1 from mytrakin.companies c
                  where c.id = case when a.tenant_id = mytrakin.ctx_tenant()
                                      or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)
                                           = any (mytrakin.my_company_ids())
                                     then a.company_id
                                     else mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) end)
$$;

-- The SOWs another workspace created under an agreement we are a party to, and has
-- actually sent. A draft is the other company's work in progress, not ours to see.
create or replace function mytrakin.shared_sows()
returns table (
  id uuid, code text, title text, side text, status text, start_date date, end_date date,
  agreement_code text, agreement_id uuid, counterparty text, sent_by text,
  sent_on timestamptz, decided_on timestamptz, decision_note text, shared boolean)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with mine as (select mytrakin.my_company_ids() as ids)
  select s.id, s.code, s.title,
         case when s.side = 'we_bill' then 'we_pay' else 'we_bill' end,
         s.status, s.start_date, s.end_date,
         a.code, a.id,
         -- the other company on the MSA, from where the reader stands
         case when a.company_id = any (m.ids) then sc.name else rc.name end,
         coalesce(s_t.name, sc.name),
         s.sent_on, s.decided_on, s.decision_note, true
    from mytrakin.sows s
    join mytrakin.agreements a on a.id = s.agreement_id
    cross join mine m
    join mytrakin.tenants t on t.id = a.tenant_id
    join mytrakin.tenants s_t on s_t.id = s.tenant_id
    left join mytrakin.companies sc on sc.id = coalesce(a.initiator_company_id, t.company_id)
    left join mytrakin.companies rc on rc.id = a.company_id
   where s.tenant_id is distinct from mytrakin.ctx_tenant()
     and s.status <> 'draft'
     and exists (select 1 from mytrakin.companies mine_c
                  where mine_c.id = any (m.ids)
                    and (mine_c.id = a.company_id or mine_c.id = coalesce(a.initiator_company_id, t.company_id)))
$$;

-- 3. Send for approval, and the other company's answer --------------------------
create or replace function mytrakin.submit_sow_for_approval(p_sow uuid) returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; peer uuid;
begin
  select * into s from mytrakin.sows where id = p_sow for update;
  if not found then raise exception 'SOW not found' using errcode = 'MT404'; end if;
  if s.tenant_id is distinct from mytrakin.ctx_tenant() then
    raise exception 'This SOW belongs to another workspace' using errcode = 'MT403';
  end if;
  if s.status <> 'draft' then
    raise exception 'This SOW has already been sent' using errcode = 'MT409';
  end if;
  peer := mytrakin.agreement_peer_company(s.agreement_id);
  if peer is null then
    raise exception 'There is no other company on this agreement to send it to' using errcode = 'MT422';
  end if;
  update mytrakin.sows set status = 'pending', sent_on = now() where id = p_sow;
end $$;

-- The company it was sent to approves it (it comes into force) or turns it down.
-- The sender of the SOW cannot answer their own SOW: it is the *other* party to the
-- agreement who does that, and only if their company is one of ours.
create or replace function mytrakin.respond_to_sow(p_sow uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('approve', 'reject') then
    raise exception 'The decision must be approve or reject' using errcode = 'MT422';
  end if;
  select * into s from mytrakin.sows where id = p_sow for update;
  if not found then raise exception 'SOW not found' using errcode = 'MT404'; end if;
  if s.tenant_id = mytrakin.ctx_tenant() then
    raise exception 'This is your own SOW — only the company it was sent to can answer it' using errcode = 'MT403';
  end if;
  if mytrakin.my_side(s.agreement_id) is null then
    raise exception 'You are not a party to this agreement' using errcode = 'MT403';
  end if;
  if s.status <> 'pending' then
    raise exception 'This SOW is not waiting for an answer' using errcode = 'MT409';
  end if;
  if p_decision = 'reject' and note is null then
    raise exception 'Say why you are turning it down' using errcode = 'MT422';
  end if;
  update mytrakin.sows
     set status = case p_decision when 'approve' then 'active' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = note
   where id = p_sow;
end $$;

revoke all on function mytrakin.agreement_peer_company(uuid), mytrakin.shared_sows(),
  mytrakin.submit_sow_for_approval(uuid), mytrakin.respond_to_sow(uuid, text, text) from public;
grant execute on function mytrakin.agreement_peer_company(uuid), mytrakin.shared_sows(),
  mytrakin.submit_sow_for_approval(uuid), mytrakin.respond_to_sow(uuid, text, text) to mytrakin_api;