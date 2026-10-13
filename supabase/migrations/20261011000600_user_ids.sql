-- =============================================================================
-- myTrakIn · 0600 · System-wide user IDs
--
-- Every person in the system gets one stable, human-readable ID (U000001,
-- U000002, …) in `mytrakin.user_codes`, no matter how many workspaces they
-- belong to. The code is assigned by the signup trigger, so application code
-- can always join on it. Backfills everyone who signed up before this change.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- The counter. A sequence (not max+1) keeps codes unique under concurrency.
create sequence if not exists mytrakin.user_id_seq;

create or replace function mytrakin.next_user_code() returns text
language sql set search_path = mytrakin, public, extensions as $$
  select 'U' || lpad(nextval('mytrakin.user_id_seq')::text, 6, '0')
$$;
grant execute on function mytrakin.next_user_code() to mytrakin_api;

-- One row per login. The code is the system-wide ID; user_id ties it to Auth.
create table if not exists mytrakin.user_codes (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  code       text not null unique,
  created_at timestamptz not null default now()
);
comment on table mytrakin.user_codes is 'System-wide user IDs (U000001, …): one row per auth.users row.';
comment on column mytrakin.user_codes.code is 'Stable public ID shown in the app and API. Never reused, may have gaps.';

-- Indexing: the primary key covers user_id lookups and the unique constraint
-- covers code lookups (both are btree). Newest-first listing for admin screens.
create index if not exists user_codes_created_idx on mytrakin.user_codes (created_at desc);

grant select, insert, update, delete on mytrakin.user_codes to mytrakin_api;
grant usage, select on mytrakin.user_id_seq to mytrakin_api;

alter table mytrakin.user_codes enable row level security;
drop policy if exists user_codes_read on mytrakin.user_codes;
create policy user_codes_read on mytrakin.user_codes for select to mytrakin_api
  using (ctx_role() not in ('anonymous', 'public', 'signer'));

-- Backfill: everyone who signed up before this migration, oldest first.
insert into mytrakin.user_codes (user_id, code)
select u.id, mytrakin.next_user_code()
  from auth.users u
 where not exists (select 1 from mytrakin.user_codes c where c.user_id = u.id)
 order by u.created_at, u.id
on conflict (user_id) do nothing;

-- Assign a code to every future signup, alongside the profile + invite claim.
create or replace function mytrakin.handle_new_user() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  insert into mytrakin.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'full_name', split_part(coalesce(new.email, ''), '@', 1)))
  on conflict (id) do nothing;

  if new.email is not null then
    update mytrakin.memberships
       set user_id = new.id, status = 'active'
     where user_id is null and invited_email = new.email::citext;
  end if;

  insert into mytrakin.user_codes (user_id, code)
  values (new.id, mytrakin.next_user_code())
  on conflict (user_id) do nothing;

  return new;
end $$;
