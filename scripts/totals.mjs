import 'dotenv/config';
import pg from 'pg';
const c = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
await c.connect();
const r = await c.query(`select i.kind,
  sum((coalesce(i.rate_cents,0)*coalesce(i.hours,0))::bigint) as invoiced,
  sum(coalesce((select sum(p.amount_cents) from payments p where p.invoice_id=i.id),0)::bigint) as paid
  from invoices i group by i.kind`);
for (const row of r.rows) {
  const bal = Number(row.invoiced) - Number(row.paid);
  console.log(row.kind, 'invoiced $' + Math.round(Number(row.invoiced) / 100).toLocaleString(), '| paid $' + Math.round(Number(row.paid) / 100).toLocaleString(), '| open $' + Math.round(bal / 100).toLocaleString());
}
await c.end();
