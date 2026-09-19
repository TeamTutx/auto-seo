"use client";

import type { AdminAuditRow } from "@/lib/types";
import { formatUsd } from "@/lib/format";

export function Money({ cents, signed = false }: { cents: number; signed?: boolean }) {
  const cls = cents < 0 ? "neg" : signed && cents > 0 ? "pos" : "";
  return <span className={cls}>{formatUsd(cents, { signed })}</span>;
}

// Audit-log rows store their details as JSON; turn the common ones into a sentence.
export function describeAudit(row: AdminAuditRow): string {
  let p: Record<string, unknown> = {};
  try {
    p = row.payload ? JSON.parse(row.payload) : {};
  } catch {
    // leave empty
  }
  const who = row.actor_email ?? "System";
  switch (row.action) {
    case "credits_adjusted":
      return `${who} ${Number(p.delta) > 0 ? "added" : "removed"} ${Math.abs(Number(p.delta))} credits — ${p.note ?? ""}`;
    case "payment_recorded":
      return `${who} recorded a manual payment of ${formatUsd(Number(p.amount_cents))}${
        Number(p.credits) ? ` (+${p.credits} credits)` : ""
      } — ${p.note ?? ""}`;
    case "payment_received":
      return `Payment received: ${formatUsd(Number(p.amount_cents))} (${String(p.kind).replace("_", " ")})${
        Number(p.credits) ? `, +${p.credits} credits` : ""
      }`;
    case "product_deleted":
      return `${who} deleted product “${p.product}”`;
    case "products_reordered":
      return `${who} reordered the credit packs`;
    case "refund_recorded":
      return `Refund recorded${p.partial ? " (partial)" : ""}`;
    case "refund_needs_review":
      return `A partial refund in ${p.currency} needs manual review in Dodo`;
    case "product_updated":
      return `${who} edited product “${p.product}”`;
    case "product_created":
      return `${who} added product “${p.product}”`;
    default:
      // Subscription events land here: Signal sells none, so they're logged
      // verbatim rather than acted on (backend/app/services/dodo_webhooks.py).
      return `${who}: ${row.action.replace(/_/g, " ")}`;
  }
}
