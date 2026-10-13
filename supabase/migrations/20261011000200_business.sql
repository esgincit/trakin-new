-- =============================================================================
-- myTrakIn · 0200 · Business data
--
-- Money rule: the tenant only ever stores its OWN two links of a vendor chain —
-- what it bills its customer (AR) and what it pays its vendor or contractor (AP).
-- Rates between other parties (end client -> prime, vendor -> consultant) are
-- never stored, so they can never leak.
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Clients, primes, vendors and end clients the tenant works with.
create table companies (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  name              text not null,
  kind              text not null check (kind in ('client', 'prime_vendor', 'vendor', 'end_client')),
  ein               text,
  state             text,
  address           text,
  contact_name      text,
  contact_email     citext,
  contact_phone     text,
  default_terms     text not null default 'Net 30',
  status            text not null default 'onboarding' check (status in ('onboarding', 'active', 'inactive')),
  onboarding_stage  smallint not null default 1 check (onboarding_stage between 0 and 8),
  inactive_since    date,
  inactive_reason   text,
  bank_verified     boolean not null default false,
  notes             text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (tenant_id, name)
);
create trigger companies_touch before update on companies for each row execute function touch_updated_at();
create index companies_tenant_kind_idx on companies (tenant_id, kind, status);

-- Everyone who does the work: W-2 employees, C2C consultants and 1099 contractors.
create table consultants (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenants (id) on delete cascade,
  user_id             uuid references auth.users (id) on delete set null,
  full_name           text not null,
  email               citext,
  phone               text,
  engagement          text not null check (engagement in ('w2_fulltime', 'w2_contract', 'c2c', '1099')),
  employer_company_id uuid references companies (id),            -- C2C only
  title               text,
  location            text,
  status              text not null default 'onboarding' check (status in ('onboarding', 'active', 'former')),
  start_date          date,
  end_date            date,
  leave_reason        text,
  rehire_eligible     boolean,
  work_auth_type      text,
  work_auth_expires   date,
  i9_status           text,
  everify_status      text,
  onboarding_checklist jsonb not null default '[]'::jsonb,
  skills              text[] not null default '{}',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint consultants_c2c_employer check (engagement <> 'c2c' or employer_company_id is not null)
);
create trigger consultants_touch before update on consultants for each row execute function touch_updated_at();
create index consultants_tenant_status_idx on consultants (tenant_id, status);
create index consultants_employer_idx on consultants (employer_company_id);
create index consultants_user_idx on consultants (user_id);

-- MSAs, subcontractor agreements, 1099 contractor agreements, NDAs and offer letters.
create table agreements (
  id                      uuid primary key default gen_random_uuid(),
  tenant_id               uuid not null references tenants (id) on delete cascade,
  code                    text not null,
  kind                    text not null check (kind in ('msa', 'subcontract', 'ica', 'nda', 'offer_letter')),
  company_id              uuid references companies (id),
  consultant_id           uuid references consultants (id),
  tenant_side             text not null check (tenant_side in ('supplier', 'buyer', 'employer')),
  effective_on            date,
  expires_on              date,
  payment_terms           text,
  renewal                 text,
  notice_period           text,
  insurance_required      text,
  status                  text not null default 'draft' check (status in ('draft', 'out_for_signature', 'active', 'expired', 'terminated')),
  signed_by               text,
  signed_file_path        text,
  source                  text not null default 'myTrakIn' check (source in ('myTrakIn', 'imported', 'manual')),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (tenant_id, code),
  constraint agreements_party check (company_id is not null or consultant_id is not null)
);
create trigger agreements_touch before update on agreements for each row execute function touch_updated_at();
create index agreements_expiry_idx on agreements (tenant_id, expires_on);

-- SOWs / work orders: what the tenant bills (we_bill) or pays (we_pay) under an agreement.
create table sows (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants (id) on delete cascade,
  code               text not null,
  agreement_id       uuid not null references agreements (id),
  side               text not null check (side in ('we_bill', 'we_pay')),
  company_id         uuid references companies (id),
  consultant_id      uuid references consultants (id),   -- 1099 work orders
  title              text not null,
  start_date         date not null,
  end_date           date not null,
  value_cap          numeric(14, 2),
  prior_invoiced     numeric(14, 2) not null default 0,  -- invoiced before myTrakIn (imports)
  prior_paid         numeric(14, 2) not null default 0,
  flows_from_sow_id  uuid references sows (id),          -- vendor SOW supporting a client SOW
  status             text not null default 'active' check (status in ('draft', 'out_for_signature', 'active', 'ended', 'terminated')),
  signed_file_path   text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code),
  constraint sows_dates check (end_date >= start_date)
);
create trigger sows_touch before update on sows for each row execute function touch_updated_at();
create index sows_tenant_end_idx on sows (tenant_id, end_date);

create table sow_amendments (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  sow_id        uuid not null references sows (id) on delete cascade,
  code          text not null,
  summary       text not null,
  new_end_date  date,
  value_change  numeric(14, 2),
  status        text not null default 'draft' check (status in ('draft', 'out_for_signature', 'signed', 'void')),
  created_at    timestamptz not null default now(),
  unique (tenant_id, code)
);

create table projects (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenants (id) on delete cascade,
  code               text not null,
  name               text not null,
  client_company_id  uuid references companies (id),
  prime_company_id   uuid references companies (id),
  description        text,
  start_date         date,
  end_date           date,
  manager_id         uuid references memberships (id) on delete set null,
  client_approver    text,
  status             text not null default 'active' check (status in ('planned', 'active', 'completed', 'internal')),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (tenant_id, code)
);
create trigger projects_touch before update on projects for each row execute function touch_updated_at();

-- One consultant on one project. A consultant can have any number of placements.
create table placements (
  id                     uuid primary key default gen_random_uuid(),
  tenant_id              uuid not null references tenants (id) on delete cascade,
  consultant_id          uuid not null references consultants (id),
  project_id             uuid not null references projects (id),
  role_title             text,
  start_date             date not null,
  end_date               date,
  hours_per_week         numeric(5, 2) not null default 40,
  status                 text not null default 'active' check (status in ('onboarding', 'active', 'ending', 'completed', 'ended')),
  end_client_company_id  uuid references companies (id),   -- name only; never a rate
  -- AR: who the tenant bills, and at what rate
  ar_company_id          uuid references companies (id),
  ar_sow_id              uuid references sows (id),
  bill_rate              numeric(10, 2),
  ar_terms               text,
  -- AP: who the tenant pays (vendor company or 1099 consultant). Null for W-2.
  ap_company_id          uuid references companies (id),
  ap_consultant_id       uuid references consultants (id),
  ap_sow_id              uuid references sows (id),
  pay_rate               numeric(10, 2),
  ap_terms               text,
  pay_when_paid          boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint placements_one_payee check (ap_company_id is null or ap_consultant_id is null),
  constraint placements_rates check (coalesce(bill_rate, 0) >= 0 and coalesce(pay_rate, 0) >= 0)
);
create trigger placements_touch before update on placements for each row execute function touch_updated_at();
create index placements_consultant_idx on placements (consultant_id);
create index placements_tenant_status_idx on placements (tenant_id, status);
create index placements_ap_company_idx on placements (ap_company_id);

-- -----------------------------------------------------------------------------
-- Timesheets: one per consultant per week; one entry per placement per day.
-- -----------------------------------------------------------------------------
create table timesheets (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  week_start     date not null check (extract(isodow from week_start) = 7),   -- Sunday
  status         text not null default 'draft' check (status in ('draft', 'submitted', 'approved', 'rejected')),
  note           text,
  submitted_at   timestamptz,
  decided_by     uuid,
  decided_at     timestamptz,
  reject_reason  text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (consultant_id, week_start)
);
create trigger timesheets_touch before update on timesheets for each row execute function touch_updated_at();
create index timesheets_tenant_week_idx on timesheets (tenant_id, week_start, status);

create table timesheet_entries (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  timesheet_id  uuid not null references timesheets (id) on delete cascade,
  placement_id  uuid references placements (id),     -- null = internal / non-billable
  work_date     date not null,
  hours         numeric(4, 2) not null check (hours >= 0 and hours <= 24),
  rate_type     text not null default 'regular' check (rate_type in ('regular', 'overtime', 'holiday', 'on_call')),
  unique (timesheet_id, placement_id, work_date, rate_type)
);
create index timesheet_entries_ts_idx on timesheet_entries (timesheet_id);
create index timesheet_entries_placement_idx on timesheet_entries (placement_id, work_date);

-- -----------------------------------------------------------------------------
-- Invoices (AR = we bill, AP = we are billed) and payments
-- -----------------------------------------------------------------------------
create table invoices (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  number            text not null,
  direction         text not null check (direction in ('ar', 'ap')),
  placement_id      uuid references placements (id),
  company_id        uuid references companies (id),     -- AR customer or AP vendor
  consultant_id     uuid references consultants (id),   -- AP 1099 payee
  sow_id            uuid references sows (id),
  period_start      date,
  period_end        date,
  hours             numeric(8, 2) not null default 0,
  approved_hours    numeric(8, 2),                      -- AP three-way match
  rate              numeric(10, 2) not null default 0,
  amount            numeric(14, 2) not null,
  issued_on         date not null default current_date,
  due_on            date,
  terms             text,
  pay_when_paid_of  uuid references invoices (id),      -- AP waits for this AR invoice
  status            text not null default 'sent' check (status in ('draft', 'sent', 'received', 'exception', 'scheduled', 'paid', 'void')),
  scheduled_on      date,
  po_number         text,
  memo              text,
  created_by        uuid,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (tenant_id, number),
  constraint invoices_payee check (direction = 'ar' or company_id is not null or consultant_id is not null)
);
create trigger invoices_touch before update on invoices for each row execute function touch_updated_at();
create index invoices_tenant_dir_status_idx on invoices (tenant_id, direction, status);
create index invoices_due_idx on invoices (tenant_id, due_on);
create index invoices_placement_idx on invoices (placement_id);
create index invoices_pwp_idx on invoices (pay_when_paid_of);

create table payments (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  invoice_id  uuid not null references invoices (id) on delete cascade,
  amount      numeric(14, 2) not null check (amount > 0),
  paid_on     date not null,
  method      text not null check (method in ('ACH', 'Wire', 'Check', 'Card', 'Other')),
  reference   text,
  created_by  uuid,
  created_at  timestamptz not null default now()
);
create index payments_invoice_idx on payments (invoice_id);
create index payments_tenant_date_idx on payments (tenant_id, paid_on);

create table collection_notes (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  invoice_id  uuid not null references invoices (id) on delete cascade,
  body        text not null,
  author_id   uuid,
  author_name text,
  created_at  timestamptz not null default now()
);

-- Invoice balance and live status in one place (used by every money screen).
create view invoice_balances with (security_invoker = true) as
select
  i.*,
  coalesce(p.paid, 0)                              as paid,
  i.amount - coalesce(p.paid, 0)                   as balance,
  greatest(0, current_date - i.due_on)             as days_late,
  case
    when i.status = 'void'                                      then 'void'
    when i.amount - coalesce(p.paid, 0) <= 0                     then 'paid'
    when i.status = 'exception'                                  then 'exception'
    when i.direction = 'ap' and i.pay_when_paid_of is not null
         and exists (select 1 from invoices ar
                      left join (select invoice_id, sum(amount) s from payments group by invoice_id) arp on arp.invoice_id = ar.id
                      where ar.id = i.pay_when_paid_of and ar.amount - coalesce(arp.s, 0) > 0)
                                                                 then 'held'
    when i.status = 'scheduled'                                  then 'scheduled'
    when i.due_on < current_date and coalesce(p.paid, 0) > 0     then 'overdue_part_paid'
    when i.due_on < current_date                                 then 'overdue'
    when coalesce(p.paid, 0) > 0                                 then 'part_paid'
    when i.direction = 'ap' and i.pay_when_paid_of is not null   then 'ready_to_pay'
    else 'open'
  end                                              as live_status
from invoices i
left join (select invoice_id, sum(amount) as paid from payments group by invoice_id) p on p.invoice_id = i.id;

-- SOW value used and remaining.
create view sow_burn with (security_invoker = true) as
select
  s.id as sow_id,
  s.tenant_id,
  s.value_cap,
  s.prior_invoiced + coalesce(sum(b.amount) filter (where b.status <> 'void'), 0) as invoiced,
  s.prior_paid + coalesce(sum(b.paid), 0)                                         as collected_or_paid,
  case when coalesce(s.value_cap, 0) > 0
       then round(100 * (s.prior_invoiced + coalesce(sum(b.amount) filter (where b.status <> 'void'), 0)) / s.value_cap)
  end                                                                             as burn_pct
from sows s
left join invoice_balances b on b.sow_id = s.id
group by s.id;

-- -----------------------------------------------------------------------------
-- Expenses and time off
-- -----------------------------------------------------------------------------
create table expenses (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  placement_id   uuid references placements (id),
  spent_on       date not null,
  category       text not null,
  amount         numeric(10, 2) not null check (amount > 0),
  billable       boolean not null default true,
  receipt_path   text,
  status         text not null default 'submitted' check (status in ('submitted', 'approved', 'rejected', 'reimbursed')),
  decided_by     uuid,
  created_at     timestamptz not null default now()
);

create table time_off (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  consultant_id  uuid not null references consultants (id),
  starts_on      date not null,
  ends_on        date not null,
  kind           text not null check (kind in ('pto', 'sick', 'unpaid', 'holiday')),
  note           text,
  status         text not null default 'requested' check (status in ('requested', 'approved', 'declined', 'holiday')),
  created_at     timestamptz not null default now(),
  constraint time_off_dates check (ends_on >= starts_on)
);

-- W-2 payroll register imported from the payroll provider (cost tracking only).
create table payroll_lines (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants (id) on delete cascade,
  consultant_id   uuid not null references consultants (id),
  period_start    date not null,
  period_end      date not null,
  pay_date        date not null,
  hours           numeric(6, 2),
  gross           numeric(12, 2) not null,
  employer_taxes  numeric(12, 2) not null default 0,
  benefits        numeric(12, 2) not null default 0,
  net             numeric(12, 2),
  source          text not null default 'import',
  created_at      timestamptz not null default now()
);

create table referral_agreements (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  referrer_name    text not null,
  referrer_type    text not null check (referrer_type in ('individual_1099', 'company', 'employee')),
  consultant_id    uuid not null references consultants (id),
  basis            text not null check (basis in ('hourly', 'one_time')),
  rate_per_hour    numeric(8, 2),
  hour_cap         numeric(8, 2),
  one_time_amount  numeric(10, 2),
  eligible_on      date,
  w9_on_file       boolean not null default false,
  created_at       timestamptz not null default now()
);

create table referral_payments (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references tenants (id) on delete cascade,
  agreement_id uuid not null references referral_agreements (id) on delete cascade,
  amount       numeric(10, 2) not null check (amount > 0),
  paid_on      date not null,
  reference    text
);
