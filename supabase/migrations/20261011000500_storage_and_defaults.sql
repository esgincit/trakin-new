-- =============================================================================
-- myTrakIn · 0500 · Storage buckets and per-tenant defaults
-- =============================================================================

set search_path = mytrakin, public, extensions;

-- Storage buckets (only when running on Supabase).
--   documents : private. Files are read through short-lived signed URLs the API issues.
--   esign     : private. Original and sealed signed PDFs.
--   avatars   : public read. Profile photos and cover images under unguessable paths.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values
      ('documents', 'documents', false, 26214400, null),
      ('esign', 'esign', false, 26214400, array['application/pdf']),
      ('avatars', 'avatars', true, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
    on conflict (id) do nothing;
  end if;
end $$;

-- Default reminder rules for a new tenant.
create or replace function seed_tenant_defaults(p_tenant uuid) returns void
language sql set search_path = mytrakin, public, extensions as $$
  insert into mytrakin.reminder_rules (tenant_id, key, area, description, offsets, channels, enabled) values
    (p_tenant, 'timesheet_due',      'Timesheets',  'Remind consultants who have not submitted: Friday 3 PM, Monday 9 AM; escalate Tuesday', '{0,3,4}', '{email,sms}', true),
    (p_tenant, 'ar_courtesy',        'Client invoices', 'Courtesy notice before the due date', '{-7}', '{email}', true),
    (p_tenant, 'ar_overdue',         'Client invoices', 'Overdue reminders; day 15 copies the account manager, day 30 escalates to finance', '{1,7,15,30}', '{email}', true),
    (p_tenant, 'ap_status',          'Vendor & 1099 invoices', 'Tell payees when an invoice is matched, held, scheduled and paid', '{}', '{email}', true),
    (p_tenant, 'esign_reminder',     'E-signatures', 'Remind the current signer every 3 days; expire after 30 days', '{3}', '{email}', true),
    (p_tenant, 'contract_expiry',    'Contracts', 'MSA and SOW expiry alerts', '{-90,-60,-30}', '{email}', true),
    (p_tenant, 'work_auth_expiry',   'Compliance', 'Work authorization and I-9 reverification', '{-120,-90,-60,-30,-14,-7,0}', '{email}', true),
    (p_tenant, 'document_expiry',    'Compliance', 'Passports, EAD, I-94, insurance certificates, certifications', '{-120,-90,-60,-30,-14,-7,0}', '{email}', true),
    (p_tenant, 'policy_acceptance',  'Policies', 'Ask people to accept new policy versions within 14 days', '{0,7,14}', '{email}', true)
  on conflict (tenant_id, key) do nothing;
$$;
grant execute on function seed_tenant_defaults(uuid) to mytrakin_api;
