-- =============================================================================
-- myTrakIn · 0300 · Documents, compliance, e-signatures, reminders, network, audit
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Any uploaded file. Bytes live in Supabase Storage; this row is the index.
create table documents (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  owner_type    text not null check (owner_type in ('company', 'consultant', 'project', 'agreement', 'sow', 'invoice', 'envelope', 'registration', 'policy', 'expense')),
  owner_id      uuid not null,
  name          text not null,
  storage_path  text not null,
  mime_type     text,
  size_bytes    bigint,
  sha256        text,
  uploaded_by   uuid,
  deleted_at    timestamptz,          -- soft delete, purged after 30 days
  created_at    timestamptz not null default now()
);
create index documents_owner_idx on documents (tenant_id, owner_type, owner_id) where deleted_at is null;

-- Things that expire: I-9 reverification, passports, EAD, I-94, COI, W-9 ...
create table tracked_documents (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  consultant_id    uuid references consultants (id) on delete cascade,
  company_id       uuid references companies (id) on delete cascade,
  doc_type         text not null check (doc_type in ('i9_reverification', 'passport', 'ead', 'i94', 'visa_notice', 'coi', 'w9',
                                                      'background_check', 'certification', 'drivers_license', 'agreement', 'other')),
  label            text not null,
  expires_on       date,
  status           text not null default 'valid' check (status in ('valid', 'missing', 'pending', 'expired', 'renewed')),
  blocks           text,                -- what is held while missing/expired, e.g. 'payouts'
  recipients       text[] not null default '{}',
  last_notified_on date,
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  constraint tracked_documents_owner check (consultant_id is not null or company_id is not null)
);
create index tracked_documents_expiry_idx on tracked_documents (tenant_id, expires_on) where active;

create table policies (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  name          text not null,
  version       text not null,
  effective_on  date not null,
  applies_to    text[] not null default '{w2_fulltime,w2_contract,c2c,1099}',
  file_path     text,
  active        boolean not null default true,
  created_at    timestamptz not null default now(),
  unique (tenant_id, name, version)
);

create table policy_acceptances (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants (id) on delete cascade,
  policy_id     uuid not null references policies (id) on delete cascade,
  consultant_id uuid not null references consultants (id) on delete cascade,
  accepted_at   timestamptz not null default now(),
  ip            text,
  user_agent    text,
  unique (policy_id, consultant_id)
);

-- Vendors, clients and contractors who registered through the public page.
create table registrations (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  kind        text not null check (kind in ('client', 'vendor', '1099', 'consultant')),
  name        text not null,
  contact     text not null,
  email       citext not null,
  phone       text,
  state       text,
  ein         text,
  checks      jsonb not null default '{}'::jsonb,
  documents   jsonb not null default '[]'::jsonb,
  status      text not null default 'pending' check (status in ('pending', 'needs_info', 'approved', 'rejected')),
  decided_by  uuid,
  decided_at  timestamptz,
  created_at  timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- E-signatures
-- -----------------------------------------------------------------------------
create table envelopes (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenants (id) on delete cascade,
  number            text not null,
  title             text not null,
  agreement_id      uuid references agreements (id),
  sow_id            uuid references sows (id),
  amendment_id      uuid references sow_amendments (id),
  consultant_id     uuid references consultants (id),     -- NDAs / offers / ICAs
  document_path     text,                                  -- original PDF in storage
  document_sha256   text,
  signed_path       text,                                  -- sealed PDF incl. certificate
  signed_sha256     text,
  message           text,
  sequential        boolean not null default true,
  remind_every_days int not null default 3,
  status            text not null default 'draft' check (status in ('draft', 'sent', 'completed', 'declined', 'voided', 'expired')),
  sent_by           uuid,
  sent_by_name      text,
  sent_at           timestamptz,
  expires_at        timestamptz,
  completed_at      timestamptz,
  created_at        timestamptz not null default now(),
  unique (tenant_id, number)
);
create index envelopes_tenant_status_idx on envelopes (tenant_id, status);

create table envelope_signers (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenants (id) on delete cascade,
  envelope_id      uuid not null references envelopes (id) on delete cascade,
  position         smallint not null,
  name             text not null,
  email            citext not null,
  company          text,
  company_id       uuid references companies (id),
  status           text not null default 'waiting' check (status in ('waiting', 'sent', 'viewed', 'signed', 'declined')),
  token_hash       text unique,          -- sha256 of the signing link token (the token itself is only emailed)
  otp_hash         text,
  otp_expires_at   timestamptz,
  otp_attempts     smallint not null default 0,
  verified_at      timestamptz,
  consented_at     timestamptz,
  signed_at        timestamptz,
  signature_type   text check (signature_type in ('typed', 'drawn')),
  signature_data   text,                 -- typed name or PNG data URL
  signed_ip        text,
  signed_user_agent text,
  signed_location  text,
  declined_reason  text,
  last_reminded_at timestamptz,
  unique (envelope_id, position)
);

-- Append-only evidence for the certificate of completion.
create table signature_events (
  id           bigserial primary key,
  tenant_id    uuid not null references tenants (id) on delete cascade,
  envelope_id  uuid not null references envelopes (id) on delete cascade,
  signer_id    uuid references envelope_signers (id) on delete cascade,
  event        text not null check (event in ('created', 'sent', 'email_delivered', 'viewed', 'verified', 'consented',
                                              'signed', 'declined', 'reminded', 'voided', 'completed', 'expired')),
  at           timestamptz not null default now(),
  ip           text,
  user_agent   text,
  location     text,
  detail       jsonb not null default '{}'::jsonb
);
create index signature_events_env_idx on signature_events (envelope_id, at);

-- Finds the signer behind a signing link without a tenant context.
create or replace function esign_lookup(p_token_hash text)
returns table (signer_id uuid, envelope_id uuid, tenant_id uuid)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select s.id, s.envelope_id, s.tenant_id from envelope_signers s where s.token_hash = p_token_hash
$$;
revoke all on function esign_lookup(text) from public;
grant execute on function esign_lookup(text) to mytrakin_api;

-- -----------------------------------------------------------------------------
-- Reminders and outbound notifications
-- -----------------------------------------------------------------------------
create table reminder_rules (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants (id) on delete cascade,
  key        text not null,
  area       text not null,
  description text not null,
  offsets    int[] not null default '{}',     -- days relative to the due/expiry date (negative = before)
  channels   text[] not null default '{email}',
  enabled    boolean not null default true,
  unique (tenant_id, key)
);

create table notifications (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid references tenants (id) on delete cascade,
  to_address  text not null,
  subject     text not null,
  kind        text not null,
  ref_type    text,
  ref_id      uuid,
  channel     text not null default 'email',
  status      text not null default 'sent' check (status in ('queued', 'sent', 'failed', 'skipped')),
  dedupe_key  text,
  sent_at     timestamptz not null default now()
);
create unique index notifications_dedupe_uq on notifications (tenant_id, dedupe_key) where dedupe_key is not null;
create index notifications_tenant_sent_idx on notifications (tenant_id, sent_at desc);

-- Logging an e-mail goes through these two SECURITY DEFINER functions so that signers and
-- visitors (who may send a notice but must not read the log) can use them, and so the
-- dedupe check (ON CONFLICT) doesn't need read access to other rows.
create or replace function log_notification(p_tenant uuid, p_to text, p_subject text, p_kind text, p_ref_type text,
                                            p_ref_id uuid, p_dedupe text) returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare v_id uuid;
begin
  if ctx_role() = 'anonymous' or p_tenant is distinct from ctx_tenant() then
    raise exception 'not allowed' using errcode = '42501';
  end if;
  insert into notifications (tenant_id, to_address, subject, kind, ref_type, ref_id, dedupe_key, status)
  values (p_tenant, p_to, left(p_subject, 250), p_kind, p_ref_type, p_ref_id, p_dedupe, 'queued')
  on conflict (tenant_id, dedupe_key) where dedupe_key is not null do nothing
  returning id into v_id;
  return v_id;     -- null = already sent (duplicate)
end $$;

create or replace function mark_notification(p_id uuid, p_status text) returns void
language sql security definer set search_path = mytrakin, public, extensions as $$
  update notifications set status = p_status, sent_at = now()
   where id = p_id and status = 'queued' and p_status in ('sent', 'failed', 'skipped')
$$;
revoke all on function log_notification(uuid, text, text, text, text, uuid, text), mark_notification(uuid, text) from public;
grant execute on function log_notification(uuid, text, text, text, text, uuid, text), mark_notification(uuid, text) to mytrakin_api;

create table import_jobs (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenants (id) on delete cascade,
  entity         text not null,
  filename       text,
  total_rows     int not null default 0,
  imported_rows  int not null default 0,
  updated_rows   int not null default 0,
  errors         jsonb not null default '[]'::jsonb,
  created_by     uuid,
  created_at     timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- Network (LinkedIn-style): connections, posts and direct messages across tenants
-- -----------------------------------------------------------------------------
create table connections (
  requester_id uuid not null references auth.users (id) on delete cascade,
  addressee_id uuid not null references auth.users (id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  created_at   timestamptz not null default now(),
  primary key (requester_id, addressee_id),
  constraint connections_not_self check (requester_id <> addressee_id)
);

create table posts (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid references tenants (id) on delete cascade,   -- null = visible to the whole network
  author_id   uuid not null references auth.users (id) on delete cascade,
  kind        text not null default 'update' check (kind in ('update', 'kudos', 'announcement', 'opening')),
  body        text not null check (length(body) <= 3000),
  likes       int not null default 0,
  created_at  timestamptz not null default now()
);
create index posts_tenant_created_idx on posts (tenant_id, created_at desc);

create table messages (
  id          uuid primary key default gen_random_uuid(),
  sender_id   uuid not null references auth.users (id) on delete cascade,
  recipient_id uuid not null references auth.users (id) on delete cascade,
  body        text not null check (length(body) <= 5000),
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);
create index messages_pair_idx on messages (least(sender_id, recipient_id), greatest(sender_id, recipient_id), created_at);

-- -----------------------------------------------------------------------------
-- Audit log: every insert, update and delete on business tables, append-only
-- -----------------------------------------------------------------------------
create table audit_log (
  id          bigserial primary key,
  tenant_id   uuid,
  actor_id    uuid,
  actor_role  text,
  action      text not null,
  entity      text not null,
  entity_id   text,
  changes     jsonb,
  ip          text,
  user_agent  text,
  at          timestamptz not null default now()
);
create index audit_log_tenant_at_idx on audit_log (tenant_id, at desc);
create index audit_log_entity_idx on audit_log (tenant_id, entity, entity_id);

create or replace function audit_row() returns trigger
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare
  v_old jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  v_new jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
  v_changes jsonb;
  v_key text;
begin
  if tg_op = 'UPDATE' then
    v_changes := '{}'::jsonb;
    for v_key in select jsonb_object_keys(v_new) loop
      if v_key not in ('updated_at', 'last_active_at', 'last_notified_on', 'last_reminded_at') and v_new -> v_key is distinct from v_old -> v_key then
        v_changes := v_changes || jsonb_build_object(v_key, jsonb_build_object('from', v_old -> v_key, 'to', v_new -> v_key));
      end if;
    end loop;
    if v_changes = '{}'::jsonb then return new; end if;
  elsif tg_op = 'INSERT' then
    v_changes := v_new;
  else
    v_changes := v_old;
  end if;

  -- Never copy secrets into the audit trail.
  v_changes := v_changes - 'token_hash' - 'otp_hash' - 'signature_data';

  insert into audit_log (tenant_id, actor_id, actor_role, action, entity, entity_id, changes, ip, user_agent)
  values (
    coalesce((v_new ->> 'tenant_id')::uuid, (v_old ->> 'tenant_id')::uuid, ctx_tenant()),
    ctx_user(), ctx_role(), lower(tg_op), tg_table_name,
    coalesce(v_new ->> 'id', v_old ->> 'id'),
    v_changes,
    nullif(current_setting('app.ip', true), ''), nullif(current_setting('app.user_agent', true), '')
  );
  return coalesce(new, old);
end $$;

do $$
declare t text;
begin
  foreach t in array array['tenants', 'memberships', 'companies', 'consultants', 'agreements', 'sows', 'sow_amendments',
                           'projects', 'placements', 'timesheets', 'invoices', 'payments', 'expenses', 'time_off',
                           'documents', 'tracked_documents', 'policies', 'policy_acceptances', 'registrations',
                           'envelopes', 'envelope_signers', 'reminder_rules', 'referral_agreements', 'referral_payments',
                           'payroll_lines', 'collection_notes']
  loop
    execute format('create trigger %I after insert or update or delete on mytrakin.%I for each row execute function mytrakin.audit_row()',
                   t || '_audit', t);
  end loop;
end $$;
