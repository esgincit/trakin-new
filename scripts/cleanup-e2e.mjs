import 'dotenv/config';
import pg from 'pg';
const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();
const ids = (await c.query(`select id from invoices where inv_no like 'TEST-E2E-%'`)).rows.map((r) => r.id);
if (ids.length) {
  await c.query(`delete from payments where invoice_id = any($1)`, [ids]);
  await c.query(`delete from invoices where id = any($1)`, [ids]);
}
console.log('cleaned', ids.length, 'test invoice(s)');
await c.end();
