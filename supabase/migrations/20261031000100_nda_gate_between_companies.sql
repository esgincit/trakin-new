-- =============================================================================
-- myTrakIn - 20261031 - The NDA gate looks at the two companies, not one side
--
-- The Verify -> NDA -> MSA gate asked "does this workspace have an NDA whose
-- company_id is X?". Two live NDAs slipped through:
--
--   1. Direction. An NDA is stored in the workspace that recorded it, with the
--      other party in company_id. When the MSA is started from the other
--      company's page ("New MSA" on the company you just signed the NDA with),
--      the pair is (that company, our own company), so the check looked for an
--      NDA *with our own company* and found nothing - while the NDA between the
--      two companies was active all along.
--   2. Workspace. When the NDA lives in the counterparty's workspace, only the
--      shared (read-only) view has it. has_company_agreement() looked at the
--      caller's own agreements only.
--
-- agreement_in_force_between(a, b, kinds, on) answers the question the gate
-- actually asks: is there an agreement of these kinds in force between company
-- a and company b - whichever workspace recorded it, whichever side is the
-- supplier? Sides are compared by id first, then by normalized name, so a
-- counterparty that exists as two rows (one per workspace) still matches.
--
-- has_company_agreement() keeps its signature (other callers) but counts the
-- statuses the rest of the workflow counts ('active', 'accepted' and
-- 'out_for_signature' - a completed envelope) and sees shared agreements too.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- "Atlas Foods Corp." and "Atlas Foods Corp" are the same counterparty.
create or replace function mytrakin.company_norm(p_id uuid) returns text
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select lower(regexp_replace(c.name, '[^a-zA-Z0-9]', '', 'g')) from mytrakin.companies c where c.id = p_id
$$;

-- An agreement in force between two companies, in either direction, in any workspace.
create or replace function mytrakin.agreement_in_force_between(
  p_a uuid, p_b uuid, p_kinds text[], p_on date default current_date)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1
      from mytrakin.agreements a
     where p_a is not null and p_b is not null and p_a <> p_b
       and a.kind = any (p_kinds)
       and a.status in ('active', 'accepted', 'out_for_signature')
       and coalesce(a.effective_on, p_on) <= p_on
       and coalesce(a.expires_on, p_on) >= p_on
       and (
            -- the exact pair, whichever column each side sits in
            (a.company_id = p_a
             and mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = p_b)
         or (a.company_id = p_b
             and mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id) = p_a)
            -- the same company recorded twice (one row per workspace): match by name
         or (mytrakin.company_norm(p_a) is not null
             and mytrakin.company_norm(p_a) <> mytrakin.company_norm(p_b)
             and (
                  (mytrakin.company_norm(a.company_id) = mytrakin.company_norm(p_a)
                   and mytrakin.company_norm(mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id))
                       = mytrakin.company_norm(p_b))
               or (mytrakin.company_norm(a.company_id) = mytrakin.company_norm(p_b)
                   and mytrakin.company_norm(mytrakin.agreement_sender_key(a.tenant_id, a.initiator_company_id))
                       = mytrakin.company_norm(p_a))
             ))
       )
  )
$$;

create or replace function mytrakin.has_company_agreement(
  p_tenant uuid, p_kinds text[], p_company uuid, p_on date default current_date)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (
    select 1 from mytrakin.agreements
     where tenant_id = p_tenant and kind = any (p_kinds) and company_id = p_company
       and status in ('active', 'accepted', 'out_for_signature')
       and coalesce(effective_on, p_on) <= p_on
       and coalesce(expires_on, p_on) >= p_on
  )
  or exists (
    select 1 from mytrakin.shared_agreements() s
     where s.kind = any (p_kinds)
       and s.status in ('active', 'accepted', 'out_for_signature')
       and mytrakin.agreement_peer_company(s.id) = p_company
       and coalesce(s.effective_on, p_on) <= p_on
       and coalesce(s.expires_on, p_on) >= p_on
  )
$$;

revoke all on function mytrakin.company_norm(uuid), mytrakin.agreement_in_force_between(uuid, uuid, text[], date),
  mytrakin.has_company_agreement(uuid, text[], uuid, date) from public;
grant execute on function mytrakin.company_norm(uuid), mytrakin.agreement_in_force_between(uuid, uuid, text[], date),
  mytrakin.has_company_agreement(uuid, text[], uuid, date) to mytrakin_api;
