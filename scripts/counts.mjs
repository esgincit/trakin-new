import 'dotenv/config';
import pg from 'pg';
const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();
const tables = ['tenants','app_users','companies','consultants','placements','msas','sows','billing_cycles','invoices','payments','timesheets','otp_codes'];
for (const t of tables) {
  try {
    const r = await c.query(`select count(*)::int as n from ${t}`);
    console.log(t + ':', r.rows[0].n);
  } catch (e) { console.log(t + ': ERR ' + e.message.slice(0, 80)); }
}
await c.end();
