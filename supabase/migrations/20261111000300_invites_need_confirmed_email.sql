-- Pending invitations (workspace and company) are claimed only for a confirmed e-mail address,
-- at sign-up if already confirmed, otherwise when the address is confirmed later.
create or replace function mytrakin.claim_invites(p_user uuid, p_email text) returns void
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if p_email is null then return; end if;
  update mytrakin.memberships set user_id = p_user, status = 'active'
   where user_id is null and invited_email = p_email::citext;
  update mytrakin.company_members set user_id = p_user, status = 'active'
   where user_id is null and invited_email = p_email::citext;
end $$;
revoke all on function mytrakin.claim_invites(uuid, text) from public;

create or replace function mytrakin.handle_new_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  insert into mytrakin.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'full_name', split_part(coalesce(new.email, ''), '@', 1)))
  on conflict (id) do nothing;

  if new.email_confirmed_at is not null then
    perform mytrakin.claim_invites(new.id, new.email);
  end if;

  insert into mytrakin.user_codes (user_id, code)
  values (new.id, mytrakin.next_user_code())
  on conflict (user_id) do nothing;

  return new;
end $$;

create or replace function mytrakin.on_email_confirmed() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  perform mytrakin.claim_invites(new.id, new.email);
  return new;
end $$;

drop trigger if exists on_auth_user_email_confirmed_mytrakin on auth.users;
create trigger on_auth_user_email_confirmed_mytrakin
  after update of email_confirmed_at on auth.users
  for each row when (old.email_confirmed_at is null and new.email_confirmed_at is not null)
  execute function mytrakin.on_email_confirmed();
