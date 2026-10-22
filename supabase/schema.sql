-- VendorChain MVP schema (Supabase / Postgres)
-- Source model: vendorchain-app (5)_7626.html in-memory arrays
-- Goals: multi-tenancy, immutable money, RLS, append-only audit

create extension if not exists "pgcrypto";

-- ---------- helpers ----------
create or replace function public.app_tenant_id()
returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claims', true)::json->'app_metadata'->>'tenant_id','')::uuid
$$;

-- ---------- tenants ----------
create table if not exists public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  state char(2),
  plan text not null default 'Starter' check (plan in ('Starter','Growth','Enterprise')),
  status text not null default 'Onboarding' check (status in ('Invited','Onboarding','Stalled','Live','Suspended')),
  onboarding_step int not null default 0 check (onboarding_step between 0 and 8),
  admin_name text,
  created_at timestamptz default now(),
  live_at date,
  last_active_at date
);
alter table public.tenants enable row level security;

-- ---------- profiles (app users, 1:1 with auth.users) ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  tenant_id uuid references public.tenants(id) on delete cascade,
  full_name text not null,
  role text not null check (role in ('platform','admin','finance','am','legal','vendor','consultant')),
  scope text not null default 'All',
  created_at timestamptz default now()
);
alter table public.profiles enable row level security;

-- ---------- companies (clients / vendors within a tenant) ----------
create table if not exists public.companies (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  name text not null,
  type text not null check (type in ('Client','Prime vendor','C2C vendor','ESG','1099','Referrer')),
  admin_contact text,
  state char(2),
  ein_last4 char(4),
  status text default 'Active',
  created_at timestamptz default now(),
  unique (tenant_id, name)
);
create index if not exists companies_tenant_idx on public.companies(tenant_id);
alter table public.companies enable row level security;

-- ---------- consultants ----------
create table if not exists public.consultants (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  name text not null,
  kind text not null check (kind in ('W-2','1099','C2C')),
  employer_company_id uuid references public.companies(id),
  title text,
  location text,
  auth_type text,
  auth_expires_on date,
  created_at timestamptz default now()
);
create index if not exists consultants_tenant_idx on public.consultants(tenant_id);
alter table public.consultants enable row level security;

-- ---------- placements ----------
create table if not exists public.placements (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  placement_no text not null,
  consultant_id uuid references public.consultants(id),
  person_name text not null,
  role_title text,
  project_name text,
  start_on date,
  end_on date,
  status text default 'Active',
  engagement text check (engagement in ('W-2','1099','C2C')),
  end_client_company_id uuid references public.companies(id),
  placed_by_company_id uuid references public.companies(id),
  unique (tenant_id, placement_no)
);
alter table public.placements enable row level security;

-- ---------- MSAs ----------
create table if not exists public.msas (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  msa_no text not null,
  kind text default 'MSA',
  counterparty_company_id uuid references public.companies(id),
  counterparty_name text not null,
  side text check (side in ('Supplier','Buyer')),
  effective_on date,
  expires_on date,
  terms text,
  renewal text,
  notice text,
  insurance text,
  signed_by text,
  unique (tenant_id, msa_no)
);
alter table public.msas enable row level security;

-- ---------- SOWs ----------
create table if not exists public.sows (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  sow_no text not null,
  msa_id uuid references public.msas(id),
  counterparty_name text,
  side text check (side in ('Supplier','Buyer')),
  title text,
  consultant_name text,
  start_on date,
  end_on date,
  ceiling_cents bigint not null default 0 check (ceiling_cents >= 0),
  status text default 'Active',
  from_sow_id uuid references public.sows(id),
  amend jsonb default '{}',
  unique (tenant_id, sow_no)
);
alter table public.sows enable row level security;

-- ---------- billing cycles (placement x period) ----------
create table if not exists public.billing_cycles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  cycle_no text not null,
  placement_id uuid references public.placements(id),
  person_name text,
  client_name text,
  period text,
  unique (tenant_id, cycle_no)
);
alter table public.billing_cycles enable row level security;

-- ---------- invoices = hops (AR / AP / upstream / payroll) ----------
create table if not exists public.invoices (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  cycle_id uuid references public.billing_cycles(id) on delete cascade,
  seq int not null default 0,
  kind text not null check (kind in ('upstream','ar','ap','payroll')),
  payer text not null,
  payee text not null,
  inv_no text,
  rate_cents int check (rate_cents is null or rate_cents >= 0),
  hours numeric(6,2) default 0,
  approved_hours numeric(6,2),
  issued_on date,
  due_on date,
  terms text,
  sow_id uuid references public.sows(id),
  pwp_invoice_id uuid references public.invoices(id),
  scheduled_for date,
  exception boolean default false,
  created_at timestamptz default now(),
  unique (tenant_id, inv_no)
);
create index if not exists invoices_tenant_due_idx on public.invoices(tenant_id, due_on);
create index if not exists invoices_cycle_idx on public.invoices(cycle_id);
alter table public.invoices enable row level security;

-- ---------- payments (immutable, idempotent) ----------
create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  invoice_id uuid not null references public.invoices(id) on delete restrict,
  paid_on date not null,
  amount_cents bigint not null check (amount_cents > 0),
  method text,
  reference text,
  idempotency_key text not null,
  created_by uuid references public.profiles(id),
  created_at timestamptz default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists payments_invoice_idx on public.payments(invoice_id);
alter table public.payments enable row level security;

-- ---------- timesheets ----------
create table if not exists public.timesheets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  consultant_id uuid references public.consultants(id),
  week_start_on date not null,
  status text not null default 'Not submitted'
    check (status in ('Not submitted','Submitted','Approved','Rejected')),
  submitted_at timestamptz,
  decided_by uuid references public.profiles(id),
  reject_reason text,
  placement_id uuid references public.placements(id),
  placed_by_status text not null default 'Pending'
    check (placed_by_status in ('Pending','Approved','Rejected')),
  placed_by_decided_by uuid,
  placed_by_decided_at timestamptz,
  placed_by_reject_reason text,
  end_client_status text not null default 'Pending'
    check (end_client_status in ('Pending','Approved','Rejected')),
  end_client_decided_by uuid,
  end_client_decided_at timestamptz,
  end_client_reject_reason text,
  unique (tenant_id, consultant_id, week_start_on)
);
alter table public.timesheets enable row level security;

create table if not exists public.timesheet_lines (
  id uuid primary key default gen_random_uuid(),
  timesheet_id uuid not null references public.timesheets(id) on delete cascade,
  placement_id uuid references public.placements(id),
  day_index int check (day_index between 0 and 6),
  hours numeric(4,2) check (hours >= 0 and hours <= 24),
  unique (timesheet_id, placement_id, day_index)
);
alter table public.timesheet_lines enable row level security;

-- ---------- audit log (append-only) ----------
create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  at timestamptz default now(),
  actor uuid references public.profiles(id),
  action text not null,
  entity text not null,
  change text,
  source text
);
alter table public.audit_log enable row level security;

-- Deny anon by default (no policies for anon); authenticated policies:
-- MVP: allow authenticated users to read/write rows in their own tenant.
-- Tighten per-role (finance-only amounts) in PostgREST / API layer, not RLS alone.

create policy "tenant read" on public.tenants for select to authenticated
  using (id = public.app_tenant_id());
create policy "tenant write" on public.tenants for all to authenticated
  using (id = public.app_tenant_id()) with check (id = public.app_tenant_id());

create policy "own profile" on public.profiles for select to authenticated
  using (id = auth.uid());
create policy "tenant profiles" on public.profiles for select to authenticated
  using (tenant_id = public.app_tenant_id());

create policy "companies rw" on public.companies for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "consultants rw" on public.consultants for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "placements rw" on public.placements for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "msas rw" on public.msas for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "sows rw" on public.sows for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "cycles rw" on public.billing_cycles for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "invoices rw" on public.invoices for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "payments rw" on public.payments for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());
create policy "timesheets rw" on public.timesheets for all to authenticated
  using (tenant_id = public.app_tenant_id()) with check (tenant_id = public.app_tenant_id());

create policy "audit read" on public.audit_log for select to authenticated
  using (tenant_id = public.app_tenant_id());
create policy "audit insert" on public.audit_log for insert to authenticated
  with check (tenant_id = public.app_tenant_id());
-- No update/delete policy on audit_log = append-only.
