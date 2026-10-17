-- =============================================================================
-- myTrakIn · 20261016 1600 · Onboard a consultant from anywhere on the platform
--
--   The consultant picker searches every registered myTrakIn user, not just the people
--   already linked to this workspace, so HR can onboard somebody who has never been in
--   this company. Two things follow from that:
--
--   1. The read side already worked: profiles and user_codes are readable by any
--      signed-in internal role, so no new policy is needed for the search itself.
--   2. The write side did not. `memberships_admin` is tenant_admin-only, so HR,
--      account managers and legal could not create the membership that gives a new
--      consultant access -- onboarding only ever worked for an owner doing it by hand.
--      grant_consultant_access() is a narrow SECURITY DEFINER entry point: it may only
--      create a *consultant* membership (or attach the consultant link to an existing
--      membership, keeping that person's role), never change anybody's role or status.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Gives one person access to this workspace as a consultant. Keeps the role they
-- already have if they are a member here in another capacity (a viewer, say) -- being
-- onboarded must not quietly demote somebody who is also staff.
create or replace function mytrakin.grant_consultant_access(
  p_tenant uuid, p_user uuid, p_consultant uuid, p_title text)
returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if p_tenant is distinct from mytrakin.ctx_tenant()
     or not mytrakin.can('hr', 'account_manager', 'legal') then
    raise exception 'not allowed' using errcode = '42501';
  end if;

  insert into mytrakin.memberships (tenant_id, user_id, role, consultant_id, title, status)
  values (p_tenant, p_user, 'consultant', p_consultant, p_title, 'active')
  on conflict (tenant_id, user_id) where user_id is not null
  do update set consultant_id = excluded.consultant_id,
                title = coalesce(memberships.title, excluded.title);
end
$$;

revoke all on function mytrakin.grant_consultant_access(uuid, uuid, uuid, text) from public;
grant execute on function mytrakin.grant_consultant_access(uuid, uuid, uuid, text) to mytrakin_api;

-- No read-side change is needed for the search: `profiles_read` and `user_codes_read`
-- already let any signed-in role read them, and the API only exposes id, U-ID, name,
-- e-mail and mobile -- the details onboarding needs and nothing more.