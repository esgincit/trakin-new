import 'dotenv/config';
import pg from 'pg';
const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();
const r = await c.query('select code from otp_codes where email=$1 and not consumed and expires_at>now() order by created_at desc limit 1', ['admin-e2e@drep.in']);
console.log('LATEST_CODE_LEN:', (r.rows[0]?.code || '').length);
await c.end();
