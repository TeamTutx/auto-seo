"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatUsd, limitLabel } from "@/lib/format";
import type { BillingSummary, Pricing, PricingPlan } from "@/lib/types";
import { Money, PlanTag } from "@/components/admin/AdminBits";

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
  const [pricing, setPricing] = useState<Pricing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(checkout === "success");
  const baseline = useRef<{ payments: number; plan: string } | null>(null);

  const load = useCallback(async () => {
    const [s, p] = await Promise.all([api.getBilling(), api.getPricing()]);
    setSummary(s);
    setPricing(p);
    return s;
  }, []);

  useEffect(() => {
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load billing."));
  }, [load]);

  // Coming back from checkout: the plan/credits are granted by a webhook that can
  // land a few seconds after the redirect, so poll briefly instead of showing stale data.
  useEffect(() => {
    if (!waiting) return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      try {
        const s = await load();
        if (baseline.current === null) baseline.current = { payments: s.payments.length, plan: s.plan };
        else if (s.payments.length > baseline.current.payments || s.plan !== baseline.current.plan) {
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

  if (!summary || !pricing) {
    return error ? <div className="form-error">{error}</div> : <div className="loading-state">Loading…</div>;
  }

  const paidPlans = pricing.plans.filter((p) => p.key !== "free");

  return (
    <>
      <div className="topbar">
        <h1 className="page-title">Billing</h1>
      </div>

      {waiting && <div className="note">Payment received — updating your account…</div>}
      {checkout === "cancelled" && <div className="note">Checkout cancelled — you haven’t been charged.</div>}
      {!pricing.billing_enabled && <div className="note">Online payments aren’t switched on yet. Plans and credits will be purchasable here soon.</div>}
      {error && <div className="form-error">{error}</div>}

      <div className="stat-row">
        <div className="stat-cell">
          <div className="stat-label">Current plan</div>
          <div className="stat-value" style={{ textTransform: "capitalize" }}>
            {summary.plan}
          </div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Credits remaining</div>
          <div className="stat-value">{summary.credits_balance}</div>
          <div className="admin-hint">1 credit = one rank check or AI suggestion</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Subscription</div>
          {summary.can_manage_billing ? (
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 6 }} disabled={busy === "portal"} onClick={manage}>
              Manage billing
            </button>
          ) : (
            <div className="admin-hint" style={{ marginTop: 8 }}>
              {summary.has_subscription ? "Active" : "None"}
            </div>
          )}
        </div>
      </div>

      <div className="section-title" style={{ margin: "28px 0 10px" }}>
        Plans
      </div>
      <div className="plan-cards">
        {pricing.plans.map((plan) => (
          <PlanCard key={plan.key} plan={plan} current={summary.plan} summary={summary} busy={busy} onBuy={buy} onManage={manage} />
        ))}
      </div>
      {paidPlans.length === 0 && <div className="admin-hint">No paid plans are available right now.</div>}

      {pricing.credit_packs.length > 0 && (
        <>
          <div className="section-title" style={{ margin: "28px 0 10px" }}>
            Credit packs
          </div>
          <div className="plan-cards">
            {pricing.credit_packs.map((pack) => (
              <div key={pack.key} className="plan-card">
                <div className="plan-card-name">{pack.name}</div>
                <div className="plan-card-price">{formatUsd(pack.price_cents)}</div>
                <ul>
                  <li>{pack.credits} credits, added instantly</li>
                  {pack.description && <li>{pack.description}</li>}
                  <li>Credits don’t expire</li>
                </ul>
                <button className="btn" disabled={!pack.purchasable || busy === pack.key} onClick={() => buy(pack.key)}>
                  {pack.purchasable ? "Buy credits" : "Coming soon"}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

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
                  {p.plan ? <> · <PlanTag plan={p.plan} /></> : null}
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

function PlanCard({
  plan,
  current,
  summary,
  busy,
  onBuy,
  onManage,
}: {
  plan: PricingPlan;
  current: string;
  summary: BillingSummary;
  busy: string | null;
  onBuy: (key: string) => void;
  onManage: () => void;
}) {
  const isCurrent = plan.key === current;
  let cta: React.ReactNode = null;
  if (isCurrent) {
    cta = (
      <button className="btn btn-ghost" disabled>
        Current plan
      </button>
    );
  } else if (plan.key !== "free") {
    if (summary.has_subscription && summary.can_manage_billing) {
      cta = (
        <button className="btn btn-ghost" disabled={busy === "portal"} onClick={onManage}>
          Change in billing portal
        </button>
      );
    } else if (plan.purchasable && plan.product_key) {
      cta = (
        <button className="btn" disabled={busy === plan.product_key} onClick={() => onBuy(plan.product_key!)}>
          Upgrade to {plan.name}
        </button>
      );
    } else {
      cta = (
        <button className="btn btn-ghost" disabled>
          Coming soon
        </button>
      );
    }
  }

  return (
    <div className={`plan-card ${isCurrent ? "current" : ""}`}>
      <div className="plan-card-name">{plan.name}</div>
      <div className="plan-card-price">
        {formatUsd(plan.price_cents)}
        {plan.interval && <small> / {plan.interval}</small>}
      </div>
      <ul>
        <li>{limitLabel(plan.limits.max_sites)} site{plan.limits.max_sites === 1 ? "" : "s"}</li>
        <li>{limitLabel(plan.limits.max_pages_per_site)} pages per site</li>
        <li>{limitLabel(plan.limits.max_keywords_per_page)} tracked keywords per page</li>
        {plan.description && <li>{plan.description}</li>}
      </ul>
      {cta}
    </div>
  );
}
