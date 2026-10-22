import 'dotenv/config';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';

const SECRET = process.env.JWT_SECRET || 'dev-secret';
const TTL = '12h';

export async function hashPassword(pw) {
  return bcrypt.hash(pw, 10);
}
export async function checkPassword(pw, hash) {
  if (!hash) return false;
  return bcrypt.compare(pw, hash);
}
export function signToken(user) {
  return jwt.sign(
    { sub: user.id, email: user.email, role: user.role, tenant_id: user.tenant_id },
    SECRET,
    { expiresIn: TTL }
  );
}
export function authRequired(req, res, next) {
  const h = req.headers.authorization || '';
  const tok = h.startsWith('Bearer ') ? h.slice(7) : null;
  if (!tok) return res.status(401).json({ error: 'Missing token' });
  try {
    req.user = jwt.verify(tok, SECRET);
    return next();
  } catch {
    return res.status(401).json({ error: 'Invalid token' });
  }
}
export function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ error: 'Forbidden' });
    }
    return next();
  };
}
export function tenantFilter(req) {
  // platform owner sees all; others scoped to their tenant
  if (req.user.role === 'platform') return null;
  return req.user.tenant_id;
}
