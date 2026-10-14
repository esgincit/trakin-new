-- =============================================================================
-- myTrakIn · 0740 · The company creator automatically becomes its owner
--
-- The API cannot insert the owner's membership row itself: company_members_write
-- is checked against existing rows, and WITH CHECK subqueries never see the row
-- being inserted. A SECURITY DEFINER trigger does it instead — it also covers
-- seeds and direct SQL inserts that set created_by.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.assign_company_owner() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
begin
  if NEW.created_by is not null then
    insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
    values (NEW.tenant_id, NEW.id, NEW.created_by, 'owner', 'active')
    on conflict do nothing;
  end if;
  return NEW;
end $$;

drop trigger if exists companies_owner on mytrakin.companies;
create trigger companies_owner
  after insert on mytrakin.companies
  for each row execute function mytrakin.assign_company_owner();
