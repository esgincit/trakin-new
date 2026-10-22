import 'dotenv/config';
import pg from 'pg';
import fs from 'node:fs';

const files = ['../supabase/schema.sql', '../supabase/002_auth.sql', '../supabase/003_auth_fk.sql', '../supabase/004_timesheet_dual_approval.sql'];
const client = new pg.Client({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
  connectionTimeoutMillis: 15000,
});
try {
  await client.connect();
  for (const f of files) {
    const sql = fs.readFileSync(new URL(f, import.meta.url));
    await client.query(sql.toString());
    console.log('APPLIED', f);
  }
} catch (e) {
  console.error('SCHEMA FAIL:', e.message);
  process.exitCode = 1;
} finally {
  await client.end().catch(() => {});
}
