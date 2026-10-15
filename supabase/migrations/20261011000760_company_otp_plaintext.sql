-- =============================================================================
-- myTrakIn · 0760 · Readable company-email OTPs
--
-- Owner's call: the 6-digit company-verification code is stored readable
-- (email_otp_code) so support can see/resend it from the database while mail
-- delivery is being fixed. Mitigations: cleared on verify and on every resend,
-- never returned by any API (except the existing test-only debug field), and
-- legacy hashes keep working until they expire.
-- =============================================================================

set search_path = mytrakin, public, extensions;

alter table mytrakin.onboarding_sessions
  add column if not exists email_otp_code text;
