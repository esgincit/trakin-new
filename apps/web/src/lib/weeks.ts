/** Timesheet weeks run Sunday to Saturday. Dates are plain YYYY-MM-DD strings (no time zones). */
export function sundayOf(d: Date = new Date()): string {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() - d.getDay());
  return iso(x);
}

export function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number) as [number, number, number];
  return iso(new Date(y, m - 1, d + days));
}

export function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function dayLabels(weekStart: string): string[] {
  return DAYS.map((name, i) => `${name} ${Number(addDays(weekStart, i).slice(8))}`);
}
