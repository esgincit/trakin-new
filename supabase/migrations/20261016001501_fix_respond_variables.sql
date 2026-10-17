-- =============================================================================
-- myTrakIn · 20261016 1301 · Fix: decide_renewal / respond_to_agreement variable names
--
--   In respond_to_renewal the PL/pgSQL variable `note` collided with the
--   agreement_renewals.note column, so declining a renewal with a note failed
--   with an ambiguous-column error. The variables are renamed. Behaviour is
--   unchanged otherwise.
-- =============================================================================

set search_path = mytrakin, public, extensions;

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
         decided_on = now(), decided_by = mytrakin.ctx_user(), decision_note = v_note
   where id = p_agreement;
end $$;

create or replace function mytrakin.respond_to_renewal(p_renewal uuid, p_decision text, p_note text default null)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare r record; a record; side text; v_note text := nullif(trim(coalesce(p_note, '')), '');
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

revoke all on function mytrakin.respond_to_agreement(uuid, text, text), mytrakin.respond_to_renewal(uuid, text, text) from public;
grant execute on function mytrakin.respond_to_agreement(uuid, text, text), mytrakin.respond_to_renewal(uuid, text, text) to mytrakin_api;
