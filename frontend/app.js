const $ = (id) => document.getElementById(id);
const toast = (t) => { const e = $('toast'); e.textContent = t; e.style.display = 'block'; clearTimeout(e._t); e._t = setTimeout(() => e.style.display = 'none', 2600); };
const token = () => localStorage.getItem('vc_token');
async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { 'Content-Type': 'application/json', ...(token() ? { Authorization: 'Bearer ' + token() } : {}), ...(opts.headers || {}) } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function tab(k) {
  $('fPw').hidden = k !== 'pw'; $('fOtp').hidden = k !== 'otp'; $('fReg').hidden = k !== 'reg';
  $('tabPw').className = k === 'pw' ? 'on' : ''; $('tabOtp').className = k === 'otp' ? 'on' : ''; $('tabReg').className = k === 'reg' ? 'on' : '';
}
function showApp(user) {
  // hand off to the full mockup page (bridge re-validates token + role)
  sessionStorage.setItem('vc_just_logged_in', '1');
  location.href = '/mockup.html';
}
async function boot() {
  if (!token()) return;
  try { const me = await api('/api/auth/me'); showApp(me); } catch { localStorage.removeItem('vc_token'); }
}
function logout() { localStorage.removeItem('vc_token'); location.reload(); }
async function doLogin() {
  try { const j = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: $('liEmail').value, password: $('liPass').value }) }); localStorage.setItem('vc_token', j.token); showApp(j.user); }
  catch (e) { $('authErr').textContent = e.message; }
}
async function doRegister() {
  try { const j = await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ email: $('rgEmail').value, password: $('rgPass').value, full_name: $('rgName').value, tenant_name: $('rgCo').value }) }); localStorage.setItem('vc_token', j.token); showApp(j.user); }
  catch (e) { $('authErr').textContent = e.message; }
}
async function reqCode() {
  try { await api('/api/auth/request-code', { method: 'POST', body: JSON.stringify({ email: $('otEmail').value }) }); toast('Code sent'); }
  catch (e) { $('authErr').textContent = e.message; }
}
async function verifyCode() {
  try { const j = await api('/api/auth/verify-code', { method: 'POST', body: JSON.stringify({ email: $('otEmail').value, code: $('otCode').value }) }); localStorage.setItem('vc_token', j.token); showApp(j.user); }
  catch (e) { $('authErr').textContent = e.message; }
}
async function resetPassword() {
  try {
    const j = await api('/api/auth/reset-password', { method: 'POST', body: JSON.stringify({ email: $('otEmail').value, code: $('otCode').value, new_password: $('otNewPass').value }) });
    localStorage.setItem('vc_token', j.token); showApp(j.user);
  } catch (e) { $('authErr').textContent = e.message; }
}
async function health() { try { toast(JSON.stringify(await api('/api/health'))); } catch (e) { toast(e.message); } }

const NAV = [['dash', 'Dashboard'], ['flow', 'Payment flow (AR/AP)'], ['recv', 'Client receipts'], ['payout', 'Vendor payouts'], ['ledger', 'Ledger'], ['sow', 'SOWs & MSAs'], ['ts', 'Timesheets'], ['co', 'Companies']];
function renderNav(v) { $('nav').innerHTML = NAV.map(([k, l]) => `<a class="${k === v ? 'on' : ''}" onclick="go('${k}')">${l}</a>`).join(''); }
const money = (c) => '$' + Math.round(Number(c || 0) / 100).toLocaleString('en-US');
async function go(v) {
  renderNav(v);
  const el = $('view'); el.innerHTML = '<p>Loading…</p>';
  try {
    if (v === 'dash') {
      const d = await api('/api/dashboard');
      el.innerHTML = `<h2>Dashboard</h2><table><tr><th>AR outstanding</th><th>Overdue</th><th>AP open</th></tr><tr><td>${money(d.ar_outstanding_cents)}</td><td>${money(d.overdue_cents)}</td><td>${money(d.ap_open_cents)}</td></tr></table>`;
    } else if (v === 'recv' || v === 'flow' || v === 'payout') {
      const kind = v === 'payout' ? 'ap' : v === 'recv' ? 'ar' : '';
      const rows = await api('/api/invoices' + (kind ? `?kind=${kind}` : ''));
      el.innerHTML = `<h2>${v}</h2><table><tr><th>Invoice</th><th>Payer → Payee</th><th>Invoiced</th><th>Paid</th><th>Balance</th><th>Due</th><th></th></tr>${rows.map(r => `<tr><td>${r.inv_no || r.id.slice(0, 8)}</td><td>${r.payer} → ${r.payee}</td><td>${money(r.invoiced_cents)}</td><td>${money(r.paid_cents)}</td><td><b>${money(r.balance_cents)}</b></td><td>${r.due_on || '—'}</td><td>${r.balance_cents > 0 ? `<button onclick="pay('${r.id}',${r.balance_cents})">Record</button>` : ''}</td></tr>`).join('')}</table>`;
    } else if (v === 'ledger') {
      const rows = await api('/api/payments/ledger');
      el.innerHTML = `<h2>Ledger</h2><table><tr><th>Date</th><th>Invoice</th><th>Amount</th><th>Method</th></tr>${rows.map(r => `<tr><td>${r.paid_on}</td><td>${r.inv_no || ''}</td><td>${money(r.amount_cents)}</td><td>${r.method || ''}</td></tr>`).join('')}</table>`;
    } else if (v === 'sow') {
      const [sows, msas] = await Promise.all([api('/api/sows'), api('/api/msas')]);
      el.innerHTML = `<h2>SOWs (${sows.length})</h2><table><tr><th>SOW</th><th>Title</th><th>End</th><th>Ceiling</th></tr>${sows.map(s => `<tr><td>${s.sow_no}</td><td>${s.title || ''}</td><td>${s.end_on || ''}</td><td>${money(s.ceiling_cents)}</td></tr>`).join('')}</table><h2>MSAs (${msas.length})</h2><table><tr><th>MSA</th><th>Counterparty</th><th>Expires</th></tr>${msas.map(m => `<tr><td>${m.msa_no}</td><td>${m.counterparty_name}</td><td>${m.expires_on || ''}</td></tr>`).join('')}</table>`;
    } else if (v === 'ts') {
      const rows = await api('/api/timesheets');
      el.innerHTML = `<h2>Timesheets</h2><table><tr><th>Consultant</th><th>Week</th><th>Status</th></tr>${rows.map(t => `<tr><td>${t.consultant_name || t.consultant_id}</td><td>${t.week_start_on}</td><td>${t.status}</td></tr>`).join('') || '<tr><td colspan=3>No rows</td></tr>'}</table>`;
    } else if (v === 'co') {
      const rows = await api('/api/companies');
      el.innerHTML = `<h2>Companies</h2><table><tr><th>Name</th><th>Type</th><th>Status</th></tr>${rows.map(c => `<tr><td>${c.name}</td><td>${c.type}</td><td>${c.status}</td></tr>`).join('')}</table><div class="row"><input id="coName" placeholder="New company name"><button onclick="addCo()">Add</button></div>`;
    }
  } catch (e) { el.innerHTML = `<p class="err">${e.message}</p>`; }
}
async function pay(id, bal) {
  try { await api('/api/payments/record', { method: 'POST', body: JSON.stringify({ invoice_id: id, amount_cents: bal }) }); toast('Payment recorded'); go('ledger'); }
  catch (e) { toast(e.message); }
}
async function addCo() {
  const name = $('coName').value.trim(); if (!name) return;
  try { await api('/api/companies', { method: 'POST', body: JSON.stringify({ name }) }); go('co'); } catch (e) { toast(e.message); }
}
boot();
