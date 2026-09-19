"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatRate, formatUsd } from "@/lib/format";
import type { BillingSummary } from "@/lib/types";
import { Money } from "@/components/admin/AdminBits";

export default function BillingPage() {
  // useSearchParams() needs a Suspense boundary or `next build` fails.
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const searchParams = useSearchParams();
  const checkout = searchParams.get("checkout");
  const { refresh } = useAuth();

  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(checkout === "success");
  const baseline = useRef<number | null>(null);

  const load = useCallback(async () => {
    const s = await api.getBilling();
    setSummary(s);
    return s;
  }, []);

  useEffect(() => {
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load billing."));
  }, [load]);

  // Coming back from checkout: the credits are granted by a webhook that can land
  // a few seconds after the redirect, so poll briefly instead of showing a stale
  // balance and making them wonder whether the payment worked.
  useEffect(() => {
    if (!waiting) return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      try {
        const s = await load();
        if (baseline.current === null) baseline.current = s.payments.length;
        else if (s.payments.length > baseline.current) {
          await refresh();
          setWaiting(false);
        }
      } catch {
        // keep trying
      }
      if (tries >= 12) setWaiting(false);
    }, 2500);
    return () => clearInterval(timer);
  }, [waiting, load, refresh]);

  async function buy(productKey: string) {
    setBusy(productKey);
    setError(null);
    try {
      const { checkout_url } = await api.startCheckout(productKey);
      window.location.href = checkout_url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start checkout.");
      setBusy(null);
    }
  }

  async function manage() {
    setBusy("portal");
    setError(null);
    try {
      const { url } = await api.openBillingPortal();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open the billing portal.");
      setBusy(null);
    }
  }

  if (!summary) {
    return error ? <div className="form-error">{error}</div> : <div className="loading-state">Loading…</div>;
  }

  return (
    <>
      <div className="topbar">
        <h1 className="page-title">Credits & billing</h1>
      </div>

      {waiting && <div className="note">Payment received — adding your credits…</div>}
      {checkout === "cancelled" && <div className="note">Checkout cancelled — you haven’t been charged.</div>}
      {!summary.billing_enabled && (
        <div className="note">Online payments aren’t switched on yet. Credit packs will be purchasable here soon.</div>
      )}
      {error && <div className="form-error">{error}</div>}

      <div className="stat-row">
        <div className="stat-cell">
          <div className="stat-label">Credits remaining</div>
          <div className="stat-value">{summary.credits_balance}</div>
          <div className="admin-hint">they don’t expire</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Credits bought</div>
          <div className="stat-value">{summary.credits_purchased}</div>
          <div className="admin-hint">including anything we’ve granted you</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Payment details</div>
          {summary.can_manage_billing ? (
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 6 }} disabled={busy === "portal"} onClick={manage}>
              Manage in portal
            </button>
          ) : (
            <div className="admin-hint" style={{ marginTop: 8 }}>
              Nothing saved yet — there’s no subscription to cancel.
            </div>
          )}
        </div>
      </div>

      <div className="section-title" style={{ margin: "28px 0 10px" }}>
        Buy credits
      </div>
      {summary.packs.length === 0 ? (
        <div className="admin-hint">No credit packs are on sale right now.</div>
      ) : (
        <div className="plan-cards">
          {summary.packs.map((pack) => (
            <div key={pack.key} className={`plan-card ${pack.badge ? "current" : ""}`}>
              <div className="plan-card-name">
                {pack.name}
                {pack.badge && <span className="admin-tag">{pack.badge}</span>}
              </div>
              <div className="plan-card-price">{formatUsd(pack.price_cents)}</div>
              <ul>
                <li>
                  {pack.credits} credits, added as soon as the payment clears
                  {pack.price_per_credit_cents ? ` (${formatRate(pack.price_per_credit_cents)} each)` : ""}
                </li>
                {pack.description && <li>{pack.description}</li>}
                <li>One-time payment — no subscription</li>
              </ul>
              <button className="btn" disabled={!pack.purchasable || busy === pack.key} onClick={() => buy(pack.key)}>
                {pack.purchasable ? "Buy credits" : "Coming soon"}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="section-title" style={{ margin: "28px 0 10px" }}>
        What a credit buys
      </div>
      <div className="panel">
        <ul className="admin-hint" style={{ display: "grid", gap: 8, marginLeft: 16, listStyle: "disc" }}>
          <li>Tracking a keyword, or re-checking its rank — 1 each</li>
          <li>Seeing who outranks you for a keyword — 1</li>
          <li>Any AI fix (title, meta description, headings, alt text, internal links) — 1</li>
          <li>Keyword opportunities for a page — 2</li>
          <li>A full ranking action plan — 2</li>
        </ul>
        <div className="admin-hint" style={{ marginTop: 12 }}>
          Audits, scores, the opportunities list and your Search Console and Analytics data are free and unlimited.
        </div>
      </div>

      <div className="section-title" style={{ margin: "28px 0 10px" }}>
        Payment history
      </div>
      <div className="panel pages-panel">
        <table className="admin-table">
          <tbody>
            {summary.payments.map((p) => (
              <tr key={p.id}>
                <td className="muted">{formatDate(p.paid_at)}</td>
                <td>
                  {p.kind.replace("_", " ")}
                  {p.credits_granted ? ` · +${p.credits_granted} credits` : ""}
                </td>
                <td className="num">
                  <Money cents={p.amount_cents} />
                </td>
              </tr>
            ))}
            {summary.payments.length === 0 && (
              <tr>
                <td className="empty-state">No payments yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="admin-hint" style={{ marginTop: 14 }}>
        Payments are processed by Dodo Payments, our merchant of record, which also handles sales tax/VAT. See our{" "}
        <a href="/refunds" style={{ color: "var(--accent)" }}>
          refund policy
        </a>
        .
      </div>
    </>
  );
}
