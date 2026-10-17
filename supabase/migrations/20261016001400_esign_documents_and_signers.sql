-- =============================================================================
-- myTrakIn · 20261017 1400 · E-signatures: several documents per envelope,
--                       signers chosen from the companies' own admins
--                       (PLAN ESG-02, AGR-07, NOT-02)
--
--   Two gaps in the "send for signature" flow:
--
--   1. An envelope carried exactly one PDF (envelopes.document_path). A packet is
--      normal in staffing — an MSA plus its SOW, or a contract and its exhibits —
--      so an envelope now holds several documents. Each one is kept in
--      `envelope_documents` (so it can be listed and removed while the envelope is
--      still a draft) and the signed copy is the documents in order, followed by
--      the certificate of completion. `document_path` / `document_sha256` stay as
--      "the merged original", so the signing link, the download and the sealing
--      code are unchanged.
--
--   2. Signers were typed in by hand, so the company that has to sign was not
--      checked against anyone, and the counterparty's admins were never told.
--      `company_signing_admins()` returns the people who may sign for a company:
--      its active owners/admins and its membership-linked vendor/client admins —
--      the same set `_can_manage_company()` accepts. It is a security definer so
--      it works for a company in another workspace (an MSA counterparty), and it
--      returns ONLY those admins' name, e-mail and role — never the rest of that
--      company, which stays behind tenant RLS (RULE-01, migration 20261016001300).
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- -----------------------------------------------------------------------------
-- Several documents per envelope
-- -----------------------------------------------------------------------------
create table if not exists mytrakin.envelope_documents (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references mytrakin.tenants (id) on delete cascade,
  envelope_id  uuid not null references mytrakin.envelopes (id) on delete cascade,
  position     smallint not null,
  name         text not null,
  storage_path text not null,
  sha256       text not null,
  size_bytes   integer,          -- null for envelopes recorded before this migration
  created_at   timestamptz not null default now()
);
create index if not exists envelope_documents_envelope_idx on mytrakin.envelope_documents (envelope_id, position);
create unique index if not exists envelope_documents_position_uq
  on mytrakin.envelope_documents (envelope_id, position);

grant select, insert, update, delete on mytrakin.envelope_documents to mytrakin_api;
alter table mytrakin.envelope_documents enable row level security;
-- Tenant isolation is the restrictive floor; the permissive policies below are what
-- actually grant access (a table with only restrictive policies allows nothing).
drop policy if exists envelope_documents_isolation on mytrakin.envelope_documents;
create policy envelope_documents_isolation on mytrakin.envelope_documents as restrictive to mytrakin_api
  using (tenant_id = mytrakin.ctx_tenant()) with check (tenant_id = mytrakin.ctx_tenant());
drop policy if exists envelope_documents_read on mytrakin.envelope_documents;
create policy envelope_documents_read on mytrakin.envelope_documents for select to mytrakin_api
  using (mytrakin.is_internal());
drop policy if exists envelope_documents_write on mytrakin.envelope_documents;
create policy envelope_documents_write on mytrakin.envelope_documents for insert to mytrakin_api
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
drop policy if exists envelope_documents_change on mytrakin.envelope_documents;
create policy envelope_documents_change on mytrakin.envelope_documents for update to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'))
  with check (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));
drop policy if exists envelope_documents_remove on mytrakin.envelope_documents;
create policy envelope_documents_remove on mytrakin.envelope_documents for delete to mytrakin_api
  using (mytrakin.can('legal', 'account_manager', 'finance', 'hr'));

drop trigger if exists envelope_documents_audit on mytrakin.envelope_documents;
create trigger envelope_documents_audit after insert or update or delete on mytrakin.envelope_documents
  for each row execute function mytrakin.audit_row();

comment on table mytrakin.envelope_documents is
  'The PDFs one envelope asks to be signed, in order. envelopes.document_path holds the merged copy.';

-- Envelopes sent before this migration have their single PDF in
-- envelopes.document_path only. Record it, so the document list is right for them
-- and they can still be added to (the rest of a packet) while they are drafts.
insert into mytrakin.envelope_documents (tenant_id, envelope_id, position, name, storage_path, sha256)
select e.tenant_id, e.id, 1, 'document.pdf', e.document_path, e.document_sha256
  from mytrakin.envelopes e
 where e.document_path is not null
   and not exists (select 1 from mytrakin.envelope_documents d where d.envelope_id = e.id);

-- Announcing the request to the other company's admins is a step of its own in the
-- envelope's timeline.
alter table mytrakin.signature_events drop constraint if exists signature_events_event_check;
alter table mytrakin.signature_events add constraint signature_events_event_check
  check (event = any (array['created', 'sent', 'email_delivered', 'viewed', 'verified', 'consented', 'signed',
                         'declined', 'reminded', 'voided', 'completed', 'expired', 'counterparty_notified']));

-- -----------------------------------------------------------------------------
-- Who may sign for a company (read-only, cross-workspace, minimal)
-- -----------------------------------------------------------------------------
create or replace function mytrakin.company_signing_admins(p_company_id uuid)
returns table (user_id uuid, name text, email text, company_role text)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  -- Company members who hold an administrative role, and the admins whose login is
  -- tied to the company. 'member' is not a signer. Ordered so the strongest role
  -- comes first: that is who the picker offers as the default.
  with admins as (
    select cm.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, cm.invited_email::text) as name,
           coalesce(p.email::text, cm.invited_email::text) as email,
           cm.company_role as company_role,
           case cm.company_role when 'super_admin' then 0 when 'owner' then 1 else 2 end as rank,
           cm.created_at
      from mytrakin.company_members cm
      left join mytrakin.profiles p on p.id = cm.user_id
     where cm.company_id = p_company_id
       and cm.status = 'active'
       and cm.company_role in ('super_admin', 'owner', 'admin')
       and (cm.user_id is not null or cm.invited_email is not null)
    union all
    select m.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, m.invited_email::text),
           coalesce(p.email::text, m.invited_email::text),
           m.role,
           3,
           m.created_at
      from mytrakin.memberships m
      left join mytrakin.profiles p on p.id = m.user_id
     where m.company_id = p_company_id
       and m.status = 'active'
       and m.role in ('vendor_admin', 'client_user')
       and (m.user_id is not null or m.invited_email is not null)
    union all
    -- The workspace that IS this company: its tenant admins (the owner above all)
    -- administer it even though a tenant_admin carries no company_id.
    select m.user_id,
           coalesce(nullif(p.full_name, ''), p.email::text, m.invited_email::text),
           coalesce(p.email::text, m.invited_email::text),
           case when m.id = t.owner_membership_id then 'owner' else m.role end,
           4,
           m.created_at
      from mytrakin.tenants t
      join mytrakin.memberships m on m.tenant_id = t.id
      left join mytrakin.profiles p on p.id = m.user_id
     where t.company_id = p_company_id
       and m.status = 'active'
       and m.role in ('tenant_admin', 'legal')
       and (m.user_id is not null or m.invited_email is not null)
  )
  select d.user_id, d.name, d.email, d.company_role
    from (
      -- One row per person (keyed on the e-mail they sign with), keeping their
      -- strongest role when they hold more than one.
      select distinct on (lower(a.email)) a.user_id, a.name, a.email, a.company_role, a.rank
        from admins a
       where a.email is not null
       order by lower(a.email), a.rank, a.name
    ) d
   order by d.rank, d.name
$$;

comment on function mytrakin.company_signing_admins(uuid) is
  'Admins of one company who may sign for it: name, e-mail and role only. Cross-workspace by design.';

revoke all on function mytrakin.company_signing_admins(uuid) from public;
grant execute on function mytrakin.company_signing_admins(uuid) to mytrakin_api;