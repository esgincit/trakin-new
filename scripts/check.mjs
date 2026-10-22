import 'dotenv/config';
import pg from 'pg';

const { Client } = pg;
const client = new Client({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  connectionTimeoutMillis: 15000,
});

try {
  await client.connect();
  const { rows } = await client.query('select version() as v');
  console.log('DB OK:', rows[0].v.slice(0, 60));
  const t = await client.query(
    "select count(*)::int as n from information_schema.tables where table_schema='public' and table_name in ('tenants','invoices','payments')"
  );
  console.log('Core tables present:', t.rows[0].n, '/ 3');
} catch (e) {
  console.error('DB FAIL:', e.message);
  process.exitCode = 1;
} finally {
  await client.end().catch(() => {});
}
