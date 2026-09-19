// Money is stored as integer USD cents everywhere (see backend Payment model);
// these are the only places it becomes a display string.

export function formatUsd(cents: number, { signed = false }: { signed?: boolean } = {}): string {
  const abs = Math.abs(cents) / 100;
  const body = abs.toLocaleString("en-US", {
    minimumFractionDigits: Number.isInteger(abs) ? 0 : 2,
    maximumFractionDigits: 2,
  });
  if (cents < 0) return `-$${body}`;
  return `${signed && cents > 0 ? "+" : ""}$${body}`;
}

// A per-credit rate is a few cents, where formatUsd's "$0.08" rounds away the
// difference between packs - so show it in cents until it reaches a dollar.
export function formatRate(cents: number): string {
  if (cents >= 100) return formatUsd(cents);
  return `${Math.round(cents * 10) / 10}\u00A2`;
}

// "24" or "24.50" typed by a human -> integer cents, or null if not a valid amount.
export function parseUsdToCents(input: string): number | null {
  const cleaned = input.trim().replace(/^\$/, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(parseFloat(cleaned) * 100);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`); // backend timestamps are naive UTC
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function limitLabel(value: number | null): string {
  return value === null ? "Unlimited" : String(value);
}
