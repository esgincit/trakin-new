// End-to-end check: login -> mockup state -> create invoice ->
// record payment -> idempotency -> overpay guard -> cleanup.
const BASE = process.env.VC_BASE || 'http://localhost:4000';
const j = (r) => r.json().then((b) => ({ ok: r.ok, status: r.status, b }));

const login = await fetch(BASE + '/api/auth/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'admin@demo.vendorchain', password: 'Demo@12345' }),
}).then(j);
if (!login.ok) throw new Error('login failed: ' + JSON.stringify(login.b));
const H = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + login.b.token };

const state = await fetch(BASE + '/api/mockup/state', { headers: H }).then(j);
if (!state.ok) throw new Error('state failed');
const hops = state.b.cycles.flatMap((c) => c.hops);
console.log('STATE cycles:', state.b.cycles.length, '| hops:', hops.length,
  '| sows:', state.b.sows.length, '| msas:', state.b.msas.length,
  '| companies:', state.b.companies.length, '| placements:', state.b.placements.length);
if (state.b.cycles.length < 7) throw new Error('expected >=7 cycles');

const invNo = 'TEST-E2E-' + Date.now().toString().slice(-6);
const created = await fetch(BASE + '/api/invoices', {
  method: 'POST', headers: H,
  body: JSON.stringify({ payer: 'TestCo', payee: 'TestVendor', kind: 'ar', rate_cents: 10000, hours: 10, inv_no: invNo }),
}).then(j);
if (!created.ok) throw new Error('create invoice failed: ' + JSON.stringify(created.b));

const pay1 = await fetch(BASE + '/api/mockup/payments', {
  method: 'POST', headers: H,
  body: JSON.stringify({ inv: invNo, amt: 500, method: 'ACH', ref: 'E2E-1', idempotency_key: 'e2e-' + invNo }),
}).then(j);
if (!pay1.ok) throw new Error('pay1 failed: ' + JSON.stringify(pay1.b));
console.log('PAY1 balance_cents:', pay1.b.balance_cents, '(expect 50000)');

const dup = await fetch(BASE + '/api/mockup/payments', {
  method: 'POST', headers: H,
  body: JSON.stringify({ inv: invNo, amt: 100, ref: 'E2E-dup', idempotency_key: 'e2e-' + invNo }),
}).then(j);
console.log('IDEMPOTENCY:', dup.status === 409 ? 'PASS (409)' : 'FAIL ' + dup.status);

const over = await fetch(BASE + '/api/mockup/payments', {
  method: 'POST', headers: H,
  body: JSON.stringify({ inv: invNo, amt: 600, ref: 'E2E-over' }),
}).then(j);
console.log('OVERPAY GUARD:', over.status === 400 ? 'PASS (400)' : 'FAIL ' + over.status);

// cleanup via API-adjacent SQL? no delete endpoint — direct DB cleanup below.
console.log('CLEANUP_ID:', created.b.id);
console.log('E2E DONE');
