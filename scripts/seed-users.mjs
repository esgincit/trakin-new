import 'dotenv/config';
import pg from 'pg';
import bcrypt from 'bcryptjs';

const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();

const esg = (await c.query(`select id from tenants where name='Executive Software Guild Inc.' limit 1`)).rows[0];
if (!esg) throw new Error('ESG tenant missing — run seed-demo.mjs first');
const T = esg.id;

const PASSWORD = 'Demo@12345';
const hash = await bcrypt.hash(PASSWORD, 10);

// email, full_name, role — one per prototype role, all on ESG tenant
const users = [
  ['admin@demo.vendorchain', 'Praveen Gottimukkula', 'admin'],
  ['finance@demo.vendorchain', 'K. Reddy', 'finance'],
  ['am@demo.vendorchain', 'S. Iyer', 'am'],
  ['legal@demo.vendorchain', 'N. Patel', 'legal'],
  ['vendor@demo.vendorchain', 'S. Rao (BrightPath)', 'vendor'],
  ['consultant@demo.vendorchain', 'Ravi Kumar', 'consultant'],
  ['platform@demo.vendorchain', 'Platform Owner', 'platform'],
];

for (const [email, name, role] of users) {
  await c.query(
    `insert into app_users(email,password_hash,full_name,role,tenant_id)
     values(lower($1),$2,$3,$4,$5)
     on conflict(email) do update set password_hash=excluded.password_hash, full_name=excluded.full_name,
       role=excluded.role, tenant_id=excluded.tenant_id`,
    [email, hash, name, role, role === 'platform' ? null : T]
  );
  console.log('upserted', email, '|', role);
}
console.log('PASSWORD for all demo users:', PASSWORD);
await c.end();
