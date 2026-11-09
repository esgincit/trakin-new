-- =============================================================================
-- myTrakIn · 20261107 0100 · Rate limit on the public registration form (SEC-02)
--
--   Visitors may insert registrations but never read them back (RLS), so the API
--   cannot count recent ones itself. This SECURITY DEFINER helper returns only a
--   number: registrations in the last hour from the same IP, across all
--   workspaces. The API refuses the sixth. Keyed on IP only: the e-mail is typed
--   by the visitor, so counting it would let anyone lock a real vendor out.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.recent_registrations(p_ip text) returns integer
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select count(*)::int
    from mytrakin.registrations
   where created_at > now() - interval '1 hour'
     and checks->>'submitted_ip' = p_ip
$$;

revoke all on function mytrakin.recent_registrations(text) from public;
grant execute on function mytrakin.recent_registrations(text) to mytrakin_api;
