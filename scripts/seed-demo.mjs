import 'dotenv/config';
import pg from 'pg';

const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();
const q = (t, p) => c.query(t, p);
const C = (d) => Math.round(d * 100); // dollars -> cents

// 1. ESG tenant
let esg = (await q(`select id from tenants where name='Executive Software Guild Inc.' limit 1`)).rows[0];
if (!esg) esg = (await q(`insert into tenants(name,state,plan,status,onboarding_step,admin_name,live_at) values('Executive Software Guild Inc.','TX','Enterprise','Live',8,'Praveen Gottimukkula','2026-04-20') returning id`)).rows[0];
const T = esg.id;
console.log('tenant ESG:', T);

// move demo users onto ESG so they can see the data
await q(`update app_users set tenant_id=$1 where role<>'platform'`, [T]);

// 2. companies
const companies = [
  ['Meridian Pharma Inc.', 'Client', 'L. Carter', 'NJ'],
  ['Northwind Consulting', 'Prime vendor', 'D. Shah', 'NY'],
  ['Executive Software Guild Inc.', 'ESG', 'P. Gottimukkula', 'TX'],
  ['BrightPath Tech LLC', 'C2C vendor', 'S. Rao', 'NJ'],
  ['Orion Data Partners', 'C2C vendor', 'M. Lee', 'IL'],
  ['Atlas Foods Corp.', 'Client', 'J. Brooks', 'TX'],
];
const coId = {};
for (const [name, type, admin, st] of companies) {
  const r = await q(`insert into companies(tenant_id,name,type,admin_contact,state) values($1,$2,$3,$4,$5)
    on conflict(tenant_id,name) do update set type=excluded.type returning id`, [T, name, type, admin, st]);
  coId[name] = r.rows[0].id;
}

// 3. consultants
const consultants = [
  ['Ravi Kumar', 'C2C', 'BrightPath Tech LLC', 'SAP GRC Consultant'],
  ['Anita Desai', 'W-2', null, 'SAP ABAP Developer'],
  ['Marcus Hill', 'C2C', 'Orion Data Partners', 'BTP Integration Lead'],
  ['Grace Okafor', 'W-2', null, 'Scrum Master'],
  ['Daniel Cho', '1099', null, 'QA Automation Engineer'],
];
const conId = {};
for (const [name, kind, emp, title] of consultants) {
  const r = await q(`insert into consultants(tenant_id,name,kind,employer_company_id,title) values($1,$2,$3,$4,$5)
    on conflict do nothing returning id`, [T, name, kind, emp ? coId[emp] : null, title]);
  conId[name] = r.rows[0]?.id || (await q(`select id from consultants where tenant_id=$1 and name=$2`, [T, name])).rows[0].id;
}

// 4. MSAs
const msas = [
  ['MSA-NW-ESG', 'Northwind Consulting', 'Supplier', '2024-03-01', '2028-06-30', 'Net 45'],
  ['MSA-AF-ESG', 'Atlas Foods Corp.', 'Supplier', '2025-04-01', '2027-03-31', 'Net 30'],
  ['MSA-ESG-BP', 'BrightPath Tech LLC', 'Buyer', '2025-10-01', '2027-09-30', 'Pay-when-paid / Net 30'],
  ['MSA-ESG-OD', 'Orion Data Partners', 'Buyer', '2026-05-15', '2026-12-31', 'Net 30'],
];
const msaId = {};
for (const [no, cp, side, eff, exp, terms] of msas) {
  const r = await q(`insert into msas(tenant_id,msa_no,counterparty_company_id,counterparty_name,side,effective_on,expires_on,terms,renewal,notice,signed_by)
    values($1,$2,$3,$4,$5,$6,$7,$8,'Manual','30 days','M. Gonnala')
    on conflict(tenant_id,msa_no) do nothing returning id`, [T, no, coId[cp], cp, side, eff, exp, terms]);
  msaId[no] = r.rows[0]?.id || (await q(`select id from msas where tenant_id=$1 and msa_no=$2`, [T, no])).rows[0].id;
}

// 5. SOWs
const sows = [
  ['WO-NW-0388', 'MSA-NW-ESG', 'Northwind Consulting', 'Supplier', 'R. Kumar SAP GRC', 'Ravi Kumar', '2026-02-02', '2027-01-29', 190000],
  ['SOW-AF-0091', 'MSA-AF-ESG', 'Atlas Foods Corp.', 'Supplier', 'GRC Audit Support', 'Ravi Kumar', '2026-08-03', '2026-12-18', 63000],
  ['SOW-AF-0087', 'MSA-AF-ESG', 'Atlas Foods Corp.', 'Supplier', 'Supplier Portal BTP', 'Marcus Hill', '2026-06-01', '2026-11-27', 86400],
  ['SOW-ESG-BP-014', 'MSA-ESG-BP', 'BrightPath Tech LLC', 'Buyer', 'R. Kumar pass-through', 'Ravi Kumar', '2026-02-02', '2027-01-29', 160000],
  ['SOW-ESG-BP-019', 'MSA-ESG-BP', 'BrightPath Tech LLC', 'Buyer', 'R. Kumar Atlas GRC', 'Ravi Kumar', '2026-08-03', '2026-12-18', 49200],
  ['SOW-ESG-OD-003', 'MSA-ESG-OD', 'Orion Data Partners', 'Buyer', 'M. Hill Atlas BTP', 'Marcus Hill', '2026-06-01', '2026-11-27', 71280],
];
const sowId = {};
for (const [no, msa, cp, side, title, who, st, en, ceil] of sows) {
  const r = await q(`insert into sows(tenant_id,sow_no,msa_id,counterparty_name,side,title,consultant_name,start_on,end_on,ceiling_cents)
    values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) on conflict(tenant_id,sow_no) do nothing returning id`,
    [T, no, msaId[msa], cp, side, title, who, st, en, C(ceil)]);
  sowId[no] = r.rows[0]?.id || (await q(`select id from sows where tenant_id=$1 and sow_no=$2`, [T, no])).rows[0].id;
}

// 6. placements
const placements = [
  ['PL-1042', 'Ravi Kumar', 'SAP GRC Consultant', 'S/4 Security Rollout', '2026-02-02', '2027-01-29', 'Active', 'C2C'],
  ['PL-1057', 'Ravi Kumar', 'SAP Security Advisor', 'GRC Audit Support', '2026-08-03', '2026-12-18', 'Active', 'C2C'],
  ['PL-1071', 'Marcus Hill', 'BTP Integration Lead', 'Supplier Portal', '2026-06-01', '2026-11-27', 'Active', 'C2C'],
  ['PL-1063', 'Anita Desai', 'SAP ABAP Developer', 'S/4 Security Rollout', '2026-04-13', '2026-12-31', 'Active', 'W-2'],
];
const plId = {};
for (const [no, who, role, proj, st, en, status, eng] of placements) {
  const cid = conId[who];
  const r = await q(`insert into placements(tenant_id,placement_no,consultant_id,person_name,role_title,project_name,start_on,end_on,status,engagement)
    values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) on conflict(tenant_id,placement_no) do nothing returning id`,
    [T, no, cid, who, role, proj, st, en, status, eng]);
  plId[no] = r.rows[0]?.id || (await q(`select id from placements where tenant_id=$1 and placement_no=$2`, [T, no])).rows[0].id;
}

// 7. cycles + invoices + payments (from prototype)
// [cycle_no, placement_no, person, client, period, hops...]
// hop: [kind, payer, payee, inv_no, rate$, hrs, apprHrs, issued, due, terms, sow_no, payments[[date,amt$,method,ref]], extra]
const ESG = 'Executive Software Guild Inc.', BP = 'BrightPath Tech LLC', OD = 'Orion Data Partners',
  NW = 'Northwind Consulting', MP = 'Meridian Pharma Inc.', AF = 'Atlas Foods Corp.';
const cycles = [
  ['CY-1042-AUG', 'PL-1042', 'Ravi Kumar', MP, 'Aug 2026', [
    ['ar', NW, ESG, 'ESG-AR-2026-0389', 95, 176, null, '2026-08-31', '2026-10-15', 'Net 45', 'WO-NW-0388', [['2026-10-01', 16720, 'ACH', 'NW-PMT-55120']]],
    ['ap', ESG, BP, 'BP-INV-1161', 80, 176, null, '2026-09-02', null, 'Pay-when-paid', 'SOW-ESG-BP-014', [['2026-10-02', 14080, 'ACH', 'ESG-ACH-1009']], { pwp: 'ESG-AR-2026-0389' }],
  ]],
  ['CY-1042-SEP', 'PL-1042', 'Ravi Kumar', MP, 'Sep 2026', [
    ['ar', NW, ESG, 'ESG-AR-2026-0412', 95, 168, null, '2026-10-01', '2026-11-15', 'Net 45', 'WO-NW-0388', []],
    ['ap', ESG, BP, 'BP-INV-1187', 80, 168, null, '2026-10-03', null, 'Pay-when-paid', 'SOW-ESG-BP-014', [], { pwp: 'ESG-AR-2026-0412' }],
  ]],
  ['CY-1057-AUG', 'PL-1057', 'Ravi Kumar', AF, 'Aug 2026', [
    ['ar', AF, ESG, 'ESG-AR-2026-0391', 105, 168, null, '2026-08-31', '2026-09-30', 'Net 30', 'SOW-AF-0091', [['2026-09-29', 17640, 'Wire', 'AF-88213']]],
    ['ap', ESG, BP, 'BP-INV-1160', 82, 168, null, '2026-09-02', '2026-10-02', 'Net 30', 'SOW-ESG-BP-019', [['2026-10-02', 13776, 'ACH', 'ESG-ACH-1010']]],
  ]],
  ['CY-1057-SEP', 'PL-1057', 'Ravi Kumar', AF, 'Sep 2026', [
    ['ar', AF, ESG, 'ESG-AR-2026-0414', 105, 64, null, '2026-10-01', '2026-10-31', 'Net 30', 'SOW-AF-0091', []],
    ['ap', ESG, BP, 'BP-INV-1188', 82, 72, 64, '2026-10-03', '2026-11-02', 'Net 30', 'SOW-ESG-BP-019', [], { exc: true }],
  ]],
  ['CY-1071-AUG', 'PL-1071', 'Marcus Hill', AF, 'Aug 2026', [
    ['ar', AF, ESG, 'ESG-AR-2026-0392', 120, 168, null, '2026-08-31', '2026-09-30', 'Net 30', 'SOW-AF-0087', [['2026-09-29', 20160, 'Wire', 'AF-88214']]],
    ['ap', ESG, OD, 'OD-0329', 99, 168, null, '2026-09-03', '2026-10-03', 'Net 30', 'SOW-ESG-OD-003', [['2026-10-02', 16632, 'ACH', 'ESG-ACH-1011']]],
  ]],
  ['CY-1071-SEP', 'PL-1071', 'Marcus Hill', AF, 'Sep 2026', [
    ['ar', AF, ESG, 'ESG-AR-2026-0413', 120, 168, null, '2026-10-01', '2026-10-31', 'Net 30', 'SOW-AF-0087', []],
    ['ap', ESG, OD, 'OD-0342', 99, 168, null, '2026-10-02', '2026-11-01', 'Net 30', 'SOW-ESG-OD-003', [], { sched: '2026-10-30' }],
  ]],
  ['CY-1063-JUL', 'PL-1063', 'Anita Desai', MP, 'Jul 2026', [
    ['ar', NW, ESG, 'ESG-AR-2026-0371', 84, 184, null, '2026-07-31', '2026-09-14', 'Net 45', 'WO-NW-0388', [['2026-09-30', 8000, 'Check', 'NW-CHK-20419']]],
  ]],
];

let invN = 0, payN = 0;
for (const [cyc, pl, who, client, period, hops] of cycles) {
  const cy = (await q(`insert into billing_cycles(tenant_id,cycle_no,placement_id,person_name,client_name,period) values($1,$2,$3,$4,$5,$6)
    on conflict(tenant_id,cycle_no) do update set period=excluded.period returning id`, [T, cyc, plId[pl], who, client, period])).rows[0];
  // two passes: invoices first (pwp needs target to exist — insert AR before AP as ordered)
  const idByInv = {};
  let seq = 0;
  for (const [kind, payer, payee, inv, rate, hrs, appr, issued, due, terms, sow, pays, ex] of hops) {
    const r = await q(`insert into invoices(tenant_id,cycle_id,seq,kind,payer,payee,inv_no,rate_cents,hours,approved_hours,issued_on,due_on,terms,sow_id,exception,scheduled_for)
      values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
      on conflict(tenant_id,inv_no) do update set hours=excluded.hours returning id`,
      [T, cy.id, seq++, kind, payer, payee, inv, C(rate), hrs, appr, issued, due, terms, sow ? sowId[sow] : null, !!(ex && ex.exc), ex && ex.sched ? ex.sched : null]);
    idByInv[inv] = r.rows[0].id; invN++;
  }
  // link pay-when-paid + payments
  for (const [kind, payer, payee, inv, rate, hrs, appr, issued, due, terms, sow, pays, ex] of hops) {
    if (ex && ex.pwp) {
      const target = (await q(`select id from invoices where tenant_id=$1 and inv_no=$2`, [T, ex.pwp])).rows[0];
      if (target) await q(`update invoices set pwp_invoice_id=$1 where id=$2`, [target.id, idByInv[inv]]);
    }
    for (const [d, amt, method, ref] of pays) {
      await q(`insert into payments(tenant_id,invoice_id,paid_on,amount_cents,method,reference,idempotency_key)
        values($1,$2,$3,$4,$5,$6,$7) on conflict(tenant_id,idempotency_key) do nothing`,
        [T, idByInv[inv], d, C(amt), method, ref, `seed-${ref}`]);
      payN++;
    }
  }
}

// 8. timesheets (current week)
await q(`insert into timesheets(tenant_id,consultant_id,week_start_on,status) values($1,$2,'2026-10-06','Submitted')
  on conflict(tenant_id,consultant_id,week_start_on) do nothing`, [T, conId['Ravi Kumar']]);
await q(`insert into timesheets(tenant_id,consultant_id,week_start_on,status) values($1,$2,'2026-10-06','Approved')
  on conflict(tenant_id,consultant_id,week_start_on) do nothing`, [T, conId['Anita Desai']]);

console.log(`SEED DONE invoices:${invN} payments:${payN}`);
await c.end();
