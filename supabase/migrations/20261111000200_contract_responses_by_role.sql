-- =============================================================================
-- myTrakIn · 20261111 0200 · Accepting / rejecting MSAs, renewals and SOWs is role based
--   Only admin, legal and account-manager roles can answer or request them on a
--   company's behalf (the API route checks the same). Bodies are otherwise the
--   latest definitions (20261016001501, 20261016001500, 20261016001700).
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.respond_to_agreement(p_agreement uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; v_note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if not mytrakin.can('legal', 'account_manager') then
    raise exception 'Only an admin, legal or account manager can answer an MSA' using errcode = 'MT403';
  end if;
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
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = v_note
   where id = p_agreement;
end $$;

create or replace function mytrakin.respond_to_renewal(p_renewal uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare r record; a record; side text; v_note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if not mytrakin.can('legal', 'account_manager') then
    raise exception 'Only an admin, legal or account manager can answer a renewal' using errcode = 'MT403';
  end if;
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
  if p_decision = 'decline' and v_note is null then
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
         decided_by = mytrakin.ctx_user(), decided_on = now(), decision_note = v_note
   where id = r.id;
end $$;

create or replace function mytrakin.request_renewal(p_agreement uuid, p_expires date, p_note text default null)
returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare a record; side text; who text; rid uuid;
begin
  if not mytrakin.can('legal', 'account_manager') then
    raise exception 'Only an admin, legal or account manager can request a renewal' using errcode = 'MT403';
  end if;
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

create or replace function mytrakin.respond_to_sow(p_sow uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare s record; note text := nullif(trim(coalesce(p_note, '')), '');
begin
  if not mytrakin.can('legal', 'account_manager') then
    raise exception 'Only an admin, legal or account manager can answer a SOW' using errcode = 'MT403';
  end if;
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
