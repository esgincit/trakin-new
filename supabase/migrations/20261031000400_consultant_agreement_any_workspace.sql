-- =============================================================================
-- myTrakIn · 20261031 0400 · A consultant's offer letter follows the person
--
--   Consultants who work through several companies have one consultant row per
--   workspace. An offer letter signed in one workspace (their employer) was not
--   visible to the others, so placing them on a project — or their timesheet —
--   failed with "no active offer letter" even though one was signed and active.
--
--   This SECURITY DEFINER helper answers the one question the gate needs: does
--   this person have an agreement of these kinds in force anywhere? It matches
--   the same person by login (user_id), or by e-mail when the row has no login.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.consultant_agreement_in_force(
    p_consultant uuid, p_kinds text[], p_on date default current_date)
returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with me as (
    select c.user_id, lower(nullif(btrim(c.email), '')) as email
      from mytrakin.consultants c
     where c.id = p_consultant
  )
  select exists (
    select 1
      from mytrakin.agreements a
      join mytrakin.consultants c on c.id = a.consultant_id
      cross join me
     where a.kind = any (p_kinds)
       and a.status in ('active', 'accepted', 'out_for_signature')
       and coalesce(a.effective_on, p_on) <= p_on
       and coalesce(a.expires_on, p_on) >= p_on
       and ((me.user_id is not null and c.user_id = me.user_id)
            or (me.user_id is null and me.email is not null
                and lower(nullif(btrim(c.email), '')) = me.email))
  );
$$;
revoke all on function mytrakin.consultant_agreement_in_force(uuid, text[], date) from public;
grant execute on function mytrakin.consultant_agreement_in_force(uuid, text[], date) to mytrakin_api;
