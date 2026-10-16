-- =============================================================================
-- myTrakIn · 20261016 0700 · Link consultants to their login (U-ID shown in list/profile)
--
--   consultants.user_id was only set when the person already had a login at onboarding.
--   In the usual path (HR adds the consultant → invite → first sign-in) the sign-up trigger
--   claims the membership but never set consultants.user_id, so the consultant's U-ID
--   showed "—" for good. Keep the two in step whenever a consultant membership gets a
--   user, and backfill everyone already signed in.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.link_consultant_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if new.consultant_id is not null and new.user_id is not null then
    update consultants set user_id = new.user_id
     where id = new.consultant_id and user_id is distinct from new.user_id;
  end if;
  return new;
end
$$;

revoke all on function mytrakin.link_consultant_user() from public;

drop trigger if exists memberships_link_consultant_user on mytrakin.memberships;
create trigger memberships_link_consultant_user
  after insert or update of user_id, consultant_id on mytrakin.memberships
  for each row execute function mytrakin.link_consultant_user();

update mytrakin.consultants c set user_id = m.user_id
  from mytrakin.memberships m
 where m.consultant_id = c.id and m.user_id is not null and c.user_id is null;
