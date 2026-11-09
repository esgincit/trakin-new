-- =============================================================================
-- myTrakIn · 20261031 0300 · One global number for project codes
--
--   Project codes are globally unique since 20261028 0100, but every workspace
--   still keeps its own `project` counter (starting at 1). A workspace whose
--   counter is behind codes other workspaces used generates a code that already
--   exists (PRJ-01, PRJ-02 …), and the insert is refused — "That project code
--   is already in use". The numbering service also only saw its own tenant's
--   codes under RLS, so it could not skip them.
--
--   One shared sequence now hands out project numbers; the taken-check below is
--   SECURITY DEFINER so it sees every workspace's codes.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create sequence if not exists mytrakin.project_code_seq;

-- Start after every PRJ-<n> already in use, so existing codes stay untouched.
select setval(
  'mytrakin.project_code_seq',
  greatest(coalesce((select max(substring(code from '^PRJ-([0-9]+)$')::int)
                       from mytrakin.projects where code ~ '^PRJ-[0-9]+$'), 0), 1),
  true);

create or replace function mytrakin.next_project_seq() returns bigint
language sql volatile security definer set search_path = mytrakin, public, extensions as $$
  select nextval('mytrakin.project_code_seq');
$$;
revoke all on function mytrakin.next_project_seq() from public;
grant execute on function mytrakin.next_project_seq() to mytrakin_api;

-- What the "new project" form shows before saving (does not consume a number).
create or replace function mytrakin.peek_project_seq() returns bigint
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select last_value + case when is_called then 1 else 0 end from mytrakin.project_code_seq;
$$;
revoke all on function mytrakin.peek_project_seq() from public;
grant execute on function mytrakin.peek_project_seq() to mytrakin_api;

-- Project codes are globally unique, so the check must see every workspace's rows.
create or replace function mytrakin.project_code_taken(p_code text) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from mytrakin.projects where code = p_code);
$$;
revoke all on function mytrakin.project_code_taken(text) from public;
grant execute on function mytrakin.project_code_taken(text) to mytrakin_api;
