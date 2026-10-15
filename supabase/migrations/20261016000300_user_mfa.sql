-- =============================================================================
-- myTrakIn · P · 0300 · Two-step verification is the user's choice (owner decision 2026-10-15)
--   memberships.mfa_allowed   the owner offers (true) or withholds (false) the option per user
--   user_has_mfa(uid)         did this person turn MFA on? (verified factor in Supabase Auth)
--   mfa_allowed_for(uid)      may they turn it on? (any active membership allows, or none yet)
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table memberships add column if not exists mfa_allowed boolean not null default true;

create or replace function user_has_mfa(p_user uuid) returns boolean
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare found boolean := false;
begin
  if p_user is not null and to_regclass('auth.mfa_factors') is not null then
    execute 'select exists (select 1 from auth.mfa_factors where user_id = $1 and status::text = ''verified'')'
       into found using p_user;
  end if;
  return found;
end $$;

create or replace function mfa_allowed_for(p_user uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(bool_or(mfa_allowed), true) from memberships where user_id = p_user and status = 'active'
$$;

revoke all on function user_has_mfa(uuid), mfa_allowed_for(uuid) from public;
grant execute on function user_has_mfa(uuid), mfa_allowed_for(uuid) to mytrakin_api;
