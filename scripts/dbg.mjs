const BASE = 'http://localhost:4000';
for (const p of ['/api/health', '/api/auth/login']) {
  const r = await fetch(BASE + p, p.includes('login')
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'x', password: 'y' }) }
    : {});
  const t = await r.text();
  console.log(p, '->', r.status, (r.headers.get('content-type') || '').slice(0, 30), '|', t.slice(0, 80).replace(/\n/g, ' '));
}
console.log('proxy env:', process.env.HTTP_PROXY || process.env.http_proxy || 'none');
