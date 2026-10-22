/* VendorChain mockup <-> live API bridge.
   Runs after the mockup's own script. Replaces in-memory money data
   (cycles) with DB state and routes mutations through the backend.
   Reference/UX data (consultants, projects, messages, policies) stays local. */
(function () {
  'use strict';
  var tok = localStorage.getItem('vc_token');
  if (!tok) { location.href = '/'; return; }

  function me() {
    try { return JSON.parse(atob(tok.split('.')[1])); }
    catch (e) { return {}; }
  }
  async function api(path, opts) {
    opts = opts || {};
    var r = await fetch(path, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
    return j;
  }

  // role from JWT (backend is source of truth for identity)
  try {
    var u = me();
    if (u.role && typeof role !== 'undefined') {
      role = u.role;
      var sel = document.getElementById('role');
      if (sel) sel.value = u.role;
    }
  } catch (e) {}

  function idx(list, key) {
    var m = {};
    list.forEach(function (x, i) { m[x[key]] = i; });
    return m;
  }

  function applyState(s) {
    // cycles: wholesale replace (money source of truth) + synthesize
    // upstream hop for AR billed via a prime vendor (not stored in DB)
    cycles.length = 0;
    (s.cycles || []).forEach(function (c) {
      var hops = (c.hops || []).slice();
      var ar = null;
      for (var i = 0; i < hops.length; i++) {
        if (hops[i].inv && hops[i].inv.indexOf('ESG-AR') === 0) { ar = hops[i]; break; }
      }
      if (ar && c.client && ar.payer !== c.client) {
        hops.unshift({ upstream: true, payer: c.client, payee: ar.payer, reported: null });
      }
      c.hops = hops;
      cycles.push(c);
    });
    // merge reference tables by key, preserving local-only fields
    // (prior/priorPaid/amend/flow-down, headcounts, chain contracts)
    var sm = idx(sows, 'id');
    Object.keys(sm).forEach(function (k) {
      var inc = s.sows[sm[k]];
      var loc = null;
      var arr = sows;
      for (var j = 0; j < arr.length; j++) if (arr[j].id === k) loc = arr[j];
      if (loc) {
        ['msa', 'party', 'side', 'title', 'people', 'start', 'end', 'status'].forEach(function (f) {
          if (inc[f] !== undefined && inc[f] !== null) loc[f] = inc[f];
        });
        if (inc.ceiling !== undefined) loc.ceiling = inc.ceiling;
      } else {
        sows.push(Object.assign({ prior: 0, priorPaid: 0, status: 'Active' }, inc));
      }
    });
    (s.msas || []).forEach(function (inc) {
      var loc = null;
      for (var j = 0; j < msas.length; j++) if (msas[j].id === inc.id) loc = msas[j];
      if (loc) Object.assign(loc, inc);
      else msas.push(inc);
    });
    (s.companies || []).forEach(function (inc) {
      var loc = null;
      for (var j = 0; j < companies.length; j++) if (companies[j].name === inc.name) loc = companies[j];
      if (loc) {
        loc.type = inc.type || loc.type; loc.admin = inc.admin || loc.admin;
        loc.state = inc.state || loc.state; loc.status = inc.status || loc.status;
      } else {
        companies.push(Object.assign({ w2: 0, t1099: 0, c2c: 0, ein: '—' }, inc));
      }
    });
    (s.placements || []).forEach(function (inc) {
      var loc = null;
      for (var j = 0; j < placements.length; j++) if (placements[j].id === inc.id) loc = placements[j];
      if (loc) {
        ['person', 'role', 'project', 'start', 'end', 'status', 'type'].forEach(function (f) {
          if (inc[f] !== undefined) loc[f] = inc[f];
        });
      } else {
        placements.push(Object.assign({ chain: [] }, inc));
      }
    });
  }

  async function refreshState() {
    var s = await api('/api/mockup/state');
    applyState(s);
    if (typeof closeDrawer === 'function') closeDrawer();
    renderNav();
    render();
  }

  // ---- mutation wrappers (same signatures as mockup originals) ----
  savePayment = async function (inv) {
    var amtEl = document.getElementById('pAmt');
    var dtEl = document.getElementById('pDate');
    var mEl = document.getElementById('pMeth');
    var rEl = document.getElementById('pRef');
    var body = {
      inv: inv,
      amt: amtEl ? +amtEl.value : 0,
      date: dtEl && dtEl.value ? dtEl.value : new Date().toISOString().slice(0, 10),
      method: mEl ? mEl.value : 'ACH',
      ref: rEl && rEl.value ? rEl.value : undefined,
    };
    try {
      var r = await api('/api/mockup/payments', { method: 'POST', body: body });
      await refreshState();
      toast('Payment recorded on ' + inv + ' — balance $' + (r.balance_cents / 100).toFixed(0));
    } catch (e) { toast(e.message); }
  };

  approveRun = async function () {
    var sel = Array.prototype.slice.call(document.querySelectorAll('.runck:checked')).map(function (c) { return c.value; });
    if (!sel.length) { toast('Select at least one eligible invoice'); return; }
    var mEl = document.getElementById('runMeth');
    try {
      var r = await api('/api/mockup/payment-runs/approve', {
        method: 'POST', body: { invs: sel, method: mEl ? mEl.value.split(' ')[0] : 'ACH' },
      });
      await refreshState();
      toast('Paid ' + r.paid + ' invoice(s), $' + Math.round(r.total_cents / 100).toLocaleString());
    } catch (e) { toast(e.message); }
  };

  resolveExc = async function (inv) {
    try {
      await api('/api/mockup/resolve-exception', { method: 'POST', body: { inv: inv } });
      await refreshState();
      toast(inv + ' corrected to approved hours and now eligible');
    } catch (e) { toast(e.message); }
  };

  schedule = async function (inv) {
    try {
      await api('/api/mockup/schedule', { method: 'POST', body: { inv: inv, date: '2026-10-16' } });
      await refreshState();
      toast(inv + ' scheduled for the Oct 16 run');
    } catch (e) { toast(e.message); }
  };

  // ---- boot: load live state, then render ----
  window.vcLogout = function () {
    localStorage.removeItem('vc_token');
    location.href = '/';
  };
  api('/api/mockup/state').then(function (s) {
    applyState(s);
    renderNav();
    render();
    var tn = document.getElementById('tenantName');
    if (tn && tn.textContent.indexOf('live API') < 0) tn.textContent += ' · live API';
    if (sessionStorage.getItem('vc_just_logged_in')) {
      sessionStorage.removeItem('vc_just_logged_in');
      toast('Signed in — live data loaded');
    }
  }).catch(function (e) {
    if (String(e.message).includes('401')) { location.href = '/'; return; }
    toast('API offline — showing demo data (' + e.message + ')');
  });
})();
