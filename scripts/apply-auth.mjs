import 'dotenv/config';
import pg from 'pg';
import fs from 'node:fs';
const client = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
try {
  await client.connect();
  const sql = fs.readFileSync(new URL('../supabase/002_auth.sql', import.meta.url));
  await client.query(sql.toString());
  console.log('AUTH MIGRATION APPLIED');
} catch (e) { console.error('FAIL:', e.message); process.exitCode = 1; }
finally { await client.end().catch(() => {}); }
