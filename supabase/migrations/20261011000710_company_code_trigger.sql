-- =============================================================================
-- myTrakIn · 0710 · Business IDs for every insert
--
-- 0700 backfilled existing companies, but seed.sql (and any direct SQL insert)
-- omits business_code — and the column is NOT NULL. This trigger assigns the
-- next C-0001-style code whenever an insert leaves it blank, so seeds, imports
-- and future code paths can never fail on it. Explicit codes pass through.
-- =============================================================================

set search_path = mytrakin, public, extensions;

create or replace function mytrakin.assign_business_code() returns trigger
language plpgsql set search_path = mytrakin, public, extensions as $$
begin
  if NEW.business_code is null or NEW.business_code = '' then
    NEW.business_code := 'C-' || lpad(mytrakin.next_number(NEW.tenant_id, 'company')::text, 4, '0');
  end if;
  return NEW;
end $$;

drop trigger if exists companies_business_code on mytrakin.companies;
create trigger companies_business_code
  before insert on mytrakin.companies
  for each row execute function mytrakin.assign_business_code();
