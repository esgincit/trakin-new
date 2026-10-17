-- =============================================================================
-- myTrakIn · 20261016 1800 · A signature is never refused
--
--   Signing DREP's MSA for Velocity failed with "There is already an active MSA
--   between these two companies (MSA-DREPSOFTWARE-001)". Two things had gone wrong:
--
--   1. Velocity could raise a counter-MSA while DREP's was out_for_signature,
--      because the trigger only counts pending/accepted/active as "live". Both
--      companies then held an unsigned MSA for the same pair.
--   2. When the last signer finished, completion set the agreement to 'accepted'.
--      That is an UPDATE, so the same trigger fired, spotted the other pending MSA
--      and raised -- aborting the whole transaction. The signature was real and had
--      been recorded in the audit trail, yet the request failed and the signer was
--      told to try again. Recording a signature may never be refused.
--
--   Now:
--     - the rule guards *creating* a second live MSA, which is where duplicates
--       actually come from. A status change on an agreement that already exists
--       never raises.
--     - when an MSA comes into force, the opposite-direction agreement for the same
--       pair that has NOT come into force is superseded rather than left dangling:
--       it is the same commercial relationship, and keeping both 'pending' leaves
--       two people waiting on each other. An MSA already in force is left alone --
--       a signature must never quietly end a live agreement.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.enforce_one_live_master() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare me uuid; other record; key text; incoming boolean;
begin
  if NEW.kind not in ('msa', 'subcontract') or NEW.company_id is null
     or NEW.status not in ('pending', 'accepted', 'active') then
    return NEW;                                    -- drafts and unsigned copies are not "live"
  end if;

  me := mytrakin.agreement_sender_key(NEW.tenant_id, NEW.initiator_company_id);
  key := least(me, NEW.company_id)::text || ':' || greatest(me, NEW.company_id)::text;
  perform pg_advisory_xact_lock(hashtextextended(key, 0));

  select o.id, o.code, o.status into other from mytrakin.agreements o
   where o.id <> NEW.id and o.kind in ('msa', 'subcontract') and o.company_id is not null
     and o.status in ('pending', 'accepted', 'active')
     and ((o.company_id = NEW.company_id
           and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = me)
       or (o.company_id = me
           and mytrakin.agreement_sender_key(o.tenant_id, o.initiator_company_id) = NEW.company_id))
   limit 1;
  if other.id is null then
    return NEW;
  end if;

  incoming := NEW.status in ('accepted', 'active');

  -- This agreement has just come into force: retire the other side's copy of the
  -- same relationship if it is still unsigned, so the pair settles on one agreement.
  if TG_OP = 'UPDATE' and incoming and other.status not in ('accepted', 'active') then
    update mytrakin.agreements
       set status = 'terminated',
           decision_note = coalesce(nullif(decision_note, ''),
                                   'Superseded by ' || NEW.code || ', which covers the same agreement between these two companies.')
     where id = other.id;
    return NEW;
  end if;

  -- Creating a second live MSA for a pair that already has one is the case worth
  -- stopping: it is a duplicate nobody asked for.
  if TG_OP = 'INSERT' then
    raise exception 'There is already an active MSA between these two companies (%). End or expire it first.', other.code
      using errcode = 'MT409';
  end if;

  -- An UPDATE that is not a coming-into-force (re-dating, re-pointing at a company,
  -- correcting a status) never blocks anything.
  return NEW;
end $$;