-- =============================================================================
-- myTrakIn · P · 0100 · One company = one account (tenant). No workspaces in the product.
--   tenants.owner_membership_id  exactly one owner per company (transferable)
--   tenants.company_id           the company's own profile record (W-9, domain, members)
--   tenants.activated_*          platform activation (status onboarding → active)
--   start_company_account()      any signed-in user opens a new company (pending activation)
--   purge_abandoned_accounts()   drafts never finished within 7 days are removed
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table tenants
  add column if not exists owner_membership_id uuid references memberships (id) on delete set null,
  add column if not exists company_id          uuid references companies (id) on delete set null,
  add column if not exists activated_at        timestamptz,
  add column if not exists activated_by        uuid,
  add column if not exists decision_note       text;

-- Existing companies: the earliest active admin is the owner.
update tenants t
   set owner_membership_id = (select m.id from memberships m
                               where m.tenant_id = t.id and m.role = 'tenant_admin' and m.status = 'active'
                               order by m.created_at limit 1)
 where owner_membership_id is null;
update tenants set activated_at = created_at where status = 'active' and activated_at is null;

-- A company without an owner (older data, seeds, invites claimed later) gets its first active admin.
create or replace function claim_company_owner() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if NEW.role = 'tenant_admin' and NEW.status = 'active' and NEW.user_id is not null then
    update tenants set owner_membership_id = NEW.id where id = NEW.tenant_id and owner_membership_id is null;
  end if;
  return NEW;
end $$;
drop trigger if exists memberships_claim_owner on memberships;
create trigger memberships_claim_owner after insert or update of role, status, user_id on memberships
  for each row execute function claim_company_owner();

-- Is the caller the owner of the current company?
create or replace function is_account_owner() returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from tenants t join memberships m on m.id = t.owner_membership_id
                  where t.id = ctx_tenant() and m.user_id = ctx_user() and m.status = 'active')
$$;

-- Opens a new company for a signed-in user. Runs before any tenant context exists,
-- hence security definer. At most 3 unfinished/pending companies per person.
create or replace function start_company_account(p_user uuid) returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare t uuid; m uuid; pending int;
begin
  select count(*) into pending
    from tenants tt join memberships mm on mm.id = tt.owner_membership_id
   where mm.user_id = p_user and tt.status = 'onboarding';
  if pending >= 3 then
    raise exception 'too_many_pending' using errcode = 'P0001';
  end if;
  insert into tenants (name, status) values ('New company', 'onboarding') returning id into t;
  insert into memberships (tenant_id, user_id, role, title, status)
       values (t, p_user, 'tenant_admin', 'Owner', 'active') returning id into m;
  update tenants set owner_membership_id = m where id = t;
  perform seed_tenant_defaults(t);
  return t;
end $$;

create or replace function purge_abandoned_accounts() returns int
language sql security definer set search_path = mytrakin, public, extensions as $$
  with gone as (delete from tenants where status = 'onboarding' and company_id is null
                                      and created_at < now() - interval '7 days' returning 1)
  select count(*)::int from gone
$$;

revoke all on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() from public;
grant execute on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() to mytrakin_api;
