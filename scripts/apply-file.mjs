import 'dotenv/config';
import pg from 'pg';
import fs from 'node:fs';
const file = process.argv[2] || '../supabase/003_auth_fk.sql';
const client = new pg.Client({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
try {
  await client.connect();
  await client.query(fs.readFileSync(new URL(file, import.meta.url)).toString());
  console.log('APPLIED', file);
} catch (e) { console.error('FAIL:', e.message); process.exitCode = 1; }
finally { await client.end().catch(() => {}); }
