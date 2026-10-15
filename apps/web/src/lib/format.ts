const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** Money, or a masked value when the API hid it (null) — the AR/AP-only rule. */
export function money(v: number | string | null | undefined, whole = false): string {
  if (v === null || v === undefined || v === "") return "••••";
  const n = Number(v);
  return (whole ? usd0 : usd).format(n);
}

export function num(v: number | string | null | undefined, digits = 1): string {
  if (v === null || v === undefined || v === "") return "–";
  return Number(v).toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function date(v: string | null | undefined): string {
  if (!v) return "–";
  const d = new Date(v.length === 10 ? v + "T00:00:00" : v);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function dateTime(v: string | null | undefined): string {
  if (!v) return "–";
  return new Date(v).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function label(v: string | null | undefined): string {
  if (!v) return "–";
  const special: Record<string, string> = {
    w2_fulltime: "W-2 full-time", w2_contract: "W-2 contract", c2c: "C2C", e2e: "E2E", "1099": "1099", ar: "AR", ap: "AP",
    prime_vendor: "Prime vendor", end_client: "End client", tenant_admin: "Admin", account_manager: "Account manager",
    vendor_admin: "Vendor", client_user: "Client", msa: "MSA", nda: "NDA", ica: "Contractor agreement",
    we_bill: "We bill", we_pay: "We pay", due_30: "Within 30 days", due_120: "Within 120 days", ok: "OK", i9_reverification: "I-9 reverification", ead: "EAD", i94: "I-94", coi: "COI", w9: "W-9",
  };
  return special[v] ?? v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

const TONES: Record<string, string> = {
  paid: "good", approved: "good", active: "good", signed: "good", completed: "good", valid: "good", accepted: "good", ok: "good",
  open: "brand", sent: "brand", submitted: "brand", scheduled: "brand", ready_to_pay: "brand", viewed: "brand", onboarding: "brand",
  part_paid: "warn", held: "warn", pending: "warn", draft: "", ending: "warn", due_120: "warn", needs_info: "warn",
  out_for_signature: "violet", invited: "violet", received: "violet",
  overdue: "bad", overdue_part_paid: "bad", exception: "bad", rejected: "bad", declined: "bad", expired: "bad", missing: "bad",
  due_30: "bad", void: "", voided: "", former: "", inactive: "", not_submitted: "bad", locked: "bad", suspended: "bad",
};
export const tone = (status: string | null | undefined) => TONES[status ?? ""] ?? "";

export function initials(name: string | null | undefined): string {
  return (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
}

export function daysLeft(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  if (n < 0) return `${-n} days ago`;
  if (n === 0) return "today";
  return `in ${n} days`;
}
