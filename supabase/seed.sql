-- =============================================================================
-- myTrakIn demo data (staging / training environments only — never production)
--
-- Before running, change the e-mail addresses below to people on your team.
-- Each address becomes an invitation; the person gets access the first time
-- they sign in with that e-mail (one-time code, SSO or magic link).
-- Dates are relative to today so the demo always looks current.
-- =============================================================================

do $$
declare
  -- ▼▼ change these ▼▼
  v_admin_email      text := 'admin@example.com';
  v_finance_email    text := 'finance@example.com';
  v_consultant_email text := 'ravi.kumar@example.com';
  v_vendor_email     text := 's.rao@brightpath.example';
  -- ▲▲ change these ▲▲

  t uuid; atlas uuid; northwind uuid; meridian uuid; bright uuid; orion uuid;
  ravi uuid; anita uuid; marcus uuid; grace uuid; daniel uuid; priya uuid;
  msa_nw uuid; msa_af uuid; msa_bp uuid; msa_od uuid; ica_dc uuid;
  wo388 uuid; wo402 uuid; sow87 uuid; sow91 uuid; sow93 uuid; sow95 uuid; bp14 uuid; bp19 uuid; od3 uuid; dc1 uuid;
  p_s4 uuid; p_grc uuid; p_portal uuid; p_internal uuid;
  pl_ravi_s4 uuid; pl_ravi_grc uuid; pl_anita uuid; pl_marcus uuid; pl_grace uuid; pl_daniel uuid;
  ar1 uuid; ar2 uuid; ar3 uuid; ar4 uuid; ar5 uuid; ar6 uuid;
  wk date := (current_date - extract(dow from current_date)::int);   -- this week's Sunday
  e1 uuid;
begin
  insert into mytrakin.tenants (name, legal_name, ein, state, plan, status, onboarding_step, live_on)
  values ('Executive Software Guild Inc.', 'Executive Software Guild Inc.', 'XX-XXX7733', 'TX', 'enterprise', 'active', 8, current_date - 180)
  returning id into t;
  perform mytrakin.seed_tenant_defaults(t);

  insert into mytrakin.memberships (tenant_id, invited_email, role, title) values
    (t, v_admin_email, 'tenant_admin', 'Tenant admin'),
    (t, v_finance_email, 'finance', 'Finance manager');

  -- Companies ------------------------------------------------------------------
  insert into mytrakin.companies (tenant_id, name, kind, ein, state, contact_name, contact_email, default_terms, status, onboarding_stage)
  values (t, 'Atlas Foods Corp.', 'client', 'XX-XXX9046', 'TX', 'J. Brooks', 'j.brooks@atlasfoods.example', 'Net 30', 'active', 8) returning id into atlas;
  insert into mytrakin.companies (tenant_id, name, kind, ein, state, contact_name, contact_email, default_terms, status, onboarding_stage)
  values (t, 'Northwind Consulting', 'prime_vendor', 'XX-XXX1190', 'NY', 'D. Shah', 'd.shah@northwind.example', 'Net 45', 'active', 8) returning id into northwind;
  insert into mytrakin.companies (tenant_id, name, kind, state, status, onboarding_stage)
  values (t, 'Meridian Pharma Inc.', 'end_client', 'NJ', 'active', 8) returning id into meridian;
  insert into mytrakin.companies (tenant_id, name, kind, ein, state, contact_name, contact_email, default_terms, status, onboarding_stage, bank_verified)
  values (t, 'BrightPath Tech LLC', 'vendor', 'XX-XXX5502', 'NJ', 'S. Rao', v_vendor_email, 'Pay-when-paid', 'active', 8, true) returning id into bright;
  insert into mytrakin.companies (tenant_id, name, kind, ein, state, contact_name, contact_email, default_terms, status, onboarding_stage, bank_verified)
  values (t, 'Orion Data Partners', 'vendor', 'XX-XXX3317', 'IL', 'M. Lee', 'm.lee@oriondata.example', 'Net 30', 'active', 8, true) returning id into orion;

  insert into mytrakin.memberships (tenant_id, invited_email, role, company_id, title)
  values (t, v_vendor_email, 'vendor_admin', bright, 'Account Director');

  -- Consultants --------------------------------------------------------------------
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, employer_company_id, title, location, status, start_date, work_auth_type, i9_status, skills)
  values (t, 'Ravi Kumar', v_consultant_email, 'c2c', bright, 'SAP GRC Consultant', 'Edison, NJ', 'active', current_date - 250, 'Managed by employer', 'Employer''s responsibility', '{SAP GRC,S/4 Security}') returning id into ravi;
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, title, location, status, start_date, work_auth_type, work_auth_expires, i9_status, everify_status, skills)
  values (t, 'Anita Desai', 'anita.desai@example.com', 'w2_contract', 'SAP ABAP Developer', 'Princeton, NJ', 'active', current_date - 900, 'H-1B (extension filed)', current_date + 41, 'Reverify before expiry', 'Employment authorized', '{ABAP,RAP,CDS}') returning id into anita;
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, employer_company_id, title, location, status, start_date, work_auth_type, skills)
  values (t, 'Marcus Hill', 'marcus.hill@example.com', 'c2c', orion, 'BTP Integration Lead', 'Chicago, IL', 'active', current_date - 130, 'Managed by employer', '{SAP BTP,Integration Suite}') returning id into marcus;
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, title, location, status, start_date, work_auth_type, i9_status, everify_status, skills)
  values (t, 'Grace Okafor', 'grace.okafor@example.com', 'w2_contract', 'Scrum Master', 'Dallas, TX', 'active', current_date - 27, 'US citizen', 'Complete', 'Employment authorized', '{Scrum,SAFe}') returning id into grace;
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, title, location, status, start_date, work_auth_type, skills)
  values (t, 'Daniel Cho', 'daniel.cho@example.com', '1099', 'QA Automation Engineer', 'Austin, TX', 'active', current_date - 55, 'Not applicable (independent contractor)', '{Selenium,Tosca}') returning id into daniel;
  insert into mytrakin.consultants (tenant_id, full_name, email, engagement, title, location, status, start_date, work_auth_type, work_auth_expires, i9_status, everify_status, skills)
  values (t, 'Priya Nair', 'priya.nair@example.com', 'w2_fulltime', 'SAP BTP Developer', 'McKinney, TX', 'active', current_date - 130, 'STEM OPT (EAD)', current_date + 56, 'Reverify before expiry', 'Employment authorized', '{SAP BTP,CAP,Fiori}') returning id into priya;

  insert into mytrakin.memberships (tenant_id, invited_email, role, consultant_id, title)
  values (t, v_consultant_email, 'consultant', ravi, 'SAP GRC Consultant');

  -- Agreements and SOWs --------------------------------------------------------------
  -- Resource contracts (WF-05): W-2 consultants work under a signed offer letter.
  insert into mytrakin.agreements (tenant_id, code, kind, consultant_id, tenant_side, effective_on, status, signed_by) values
    (t, 'OFFER-ESG-AD', 'offer_letter', anita, 'employer', current_date - 905, 'active', 'Madhavi Gonnala'),
    (t, 'OFFER-ESG-GO', 'offer_letter', grace, 'employer', current_date - 30, 'active', 'Madhavi Gonnala'),
    (t, 'OFFER-ESG-PN', 'offer_letter', priya, 'employer', current_date - 135, 'active', 'Madhavi Gonnala');
  -- Verify → NDA → MSA (WF-02): every seeded client and vendor has its NDA on file.
  insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, status, signed_by) values
    (t, 'NDA-NW-ESG', 'nda', northwind, 'supplier', current_date - 960, 'active', 'Madhavi Gonnala'),
    (t, 'NDA-AF-ESG', 'nda', atlas, 'supplier', current_date - 570, 'active', 'Madhavi Gonnala'),
    (t, 'NDA-MP-ESG', 'nda', meridian, 'supplier', current_date - 570, 'active', 'Madhavi Gonnala'),
    (t, 'NDA-ESG-BP', 'nda', bright, 'buyer', current_date - 380, 'active', 'Madhavi Gonnala'),
    (t, 'NDA-ESG-OD', 'nda', orion, 'buyer', current_date - 150, 'active', 'Madhavi Gonnala');
  insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, expires_on, payment_terms, renewal, notice_period, insurance_required, status, signed_by)
  values (t, 'MSA-NW-ESG', 'msa', northwind, 'supplier', current_date - 950, current_date + 630, 'Net 45', 'Manual', '30 days', 'GL $1M, E&O $2M', 'active', 'Madhavi Gonnala') returning id into msa_nw;
  insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, expires_on, payment_terms, renewal, notice_period, insurance_required, status, signed_by)
  values (t, 'MSA-AF-ESG', 'msa', atlas, 'supplier', current_date - 560, current_date + 171, 'Net 30', 'Auto, 1 year', '60 days', 'GL $2M, E&O $2M, Cyber $1M', 'active', 'Madhavi Gonnala') returning id into msa_af;
  insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, expires_on, payment_terms, status, signed_by)
  values (t, 'MSA-ESG-BP', 'subcontract', bright, 'buyer', current_date - 375, current_date + 354, 'Pay-when-paid / Net 30', 'active', 'Madhavi Gonnala') returning id into msa_bp;
  insert into mytrakin.agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, expires_on, payment_terms, status, signed_by)
  values (t, 'MSA-ESG-OD', 'subcontract', orion, 'buyer', current_date - 149, current_date + 81, 'Net 30', 'active', 'Madhavi Gonnala') returning id into msa_od;
  insert into mytrakin.agreements (tenant_id, code, kind, consultant_id, tenant_side, effective_on, expires_on, payment_terms, status, signed_by)
  values (t, 'ICA-ESG-DC', 'ica', daniel, 'buyer', current_date - 62, current_date + 303, 'Net 15', 'active', 'Madhavi Gonnala') returning id into ica_dc;

  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, prior_invoiced, prior_paid)
  values (t, 'WO-NW-0388', msa_nw, 'we_bill', northwind, 'R. Kumar – SAP GRC, S/4 Security Rollout', current_date - 250, current_date + 110, 190000, 93480, 93480) returning id into wo388;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, prior_invoiced, prior_paid)
  values (t, 'WO-NW-0402', msa_nw, 'we_bill', northwind, 'A. Desai – SAP ABAP, S/4 Security Rollout', current_date - 180, current_date + 81, 117600, 36288, 36288) returning id into wo402;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, prior_invoiced, prior_paid)
  values (t, 'SOW-AF-0087', msa_af, 'we_bill', atlas, 'Supplier Portal – BTP Integration', current_date - 130, current_date + 47, 86400, 40320, 40320) returning id into sow87;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap)
  values (t, 'SOW-AF-0091', msa_af, 'we_bill', atlas, 'GRC Audit Support', current_date - 69, current_date + 68, 63000) returning id into sow91;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap)
  values (t, 'SOW-AF-0093', msa_af, 'we_bill', atlas, 'Supplier Portal – Scrum Master', current_date - 27, current_date + 152, 88000) returning id into sow93;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap)
  values (t, 'SOW-AF-0095', msa_af, 'we_bill', atlas, 'Supplier Portal – QA Automation', current_date - 55, current_date + 124, 60000) returning id into sow95;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, prior_invoiced, prior_paid, flows_from_sow_id)
  values (t, 'SOW-ESG-BP-014', msa_bp, 'we_pay', bright, 'R. Kumar – pass-through', current_date - 250, current_date + 110, 160000, 78720, 78720, wo388) returning id into bp14;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, flows_from_sow_id)
  values (t, 'SOW-ESG-BP-019', msa_bp, 'we_pay', bright, 'R. Kumar – Atlas GRC', current_date - 69, current_date + 68, 49200, sow91) returning id into bp19;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, company_id, title, start_date, end_date, value_cap, prior_invoiced, prior_paid, flows_from_sow_id)
  values (t, 'SOW-ESG-OD-003', msa_od, 'we_pay', orion, 'M. Hill – Atlas BTP Integration', current_date - 130, current_date + 47, 71280, 33264, 33264, sow87) returning id into od3;
  insert into mytrakin.sows (tenant_id, code, agreement_id, side, consultant_id, title, start_date, end_date, value_cap, flows_from_sow_id)
  values (t, 'ICA-ESG-DC-001', ica_dc, 'we_pay', daniel, 'Contractor work order – D. Cho', current_date - 55, current_date + 124, 45760, sow95) returning id into dc1;

  insert into mytrakin.sow_amendments (tenant_id, sow_id, code, summary, new_end_date, value_change, status)
  values (t, sow87, 'AMD-AF-0087-1', 'Extend to three months later and add $36,000', current_date + 138, 36000, 'out_for_signature');

  -- Projects and placements (AR and AP rates only) --------------------------------------------
  insert into mytrakin.projects (tenant_id, code, name, client_company_id, prime_company_id, description, start_date, end_date, client_approver, status)
  values (t, 'PRJ-01', 'S/4 Security Rollout', meridian, northwind, 'SAP S/4HANA role redesign, SoD clean-up and audit readiness.', current_date - 250, current_date + 110, 'L. Carter (Meridian)', 'active') returning id into p_s4;
  insert into mytrakin.projects (tenant_id, code, name, client_company_id, description, start_date, end_date, client_approver, status)
  values (t, 'PRJ-02', 'GRC Audit Support', atlas, 'Access reviews and SoD remediation for the SOX cycle.', current_date - 69, current_date + 68, 'J. Brooks (Atlas)', 'active') returning id into p_grc;
  insert into mytrakin.projects (tenant_id, code, name, client_company_id, description, start_date, end_date, client_approver, status)
  values (t, 'PRJ-03', 'Supplier Portal', atlas, 'Supplier self-service portal on SAP BTP.', current_date - 130, current_date + 152, 'J. Brooks (Atlas)', 'active') returning id into p_portal;
  insert into mytrakin.projects (tenant_id, code, name, description, start_date, end_date, status)
  values (t, 'PRJ-04', 'Accelerator (internal)', 'Reusable BTP and GRC accelerators built between engagements.', current_date - 40, current_date + 80, 'internal') returning id into p_internal;

  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, end_client_company_id, ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_company_id, ap_sow_id, pay_rate, ap_terms, pay_when_paid)
  values (t, ravi, p_s4, 'SAP GRC Consultant', current_date - 250, current_date + 110, 24, 'active', meridian, northwind, wo388, 95, 'Net 45', bright, bp14, 80, 'Pay-when-paid', true) returning id into pl_ravi_s4;
  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_company_id, ap_sow_id, pay_rate, ap_terms)
  values (t, ravi, p_grc, 'SAP Security Advisor', current_date - 69, current_date + 68, 16, 'active', atlas, sow91, 105, 'Net 30', bright, bp19, 82, 'Net 30') returning id into pl_ravi_grc;
  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, end_client_company_id, ar_company_id, ar_sow_id, bill_rate, ar_terms)
  values (t, anita, p_s4, 'SAP ABAP Developer', current_date - 180, current_date + 81, 40, 'active', meridian, northwind, wo402, 84, 'Net 45') returning id into pl_anita;
  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_company_id, ap_sow_id, pay_rate, ap_terms)
  values (t, marcus, p_portal, 'BTP Integration Lead', current_date - 130, current_date + 47, 40, 'ending', atlas, sow87, 120, 'Net 30', orion, od3, 99, 'Net 30') returning id into pl_marcus;
  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, ar_company_id, ar_sow_id, bill_rate, ar_terms)
  values (t, grace, p_portal, 'Scrum Master', current_date - 27, current_date + 152, 40, 'active', atlas, sow93, 88, 'Net 30') returning id into pl_grace;
  insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week, status, ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_consultant_id, ap_sow_id, pay_rate, ap_terms)
  values (t, daniel, p_portal, 'QA Automation Engineer', current_date - 55, current_date + 124, 40, 'active', atlas, sow95, 85, 'Net 30', daniel, dc1, 65, 'Net 15') returning id into pl_daniel;

  -- Last week's timesheets (approved) and this week's (mixed) -------------------------------------
  insert into mytrakin.timesheets (tenant_id, consultant_id, week_start, status, submitted_at, decided_at)
  select t, c, wk - 7, 'approved', now() - interval '6 days', now() - interval '5 days'
    from unnest(array[ravi, anita, marcus, grace, daniel, priya]) as c;
  insert into mytrakin.timesheets (tenant_id, consultant_id, week_start, status, submitted_at)
  values (t, anita, wk, 'submitted', now() - interval '3 hours'),
         (t, daniel, wk, 'submitted', now() - interval '2 hours'),
         (t, marcus, wk, 'approved', now() - interval '1 day'),
         (t, ravi, wk, 'draft', null);

  insert into mytrakin.timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
  select t, ts.id, pl.id, ts.week_start + d, h
    from mytrakin.timesheets ts
    join lateral (values (ravi, pl_ravi_s4, 5.0), (ravi, pl_ravi_grc, 3.0), (anita, pl_anita, 8.0), (marcus, pl_marcus, 8.0),
                         (grace, pl_grace, 8.0), (daniel, pl_daniel, 8.0), (priya, null::uuid, 8.0)) v(cid, plid, h) on v.cid = ts.consultant_id
    left join mytrakin.placements pl on pl.id = v.plid
    cross join generate_series(1, 5) d
   where ts.tenant_id = t and not (ts.week_start = wk and ts.consultant_id = anita and d = 5);
  -- Anita worked a Saturday this week (shows the weekend check)
  insert into mytrakin.timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
  select t, id, pl_anita, wk + 5, 9 from mytrakin.timesheets where consultant_id = anita and week_start = wk;
  insert into mytrakin.timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
  select t, id, pl_anita, wk + 6, 4 from mytrakin.timesheets where consultant_id = anita and week_start = wk;

  -- Invoices and payments (AR and AP) -------------------------------------------------------------
  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'ESG-AR-0371', 'ar', pl_anita, northwind, wo402, current_date - 102, current_date - 72, 184, 84, 15456, current_date - 72, current_date - 27, 'Net 45', 'sent') returning id into ar1;
  insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference) values (t, ar1, 8000, current_date - 11, 'Check', 'NW-CHK-20419');
  insert into mytrakin.collection_notes (tenant_id, invoice_id, body, author_name) values
    (t, ar1, 'Reminder 1 sent to Northwind AP.', 'K. Reddy'),
    (t, ar1, 'Partial check for $8,000 received. Balance promised in their next run.', 'K. Reddy');

  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'ESG-AR-0412', 'ar', pl_ravi_s4, northwind, wo388, current_date - 40, current_date - 10, 168, 95, 15960, current_date - 10, current_date + 35, 'Net 45', 'sent') returning id into ar2;
  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, approved_hours, rate, amount, issued_on, due_on, terms, status, pay_when_paid_of)
  values (t, 'BP-INV-1187', 'ap', pl_ravi_s4, bright, bp14, current_date - 40, current_date - 10, 168, 168, 80, 13440, current_date - 8, null, 'Pay-when-paid', 'received', ar2);

  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'ESG-AR-0414', 'ar', pl_ravi_grc, atlas, sow91, current_date - 40, current_date - 10, 64, 105, 6720, current_date - 10, current_date + 20, 'Net 30', 'sent') returning id into ar3;
  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, approved_hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'BP-INV-1188', 'ap', pl_ravi_grc, bright, bp19, current_date - 40, current_date - 10, 72, 64, 82, 5904, current_date - 8, current_date + 22, 'Net 30', 'exception');

  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'ESG-AR-0413', 'ar', pl_marcus, atlas, sow87, current_date - 40, current_date - 10, 168, 120, 20160, current_date - 10, current_date + 20, 'Net 30', 'sent') returning id into ar4;
  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, approved_hours, rate, amount, issued_on, due_on, terms, status, scheduled_on)
  values (t, 'OD-0342', 'ap', pl_marcus, orion, od3, current_date - 40, current_date - 10, 168, 168, 99, 16632, current_date - 9, current_date + 21, 'Net 30', 'scheduled', current_date + 20);

  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'ESG-AR-0393', 'ar', pl_daniel, atlas, sow95, current_date - 71, current_date - 41, 88, 85, 7480, current_date - 41, current_date - 11, 'Net 30', 'sent') returning id into ar5;
  insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference) values (t, ar5, 7480, current_date - 12, 'Wire', 'AF-88215');
  insert into mytrakin.invoices (tenant_id, number, direction, placement_id, consultant_id, sow_id, period_start, period_end, hours, approved_hours, rate, amount, issued_on, due_on, terms, status)
  values (t, 'DC-0007', 'ap', pl_daniel, daniel, dc1, current_date - 71, current_date - 41, 88, 88, 65, 5720, current_date - 40, current_date - 25, 'Net 15', 'sent') returning id into ar6;
  insert into mytrakin.payments (tenant_id, invoice_id, amount, paid_on, method, reference) values (t, ar6, 5720, current_date - 26, 'ACH', 'ESG-ACH-1004');

  -- Compliance -----------------------------------------------------------------------------
  insert into mytrakin.tracked_documents (tenant_id, consultant_id, company_id, doc_type, label, expires_on, status, blocks, recipients) values
    (t, anita, null, 'i9_reverification', 'Form I-9 reverification (H-1B)', current_date + 41, 'valid', null, '{anita.desai@example.com,hr@example.com}'),
    (t, anita, null, 'passport', 'Passport', current_date + 126, 'valid', null, '{anita.desai@example.com}'),
    (t, priya, null, 'ead', 'EAD card (STEM OPT)', current_date + 56, 'valid', null, '{priya.nair@example.com,hr@example.com}'),
    (t, daniel, null, 'coi', 'Professional liability insurance', current_date + 50, 'valid', null, '{daniel.cho@example.com}'),
    (t, null, bright, 'coi', 'Certificate of insurance (GL, E&O)', current_date + 21, 'valid', 'payouts', '{s.rao@brightpath.example}'),
    (t, null, orion, 'w9', 'W-9', null, 'missing', '1099 reporting', '{m.lee@oriondata.example}');

  insert into mytrakin.policies (tenant_id, name, version, effective_on, applies_to) values
    (t, 'Code of conduct', 'v2', current_date - 283, '{w2_fulltime,w2_contract,c2c,1099}'),
    (t, 'Information security & acceptable use', 'v3', current_date - 10, '{w2_fulltime,w2_contract,c2c,1099}'),
    (t, 'Anti-harassment policy', 'v1', current_date - 650, '{w2_fulltime,w2_contract}'),
    (t, 'Timesheet & expense policy', 'v2', current_date - 283, '{w2_fulltime,w2_contract,c2c,1099}');

  -- One completed e-signature with its evidence trail ---------------------------------------------
  insert into mytrakin.envelopes (tenant_id, number, title, sow_id, status, sent_by_name, sent_at, completed_at, document_sha256, signed_sha256)
  values (t, 'ENV-1001', 'SOW-AF-0093 — Supplier Portal, Scrum Master', sow93, 'completed', 'N. Patel', now() - interval '33 days', now() - interval '30 days',
          encode(sha256('demo-original'::bytea), 'hex'), encode(sha256('demo-signed'::bytea), 'hex'))
  returning id into e1;
  insert into mytrakin.envelope_signers (tenant_id, envelope_id, position, name, email, company, company_id, status, verified_at, consented_at, signed_at, signature_type, signature_data, signed_ip, signed_user_agent, signed_location)
  values (t, e1, 1, 'J. Brooks', 'j.brooks@atlasfoods.example', 'Atlas Foods Corp.', atlas, 'signed', now() - interval '32 days', now() - interval '32 days', now() - interval '31 days', 'typed', 'J. Brooks', '198.51.100.24', 'Chrome on Windows', 'Dallas, TX'),
         (t, e1, 2, 'Madhavi Gonnala', 'madhavi@esg.example.com', 'Executive Software Guild Inc.', null, 'signed', now() - interval '30 days', now() - interval '30 days', now() - interval '30 days', 'typed', 'Madhavi Gonnala', '203.0.113.10', 'Safari on macOS', 'McKinney, TX');
  insert into mytrakin.signature_events (tenant_id, envelope_id, signer_id, event, at, ip, user_agent, location)
  select t, e1, s.id, ev.e, s.signed_at - ev.lag, s.signed_ip, s.signed_user_agent, s.signed_location
    from mytrakin.envelope_signers s
   cross join (values ('sent', interval '2 days'), ('viewed', interval '1 day'), ('verified', interval '1 day'), ('consented', interval '1 day'), ('signed', interval '0')) ev(e, lag)
   where s.envelope_id = e1;
  -- W-2 payroll results, a referral fee, an expense and a time-off request ------------------------
  insert into mytrakin.payroll_lines (tenant_id, consultant_id, period_start, period_end, pay_date, hours, gross, employer_taxes, benefits, net)
  select t, c.id, ps, ps + 14, ps + 19, h, g, round(g * 0.0765, 2), b, round(g * 0.74, 2)
    from (values (anita, 80, 5200, 310), (grace, 80, 4400, 290), (priya, 80, 5600, 420)) v(cid, h, g, b)
    join mytrakin.consultants c on c.id = v.cid
   cross join (values (date_trunc('month', current_date - 30)::date), (date_trunc('month', current_date - 30)::date + 15)) d(ps);

  insert into mytrakin.referral_agreements (tenant_id, referrer_name, referrer_type, consultant_id, basis, rate_per_hour, hour_cap, eligible_on, w9_on_file)
  values (t, 'Kiran Patel', 'individual_1099', marcus, 'hourly', 2.00, 1040, current_date - 130, true);
  insert into mytrakin.referral_agreements (tenant_id, referrer_name, referrer_type, consultant_id, basis, one_time_amount, eligible_on)
  values (t, 'Grace Okafor', 'employee', grace, 'one_time', 1000, current_date + 63);
  insert into mytrakin.referral_payments (tenant_id, agreement_id, amount, paid_on, reference)
  select t, id, 120, current_date - 35, 'ACH-REF-0091' from mytrakin.referral_agreements where referrer_name = 'Kiran Patel' and tenant_id = t;

  insert into mytrakin.expenses (tenant_id, consultant_id, placement_id, spent_on, category, amount, billable)
  values (t, ravi, pl_ravi_grc, current_date - 6, 'Travel – client site visit', 412.60, true);
  insert into mytrakin.time_off (tenant_id, consultant_id, starts_on, ends_on, kind, note)
  values (t, anita, current_date + 20, current_date + 22, 'pto', 'Family event');

  update mytrakin.counters set value = 1001 where tenant_id = t and key = 'envelope';
  insert into mytrakin.counters (tenant_id, key, value) values (t, 'envelope', 1001), (t, 'ar_invoice', 420) on conflict (tenant_id, key) do nothing;

  -- WF-04: each SOW / work order belongs to the project of the placements that use it.
  update mytrakin.sows s set project_id = sub.project_id
    from (select distinct on (sow_id) sow_id, project_id
            from (select ar_sow_id as sow_id, project_id, start_date from mytrakin.placements where ar_sow_id is not null
                  union all
                  select ap_sow_id, project_id, start_date from mytrakin.placements where ap_sow_id is not null) x
           order by sow_id, start_date) sub
   where sub.sow_id = s.id and s.project_id is null;
end $$;
