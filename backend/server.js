import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { query } from './db.js';
import { sendMail, verifyMail } from './mailer.js';
import { hashPassword, checkPassword, signToken, authRequired, requireRole, tenantFilter } from './auth.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const money = (c) => '$' + Math.round(Number(c || 0)).toLocaleString('en-US');

/* ---------- health ---------- */
app.get('/api/health', async (req, res) => {
  let db = 'down', smtp = 'down';
  try { await query('select 1'); db = 'up'; } catch {}
  try { await verifyMail(); smtp = 'up'; } catch {}
  res.json({ ok: db === 'up', db, smtp, time: new Date().toISOString() });
});

/* ---------- auth ---------- */
app.post('/api/auth/register', async (req, res) => {
  const { email, password, full_name, role = 'admin', tenant_name } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: 'email and password required' });
  try {
    let tenant_id = null;
    if (tenant_name) {
      const t = await query(
        `insert into tenants(name,status,onboarding_step) values($1,'Live',8) returning id`,
        [tenant_name]
      );
      tenant_id = t.rows[0].id;
    } else {
      const t = await query(`select id from tenants order by created_at limit 1`);
      tenant_id = t.rows[0]?.id || null;
      if (!tenant_id) {
        const n = await query(
          `insert into tenants(name,status,onboarding_step) values('Default Tenant','Live',8) returning id`
        );
        tenant_id = n.rows[0].id;
      }
    }
    const ph = await hashPassword(password);
    const u = await query(
      `insert into app_users(email,password_hash,full_name,role,tenant_id)
       values(lower($1),$2,$3,$4,$5) returning id,email,full_name,role,tenant_id`,
      [email, ph, full_name || email.split('@')[0], role, role === 'platform' ? null : tenant_id]
    );
    const token = signToken(u.rows[0]);
    res.json({ token, user: u.rows[0] });
  } catch (e) {
    if (String(e.message).includes('duplicate')) return res.status(409).json({ error: 'Email already registered' });
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: 'email and password required' });
  const r = await query(`select * from app_users where email=lower($1)`, [email]);
  const u = r.rows[0];
  if (!u || !(await checkPassword(password, u.password_hash))) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }
  const token = signToken(u);
  res.json({ token, user: { id: u.id, email: u.email, full_name: u.full_name, role: u.role, tenant_id: u.tenant_id } });
});

app.post('/api/auth/request-code', async (req, res) => {
  const { email } = req.body || {};
  if (!email) return res.status(400).json({ error: 'email required' });
  const code = String(crypto.randomInt(100000, 999999));
  await query(`insert into otp_codes(email,code,expires_at) values(lower($1),$2,now()+interval '10 minutes')`, [email, code]);
  try {
    await sendMail({
      to: email,
      subject: 'Your VendorChain sign-in code',
      text: `Your code is ${code}. It expires in 10 minutes.`,
      html: `<p>Your VendorChain code is <b>${code}</b>. It expires in 10 minutes.</p>`,
    });
    res.json({ ok: true, sent: true });
  } catch (e) {
    res.status(502).json({ error: 'SMTP send failed: ' + e.message });
  }
});

app.post('/api/auth/verify-code', async (req, res) => {
  const { email, code } = req.body || {};
  if (!email || !code) return res.status(400).json({ error: 'email and code required' });
  const r = await query(
    `select * from otp_codes where email=lower($1) and code=$2 and not consumed and expires_at>now() order by created_at desc limit 1`,
    [email, code]
  );
  if (!r.rows[0]) return res.status(401).json({ error: 'Invalid or expired code' });
  await query(`update otp_codes set consumed=true where id=$1`, [r.rows[0].id]);
  let u = (await query(`select * from app_users where email=lower($1)`, [email])).rows[0];
  if (!u) {
    const t = await query(`select id from tenants order by created_at limit 1`);
    let tid = t.rows[0]?.id;
    if (!tid) tid = (await query(`insert into tenants(name,status,onboarding_step) values('Default Tenant','Live',8) returning id`)).rows[0].id;
    u = (await query(
      `insert into app_users(email,full_name,role,tenant_id) values(lower($1),$2,'consultant',$3) returning *`,
      [email, email.split('@')[0], tid]
    )).rows[0];
  }
  res.json({ token: signToken(u), user: { id: u.id, email: u.email, role: u.role, tenant_id: u.tenant_id } });
});

app.post('/api/auth/reset-password', async (req, res) => {
  const { email, code, new_password } = req.body || {};
  if (!email || !code || !new_password) return res.status(400).json({ error: 'email, code and new_password required' });
  if (String(new_password).length < 8) return res.status(400).json({ error: 'Password must be 8+ characters' });
  const r = await query(
    `select * from otp_codes where email=lower($1) and code=$2 and not consumed and expires_at>now() order by created_at desc limit 1`,
    [email, code]
  );
  if (!r.rows[0]) return res.status(401).json({ error: 'Invalid or expired code' });
  await query(`update otp_codes set consumed=true where id=$1`, [r.rows[0].id]);
  const ph = await hashPassword(new_password);
  const u = (await query(`update app_users set password_hash=$2 where email=lower($1) returning id,email,full_name,role,tenant_id`, [email, ph])).rows[0];
  if (!u) return res.status(404).json({ error: 'Email not registered — use Register instead' });
  res.json({ token: signToken(u), user: { id: u.id, email: u.email, role: u.role, tenant_id: u.tenant_id } });
});

app.get('/api/auth/me', authRequired, async (req, res) => {
  const r = await query(`select id,email,full_name,role,tenant_id from app_users where id=$1`, [req.user.sub]);
  res.json(r.rows[0] || null);
});

/* ---------- dashboard ---------- */
app.get('/api/dashboard', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const args = tid ? [tid] : [];
  const where = tid ? 'and i.tenant_id=$1' : '';
  const sql = `
    select i.kind,
      (coalesce(i.rate_cents,0)*coalesce(i.hours,0))::bigint as invoiced_cents,
      coalesce((select sum(p.amount_cents) from payments p where p.invoice_id=i.id),0)::bigint as paid_cents,
      i.due_on
    from invoices i where 1=1 ${where}`;
  const r = await query(sql, args);
  const today = new Date().toISOString().slice(0, 10);
  let arOut = 0, over = 0, apOpen = 0, held = 0, collected30 = 0;
  for (const row of r.rows) {
    const bal = Number(row.invoiced_cents) - Number(row.paid_cents);
    if (row.kind === 'ar' && bal > 0) {
      arOut += bal;
      if (row.due_on && row.due_on < today) over += bal;
    }
    if (row.kind === 'ap' && bal > 0) apOpen += bal;
  }
  res.json({ ar_outstanding_cents: arOut, overdue_cents: over, ap_open_cents: apOpen, held_cents: held, collected30_cents: collected30 });
});

/* ---------- companies ---------- */
app.get('/api/companies', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const r = tid
    ? await query(`select * from companies where tenant_id=$1 order by name`, [tid])
    : await query(`select * from companies order by name limit 100`);
  res.json(r.rows);
});
app.post('/api/companies', authRequired, async (req, res) => {
  const tid = tenantFilter(req) || req.body.tenant_id;
  if (!tid) return res.status(400).json({ error: 'tenant required' });
  const { name, type = 'Client', admin_contact, state } = req.body || {};
  if (!name) return res.status(400).json({ error: 'name required' });
  const r = await query(
    `insert into companies(tenant_id,name,type,admin_contact,state) values($1,$2,$3,$4,$5) returning *`,
    [tid, name, type, admin_contact || null, state || null]
  );
  res.json(r.rows[0]);
});

/* ---------- invoices ---------- */
app.get('/api/invoices', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const { kind, q } = req.query;
  const conds = [], params = [];
  if (tid) { params.push(tid); conds.push(`i.tenant_id=$${params.length}`); }
  if (kind) { params.push(kind); conds.push(`i.kind=$${params.length}`); }
  if (q) { params.push(`%${q}%`); conds.push(`(i.inv_no ilike $${params.length} or i.payer ilike $${params.length} or i.payee ilike $${params.length})`); }
  const where = conds.length ? 'where ' + conds.join(' and ') : '';
  const r = await query(
    `select i.*, coalesce((select sum(amount_cents) from payments p where p.invoice_id=i.id),0)::bigint as paid_cents,
      (coalesce(i.rate_cents,0)*coalesce(i.hours,0))::bigint as invoiced_cents
     from invoices i ${where} order by i.due_on nulls last, i.issued_on desc limit 200`, params);
  res.json(r.rows.map(x => ({ ...x, balance_cents: Number(x.invoiced_cents) - Number(x.paid_cents) })));
});

app.post('/api/invoices', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const tid = tenantFilter(req) || req.body.tenant_id;
  const { payer, payee, kind = 'ar', rate_cents = 0, hours = 0, due_on, terms, inv_no } = req.body || {};
  if (!payer || !payee) return res.status(400).json({ error: 'payer/payee required' });
  const no = inv_no || `INV-${Date.now().toString().slice(-6)}`;
  const r = await query(
    `insert into invoices(tenant_id,payer,payee,kind,rate_cents,hours,due_on,terms,inv_no,issued_on)
     values($1,$2,$3,$4,$5,$6,$7,$8,$9,current_date) returning *`,
    [tid, payer, payee, kind, rate_cents, hours, due_on || null, terms || null, no]
  );
  res.json(r.rows[0]);
});

/* ---------- payments ---------- */
app.post('/api/payments/record', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const { invoice_id, amount_cents, method = 'ACH', reference, idempotency_key } = req.body || {};
  if (!invoice_id || !amount_cents) return res.status(400).json({ error: 'invoice_id and amount_cents required' });
  const inv = (await query(`select *, (coalesce(rate_cents,0)*coalesce(hours,0))::bigint as invoiced_cents from invoices where id=$1`, [invoice_id])).rows[0];
  if (!inv) return res.status(404).json({ error: 'invoice not found' });
  if (tenantFilter(req) && inv.tenant_id !== tenantFilter(req)) return res.status(403).json({ error: 'wrong tenant' });
  const paid = Number((await query(`select coalesce(sum(amount_cents),0) as s from payments where invoice_id=$1`, [invoice_id])).rows[0].s);
  const bal = Number(inv.invoiced_cents) - paid;
  if (amount_cents > bal) return res.status(400).json({ error: `Overpay: balance is ${bal}` });
  const key = idempotency_key || `pay_${invoice_id}_${Date.now()}`;
  try {
    const r = await query(
      `insert into payments(tenant_id,invoice_id,paid_on,amount_cents,method,reference,idempotency_key,created_by)
       values($1,$2,current_date,$3,$4,$5,$6,$7) returning *`,
      [inv.tenant_id, invoice_id, amount_cents, method, reference || null, key, req.user.sub]
    );
    res.json(r.rows[0]);
  } catch (e) {
    if (String(e.message).includes('duplicate')) return res.status(409).json({ error: 'Duplicate payment (idempotency)' });
    throw e;
  }
});

app.post('/api/payment-runs/approve', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const { invoice_ids = [], method = 'ACH' } = req.body || {};
  if (!invoice_ids.length) return res.status(400).json({ error: 'invoice_ids required' });
  const out = [];
  for (const id of invoice_ids) {
    const inv = (await query(`select *, (coalesce(rate_cents,0)*coalesce(hours,0))::bigint as invoiced_cents from invoices where id=$1`, [id])).rows[0];
    if (!inv || inv.exception) continue;
    const paid = Number((await query(`select coalesce(sum(amount_cents),0) as s from payments where invoice_id=$1`, [id])).rows[0].s);
    const bal = Number(inv.invoiced_cents) - paid;
    if (bal <= 0) continue;
    const r = await query(
      `insert into payments(tenant_id,invoice_id,paid_on,amount_cents,method,reference,idempotency_key,created_by)
       values($1,$2,current_date,$3,$4,$5,$6,$7) returning *`,
      [inv.tenant_id, id, bal, method, `RUN-${new Date().toISOString().slice(0, 10)}`, `run_${id}_${Date.now()}_${out.length}`, req.user.sub]
    );
    out.push(r.rows[0]);
  }
  res.json({ paid: out.length, payments: out });
});

app.get('/api/payments/ledger', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const r = tid
    ? await query(`select p.*, i.inv_no, i.payer, i.payee, i.kind from payments p join invoices i on i.id=p.invoice_id where p.tenant_id=$1 order by p.paid_on desc limit 200`, [tid])
    : await query(`select p.*, i.inv_no from payments p join invoices i on i.id=p.invoice_id order by p.paid_on desc limit 200`);
  res.json(r.rows);
});

/* ---------- sows / msas ---------- */
app.get('/api/sows', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const r = tid ? await query(`select * from sows where tenant_id=$1 order by end_on`, [tid])
    : await query(`select * from sows order by end_on limit 100`);
  res.json(r.rows);
});
app.get('/api/msas', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const r = tid ? await query(`select * from msas where tenant_id=$1 order by expires_on`, [tid])
    : await query(`select * from msas order by expires_on limit 100`);
  res.json(r.rows);
});

/* ---------- timesheets ----------
   Dual approval: a consultant's timesheet is routed to both the Placed By
   company and the End Client company. It is 'Approved' only after BOTH
   parties approve; a rejection by either party marks it 'Rejected'. */
function tsParty(req) {
  // party of the logged-in approver: end-client users act for the end client,
  // everyone else (vendor/tenant admin) acts for the Placed By company.
  return req.body.party === 'end_client' || req.body.party === 'placed_by'
    ? req.body.party
    : (req.body.party === undefined && req.user.role === 'am' ? 'end_client' : 'placed_by');
}
app.get('/api/timesheets', authRequired, async (req, res) => {
  const tid = tenantFilter(req);
  const args = tid ? [tid] : [];
  const where = tid ? 'where t.tenant_id=$1' : '';
  const r = await query(
    `select t.*, c.name as consultant_name,
      coalesce(ec.name, 'End Client') as end_client_name,
      coalesce(pbc.name, 'Placed By') as placed_by_name
     from timesheets t
     left join consultants c on c.id = t.consultant_id
     left join placements p on p.id = coalesce(t.placement_id,
       (select tl.placement_id from timesheet_lines tl
         where tl.timesheet_id = t.id and tl.placement_id is not null limit 1))
     left join companies ec on ec.id = p.end_client_company_id
     left join companies pbc on pbc.id = p.placed_by_company_id
     ${where} order by t.week_start_on desc limit 100`, args);
  res.json(r.rows);
});
app.post('/api/timesheets/submit', authRequired, requireRole('consultant', 'admin', 'platform'), async (req, res) => {
  const tid = tenantFilter(req) || req.body.tenant_id;
  const { consultant_id, week_start_on, placement_id, lines = [] } = req.body || {};
  if (!consultant_id || !week_start_on) return res.status(400).json({ error: 'consultant_id and week_start_on required' });
  if (!tid) return res.status(400).json({ error: 'tenant required' });
  const r = await query(
    `insert into timesheets(tenant_id,consultant_id,week_start_on,placement_id,status,submitted_at,placed_by_status,end_client_status)
     values($1,$2,$3,$4,'Submitted',now(),'Pending','Pending')
     on conflict (tenant_id,consultant_id,week_start_on) do update
       set status='Submitted', submitted_at=now(), placement_id=$4,
           placed_by_status='Pending', end_client_status='Pending',
           placed_by_reject_reason=null, end_client_reject_reason=null, decided_by=null
     returning *`, [tid, consultant_id, week_start_on, placement_id || null]);
  const ts = r.rows[0];
  for (const l of lines) {
    if (!l || !l.placement_id || l.day_index == null) continue;
    await query(
      `insert into timesheet_lines(timesheet_id,placement_id,day_index,hours) values($1,$2,$3,$4)
       on conflict (timesheet_id,placement_id,day_index) do update set hours=excluded.hours`,
      [ts.id, l.placement_id, l.day_index, l.hours || 0]);
  }
  res.json({ ok: true, timesheet: ts, routed_to: ['placed_by', 'end_client'] });
});
app.post('/api/timesheets/:id/approve', authRequired, requireRole('admin', 'vendor', 'am', 'platform'), async (req, res) => {
  const party = tsParty(req);
  const t = (await query(`select * from timesheets where id=$1`, [req.params.id])).rows[0];
  if (!t) return res.status(404).json({ error: 'timesheet not found' });
  if (tenantFilter(req) && t.tenant_id !== tenantFilter(req)) return res.status(403).json({ error: 'wrong tenant' });
  if (t[`${party}_status`] === 'Rejected') return res.status(409).json({ error: `already rejected by ${party.replace('_', ' ')}` });
  if (t[`${party}_status`] === 'Approved') return res.json({ ok: true, status: t.status, placed_by_status: t.placed_by_status, end_client_status: t.end_client_status });
  await query(
    `update timesheets set ${party}_status='Approved', ${party}_decided_by=$2, ${party}_decided_at=now() where id=$1`,
    [req.params.id, req.user.sub]);
  const cur = (await query(`select * from timesheets where id=$1`, [req.params.id])).rows[0];
  const both = cur.placed_by_status === 'Approved' && cur.end_client_status === 'Approved';
  if (both) await query(`update timesheets set status='Approved', decided_by=$2 where id=$1`, [req.params.id, req.user.sub]);
  res.json({ ok: true, status: both ? 'Approved' : 'Submitted', placed_by_status: cur.placed_by_status, end_client_status: cur.end_client_status });
});
app.post('/api/timesheets/:id/reject', authRequired, requireRole('admin', 'vendor', 'am', 'platform'), async (req, res) => {
  const party = tsParty(req);
  const t = (await query(`select * from timesheets where id=$1`, [req.params.id])).rows[0];
  if (!t) return res.status(404).json({ error: 'timesheet not found' });
  if (tenantFilter(req) && t.tenant_id !== tenantFilter(req)) return res.status(403).json({ error: 'wrong tenant' });
  await query(
    `update timesheets set ${party}_status='Rejected', ${party}_decided_by=$2, ${party}_decided_at=now(),
       ${party}_reject_reason=$3, status='Rejected' where id=$1`,
    [req.params.id, req.user.sub, req.body.reason || '']);
  res.json({ ok: true });
});

/* ---------- reminders via SMTP ---------- */
app.post('/api/reminders/invoice', authRequired, async (req, res) => {
  const { invoice_id, to } = req.body || {};
  const inv = (await query(`select * from invoices where id=$1`, [invoice_id])).rows[0];
  if (!inv) return res.status(404).json({ error: 'invoice not found' });
  const dest = to || `${inv.payer} AP`;
  await sendMail({
    to: dest.includes('@') ? dest : process.env.SMTP_FROM,
    subject: `Reminder: invoice ${inv.inv_no} due ${inv.due_on || ''}`,
    text: `Hello ${inv.payer}, invoice ${inv.inv_no} for ${money(Number(inv.rate_cents) * Number(inv.hours) / 100)} is due ${inv.due_on || ''}.`,
  });
  res.json({ ok: true });
});

/* ---------- mockup bridge: full-prototype state + mutations ----------
   Shapes match vendorchain-app (5) in-memory model so mockup.html
   renders live DB data. Money in dollars (rate) / dollars (amounts). */
function resolveTid(req) {
  if (req.user.role !== 'platform' && req.user.tenant_id) return req.user.tenant_id;
  return null; // platform resolved below
}
async function effectiveTid(req) {
  const t = resolveTid(req);
  if (t) return t;
  const esg = (await query(`select id from tenants where name='Executive Software Guild Inc.' limit 1`)).rows[0];
  if (esg) return esg.id;
  return (await query(`select id from tenants order by created_at limit 1`)).rows[0]?.id || null;
}

app.get('/api/mockup/state', authRequired, async (req, res) => {
  const tid = await effectiveTid(req);
  if (!tid) return res.json({ cycles: [], sows: [], msas: [], companies: [], placements: [] });
  const [cy, inv, pay, sow, msa, co, pl] = await Promise.all([
    query(`select bc.*, p.placement_no from billing_cycles bc left join placements p on p.id=bc.placement_id where bc.tenant_id=$1`, [tid]),
    query(`select i.*, s.sow_no, (select inv2.inv_no from invoices inv2 where inv2.id=i.pwp_invoice_id) as pwp_no from invoices i left join sows s on s.id=i.sow_id where i.tenant_id=$1 order by i.seq`, [tid]),
    query(`select p.* from payments p where p.tenant_id=$1`, [tid]),
    query(`select * from sows where tenant_id=$1`, [tid]),
    query(`select * from msas where tenant_id=$1`, [tid]),
    query(`select * from companies where tenant_id=$1 order by name`, [tid]),
    query(`select * from placements where tenant_id=$1`, [tid]),
  ]);
  const paysByInv = {};
  for (const p of pay.rows) {
    (paysByInv[p.invoice_id] = paysByInv[p.invoice_id] || []).push({
      date: p.paid_on?.slice?.(0, 10) || p.paid_on, amt: Number(p.amount_cents) / 100, method: p.method, ref: p.reference,
    });
  }
  const invById = Object.fromEntries(inv.rows.map((x) => [x.id, x]));
  const hopsByCycle = {};
  for (const h of inv.rows) {
    const hop = {
      payer: h.payer, payee: h.payee, inv: h.inv_no,
      rate: h.rate_cents == null ? null : Number(h.rate_cents) / 100,
      hrs: Number(h.hours), ...(h.approved_hours != null ? { apprHrs: Number(h.approved_hours) } : {}),
      issued: h.issued_on?.slice?.(0, 10) || h.issued_on, due: h.due_on?.slice?.(0, 10) || h.due_on,
      terms: h.terms, sow: h.sow_no || undefined,
      ...(h.pwp_no ? { pwp: h.pwp_no } : {}),
      ...(h.scheduled_for ? { scheduled: h.scheduled_for?.slice?.(0, 10) || h.scheduled_for } : {}),
      ...(h.exception ? { exception: true } : {}),
      ...(h.kind === 'upstream' ? { upstream: true, reported: h.reported_on || h.issued_on } : {}),
      ...(h.kind === 'payroll' ? { payroll: true } : {}),
      payments: paysByInv[h.id] || [],
    };
    // prototype omits inv/rate for upstream hops only; keep inv for lookup
    (hopsByCycle[h.cycle_id] = hopsByCycle[h.cycle_id] || []).push(hop);
  }
  const cycles = cy.rows.map((c) => ({
    id: c.cycle_no, pl: c.placement_no, person: c.person_name, client: c.client_name,
    period: c.period, hops: hopsByCycle[c.id] || [],
  }));
  res.json({
    cycles,
    sows: sow.rows.map((s) => ({
      id: s.sow_no, msa: (msa.rows.find((m) => m.id === s.msa_id) || {}).msa_no,
      party: s.counterparty_name, side: s.side, title: s.title, people: s.consultant_name,
      start: s.start_on?.slice?.(0, 10), end: s.end_on?.slice?.(0, 10),
      ceiling: Number(s.ceiling_cents) / 100, prior: 0, priorPaid: 0, status: s.status,
    })),
    msas: msa.rows.map((m) => ({
      id: m.msa_no, kind: m.kind || 'MSA', party: m.counterparty_name, side: m.side,
      effective: m.effective_on?.slice?.(0, 10), expiry: m.expires_on?.slice?.(0, 10),
      terms: m.terms, renew: m.renewal, notice: m.notice, insurance: m.insurance, signed: m.signed_by,
    })),
    companies: co.rows.map((c) => ({ name: c.name, type: c.type, admin: c.admin_contact, state: c.state, status: c.status })),
    placements: pl.rows.map((p) => ({
      id: p.placement_no, person: p.person_name, role: p.role_title, project: p.project_name,
      start: p.start_on?.slice?.(0, 10), end: p.end_on?.slice?.(0, 10), status: p.status, type: p.engagement,
    })),
  });
});

async function findInv(tid, invNo) {
  return (await query(`select * from invoices where tenant_id=$1 and inv_no=$2`, [tid, invNo])).rows[0];
}
app.post('/api/mockup/payments', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const tid = await effectiveTid(req);
  const { inv, amt, date, method = 'ACH', ref, idempotency_key } = req.body || {};
  if (!inv || !(Number(amt) > 0)) return res.status(400).json({ error: 'inv and amt>0 required' });
  const h = await findInv(tid, inv);
  if (!h) return res.status(404).json({ error: 'invoice not found' });
  const paid = Number((await query(`select coalesce(sum(amount_cents),0) as s from payments where invoice_id=$1`, [h.id])).rows[0].s);
  const bal = Number(h.rate_cents) * Number(h.hours) - paid;
  const cents = Math.round(Number(amt) * 100);
  if (cents > bal) return res.status(400).json({ error: `Overpay: balance is $${(bal / 100).toFixed(2)}` });
  try {
    const r = await query(
      `insert into payments(tenant_id,invoice_id,paid_on,amount_cents,method,reference,idempotency_key,created_by)
       values($1,$2,$3,$4,$5,$6,$7,$8) returning *`,
      [tid, h.id, date || new Date().toISOString().slice(0, 10), cents, method, ref || 'Manual entry', idempotency_key || `ui-${inv}-${Date.now()}`, req.user.sub]
    );
    res.json({ ok: true, payment: r.rows[0], balance_cents: bal - cents });
  } catch (e) {
    if (String(e.message).includes('duplicate')) return res.status(409).json({ error: 'Duplicate (idempotency)' });
    throw e;
  }
});
app.post('/api/mockup/payment-runs/approve', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const tid = await effectiveTid(req);
  const { invs = [], method = 'ACH' } = req.body || {};
  if (!invs.length) return res.status(400).json({ error: 'invs required' });
  let n = 0, total = 0;
  for (const no of invs) {
    const h = await findInv(tid, no);
    if (!h || h.exception) continue;
    const paid = Number((await query(`select coalesce(sum(amount_cents),0) as s from payments where invoice_id=$1`, [h.id])).rows[0].s);
    const bal = Number(h.rate_cents) * Number(h.hours) - paid;
    if (bal <= 0) continue;
    await query(
      `insert into payments(tenant_id,invoice_id,paid_on,amount_cents,method,reference,idempotency_key,created_by)
       values($1,$2,current_date,$3,$4,$5,$6,$7) on conflict(tenant_id,idempotency_key) do nothing`,
      [tid, h.id, bal, method, `RUN-${new Date().toISOString().slice(0, 10)}`, `run-${no}-${Date.now()}-${n}`, req.user.sub]
    );
    n++; total += bal;
  }
  res.json({ ok: true, paid: n, total_cents: total });
});
app.post('/api/mockup/resolve-exception', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const tid = await effectiveTid(req);
  const h = await findInv(tid, req.body?.inv);
  if (!h) return res.status(404).json({ error: 'invoice not found' });
  await query(`update invoices set hours=approved_hours, exception=false where id=$1`, [h.id]);
  res.json({ ok: true });
});
app.post('/api/mockup/schedule', authRequired, requireRole('admin', 'finance', 'platform'), async (req, res) => {
  const tid = await effectiveTid(req);
  const h = await findInv(tid, req.body?.inv);
  if (!h) return res.status(404).json({ error: 'invoice not found' });
  await query(`update invoices set scheduled_for=$2 where id=$1`, [h.id, req.body?.date || '2026-10-16']);
  res.json({ ok: true });
});

/* ---------- api error shape (never leak HTML for /api) ---------- */
app.use('/api', (err, req, res, next) => {
  console.error('API', req.method, req.path, err.message);
  res.status(500).json({ error: err.message });
});

/* ---------- frontend ---------- */
app.use(express.static(path.join(__dirname, '..', 'frontend')));
app.use((req, res, next) => {
  if (req.path.startsWith('/api/')) return next();
  if (req.method !== 'GET') return next();
  res.sendFile(path.join(__dirname, '..', 'frontend', 'index.html'));
});

const PORT = Number(process.env.PORT || 4000);
app.listen(PORT, () => console.log(`VendorChain API on :${PORT}`));
