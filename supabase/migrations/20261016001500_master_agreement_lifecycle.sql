-- =============================================================================
-- myTrakIn · 20261016 1300 · MSA lifecycle between two companies
--
--   pending   sent by company A, waiting for company B
--   accepted  B accepted: the MSA is in force
--   rejected  B rejected it, with a note
--   expired   past its end date (set by expire_master_agreements, run daily)
--   Only one live MSA (pending, accepted or legacy active) may exist between two
--   companies, whichever way round it was sent. A renewal is a separate request
--   on the MSA: the other company accepts it (the end date moves) or declines
--   it with a note.
--   Cross-company writes go through security-definer functions: company B can't
--   update rows in company A's workspace.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- 1. Statuses ----------------------------------------------------------------
do $$ declare c record; begin
  for c in select conname from pg_constraint
            where conrelid = 'mytrakin.agreements'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) ilike '%status%' loop
    execute format('alter table mytrakin.agreements drop constraint %I', c.conname);
  end loop;
end $$;
alter table mytrakin.agreements add constraint agreements_status_check
  check (status in ('draft', 'out_for_signature', 'pending', 'accepted', 'rejected', 'active', 'expired', 'terminated'));

alter table mytrakin.agreements
  add column if not exists decided_on    timestamptz,
  add column if not exists decided_by    uuid,
  add column if not exists decision_note text;

-- 2. Who a row is between ------------------------------------------------------
-- The company that sent an agreement: the company the workspace represents, or
-- the company it was initiated from. Falls back to the workspace itself.
create or replace function mytrakin.agreement_sender_key(p_tenant uuid, p_initiator uuid) returns uuid
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(p_initiator, (select t.company_id from mytrakin.tenants t where t.id = p_tenant), p_tenant)
$$;

-- Which side of an agreement the signed-in user acts for: 'counterparty', 'sender' or null.
create or replace function mytrakin.my_side(p_agreement uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select case
           when a.company_id = any (mytrakin.my_company_ids()) then 'counterparty'
           when a.tenant_id = mytrakin.ctx_tenant()
             or mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = any (mytrakin.my_company_ids()) then 'sender'
         end
    from mytrakin.agreements a where a.id = p_agreement
$$;

-- 3. One live MSA between two companies ----------------------------------------
create or replace function mytrakin.enforce_one_live_master() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare me uuid; other record; key text;
begin
  if NEW.kind in ('msa', 'subcontract') and NEW.company_id is not null
     and NEW.status in ('pending', 'accepted', 'active') then
    me := mytrakin.agreement_sender_key(NEW.tenant_id, NEW.initiator_company_id);
    key := least(me, NEW.company_id)::text || ':' || greatest(me, NEW.company_id)::text;
    perform pg_advisory_xact_lock(hashtextextended(key, 0));
    select o.id, o.code into other from mytrakin.agreements o
     where o.id <> NEW.id and o.kind in ('msa', 'subcontract') and o.company_id is not null
       and o.status in ('pending', 'accepted', 'active')
       and ((o.company_id = NEW.company_id
             and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = me)
         or (o.company_id = me
             and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = NEW.company_id))
     limit 1;
    if other.id is not null then
      raise exception 'There is already an active MSA between these two companies (%). End or expire it first.', other.code
        using errcode = 'MT409';
    end if;
  end if;
  return NEW;
end $$;

drop trigger if exists agreements_one_live_master on mytrakin.agreements;
create trigger agreements_one_live_master
  before insert or update of status, kind, company_id, initiator_company_id, tenant_id on mytrakin.agreements
  for each row execute function mytrakin.enforce_one_live_master();

-- 4. Renewal requests ----------------------------------------------------------
create table if not exists mytrakin.agreement_renewals (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references mytrakin.tenants (id) on delete cascade,
  agreement_id         uuid not null references mytrakin.agreements (id) on delete cascade,
  requested_side       text not null check (requested_side in ('sender', 'counterparty')),
  requested_by         uuid,
  requested_by_name    text,
  requested_on         timestamptz not null default now(),
  proposed_expires_on  date not null,
  note                 text,
  status               text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  decided_by           uuid,
  decided_on           timestamptz,
  decision_note        text
);
create unique index if not exists agreement_renewals_one_pending
  on mytrakin.agreement_renewals (agreement_id) where status = 'pending';
create index if not exists agreement_renewals_agreement_idx on mytrakin.agreement_renewals (agreement_id, requested_on desc);

grant select, insert, update on mytrakin.agreement_renewals to mytrakin_api;
alter table mytrakin.agreement_renewals enable row level security;
drop policy if exists agreement_renewals_tenant on mytrakin.agreement_renewals;
create policy agreement_renewals_tenant on mytrakin.agreement_renewals for all to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());

-- 5. Actions by a party ----------------------------------------------------------
-- The counterparty accepts or rejects a pending MSA.
create or replace function mytrakin.respond_to_agreement(p_agreement uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; note text := nullif(trim(coalesce(p_note, '')), '');
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
  if p_decision = 'reject' and note is null then
    raise exception 'Say why you are rejecting it' using errcode = 'MT422';
  end if;
  update mytrakin.agreements
     set status = case p_decision when 'accept' then 'accepted' else 'rejected' end,
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = note
   where id = p_agreement;
end $$;

-- Either party asks to renew an MSA that is in force (or expired).
create or replace function mytrakin.request_renewal(p_agreement uuid, p_expires date, p_note text default null)
returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; side text; who text; rid uuid;
begin
  select * into a from mytrakin.agreements where id = p_agreement;
  if not found then raise exception 'Agreement not found' using errcode = 'MT404'; end if;
  side := mytrakin.my_side(p_agreement);
  if side is null then raise exception 'You are not a party to this agreement' using errcode = 'MT403'; end if;
  if a.kind not in ('msa', 'subcontract') then
    raise exception 'Only MSAs and subcontracts are renewed this way' using errcode = 'MT422';
  end if;
  if a.status not in ('accepted', 'active', 'expired') then
    raise exception 'Only an accepted MSA can be renewed' using errcode = 'MT409';
  end if;
  if p_expires is null or p_expires <= current_date then
    raise exception 'The new end date must be in the future' using errcode = 'MT422';
  end if;
  if a.status <> 'expired' and a.expires_on is not null and p_expires <= a.expires_on then
    raise exception 'The renewal must end after the current end date' using errcode = 'MT422';
  end if;
  if side = 'counterparty' then
    who := (select name from mytrakin.companies where id = a.company_id);
  else
    who := coalesce(
      (select c.name from mytrakin.companies c where c.id = mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id)),
      (select t.name from mytrakin.tenants t where t.id = a.tenant_id));
  end if;
  begin
    insert into mytrakin.agreement_renewals (tenant_id, agreement_id, requested_side, requested_by, requested_by_name,
                                             proposed_expires_on, note)
    values (a.tenant_id, p_agreement, side, mytrakin.ctx_user(), who, p_expires, nullif(trim(coalesce(p_note, '')), ''))
    returning id into rid;
  exception when unique_violation then
    raise exception 'A renewal request is already waiting for an answer' using errcode = 'MT409';
  end;
  return rid;
end $$;

-- The other party accepts a renewal (the end date moves) or declines it with a note.
create or replace function mytrakin.respond_to_renewal(p_renewal uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare r record; a record; side text; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if p_decision not in ('accept', 'decline') then
    raise exception 'The decision must be accept or decline' using errcode = 'MT422';
  end if;
  select * into r from mytrakin.agreement_renewals where id = p_renewal for update;
  if not found then raise exception 'Renewal request not found' using errcode = 'MT404'; end if;
  if r.status <> 'pending' then raise exception 'This renewal was already answered' using errcode = 'MT409'; end if;
  side := mytrakin.my_side(r.agreement_id);
  if side is null or side = r.requested_side then
    raise exception 'Only the other company can answer this renewal request' using errcode = 'MT403';
  end if;
  if p_decision = 'decline' and note is null then
    raise exception 'Say why you are declining the renewal' using errcode = 'MT422';
  end if;
  select * into a from mytrakin.agreements where id = r.agreement_id;
  if p_decision = 'accept' then
    update mytrakin.agreements
       set expires_on = r.proposed_expires_on,
           status = case when status = 'expired' then 'accepted' else status end
     where id = a.id;
  end if;
  update mytrakin.agreement_renewals
     set status = case p_decision when 'accept' then 'accepted' else 'declined' end,
         decided_by = mytrakin.ctx_user(), decided_on = now(), decision_note = note
   where id = r.id;
end $$;

-- Renewal history of an agreement, for either party.
create or replace function mytrakin.agreement_renewals_for(p_agreement uuid)
returns table (id uuid, requested_side text, requested_by_name text, requested_on timestamptz,
               proposed_expires_on date, note text, status text, decided_on timestamptz, decision_note text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select r.id, r.requested_side, r.requested_by_name, r.requested_on, r.proposed_expires_on, r.note,
         r.status, r.decided_on, r.decision_note
    from mytrakin.agreement_renewals r
   where r.agreement_id = p_agreement and mytrakin.my_side(p_agreement) is not null
   order by r.requested_on desc
$$;

-- 6. Expiry ----------------------------------------------------------------------
-- Run daily by the cron job: MSAs past their end date move to expired.
create or replace function mytrakin.expire_master_agreements() returns int
language sql security definer set search_path = mytrakin, public, extensions as $$
  with gone as (
    update mytrakin.agreements set status = 'expired'
     where kind in ('msa', 'subcontract') and status in ('accepted', 'active')
       and expires_on is not null and expires_on < current_date
    returning 1)
  select count(*)::int from gone
$$;

revoke all on function mytrakin.agreement_sender_key(uuid, uuid), mytrakin.my_side(uuid),
  mytrakin.respond_to_agreement(uuid, text, text), mytrakin.request_renewal(uuid, date, text),
  mytrakin.respond_to_renewal(uuid, text, text), mytrakin.agreement_renewals_for(uuid),
  mytrakin.expire_master_agreements() from public;
grant execute on function mytrakin.agreement_sender_key(uuid, uuid), mytrakin.my_side(uuid),
  mytrakin.respond_to_agreement(uuid, text, text), mytrakin.request_renewal(uuid, date, text),
  mytrakin.respond_to_renewal(uuid, text, text), mytrakin.agreement_renewals_for(uuid),
  mytrakin.expire_master_agreements() to mytrakin_api;
