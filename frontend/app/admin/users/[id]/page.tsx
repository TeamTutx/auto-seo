"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateTime, parseUsdToCents } from "@/lib/format";
import type { AdminUserDetail } from "@/lib/types";
import { describeAudit, Money } from "@/components/admin/AdminBits";

export default function AdminUserPage() {
  const params = useParams<{ id: string }>();
  const userId = Number(params.id);
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminUser(userId)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load user."));
  }, [userId]);

  // Every action returns the refreshed user, so the whole page stays in sync.
  async function run(action: () => Promise<AdminUserDetail>, success: string): Promise<boolean> {
    setError(null);
    setNotice(null);
    try {
      setDetail(await action());
      setNotice(success);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Try again.");
      return false;
    }
  }

  if (error && !detail) return <div className="form-error">{error}</div>;
  if (!detail) return <div className="loading-state">Loading…</div>;

  return (
    <>
      <div className="detail-header">
        <div>
          <div className="breadcrumb">
            <Link href="/admin/users" className="link-btn">
              Users
            </Link>{" "}
            / #{detail.id}
          </div>
          <div className="detail-title">
            {detail.email}
            {detail.is_admin && <span className="admin-tag">ADMIN</span>}
          </div>
          <div className="admin-hint" style={{ marginTop: 4 }}>
            Joined {formatDate(detail.created_at)} · Google {detail.google_connected ? "connected" : "not connected"}
          </div>
        </div>
      </div>

      {error && <div className="form-error">{error}</div>}
      {notice && <div className="note">{notice}</div>}

      <div className="stat-row stat-row-4">
        <div className="stat-cell">
          <div className="stat-label">Credits left</div>
          <div className="stat-value">{detail.credits_balance}</div>
          <div className="admin-hint">{detail.credits_purchased} bought or granted in total</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Total paid</div>
          <div className="stat-value">
            <Money cents={detail.total_paid_cents} />
          </div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Sites</div>
          <div className="stat-value">{detail.sites.length}</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Last scan</div>
          <div className="stat-value" style={{ fontSize: 17 }}>
            {formatDate(detail.last_active_at)}
          </div>
        </div>
      </div>

      <div className="admin-grid-2 admin-section">
        <CreditsForm onSubmit={(delta, note) => run(() => api.adminAdjustCredits(userId, delta, note), "Credits updated.")} />
        <PaymentForm
          onSubmit={(data) => run(() => api.adminRecordPayment(userId, data), "Payment recorded.")}
        />
      </div>

      <div className="admin-section">
        <div className="section-title">Payments</div>
        <div className="panel pages-panel">
          <div className="admin-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Amount
                  </th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Credits
                  </th>
                  <th>Source</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {detail.payments.map((p) => (
                  <tr key={p.id}>
                    <td className="muted">{formatDateTime(p.paid_at)}</td>
                    <td>
                      {p.kind.replace("_", " ")}
                      {p.product_key ? <span className="muted"> · {p.product_key}</span> : null}
                    </td>
                    <td className="num">
                      <Money cents={p.amount_cents} />
                      {p.tax_cents ? <span className="muted"> (+{(p.tax_cents / 100).toFixed(2)} tax)</span> : null}
                    </td>
                    <td className="num">{p.credits_granted || "—"}</td>
                    <td className="muted">
                      {p.provider}
                      {p.provider_ref ? <span className="mono"> {p.provider_ref}</span> : null}
                    </td>
                    <td className="muted">{p.note ?? ""}</td>
                  </tr>
                ))}
                {detail.payments.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      No payments yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="admin-section">
        <div className="section-title">Credit history</div>
        <div className="panel pages-panel">
          <div className="admin-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Reason</th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Change
                  </th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Balance
                  </th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {detail.ledger.map((t) => (
                  <tr key={t.id}>
                    <td className="muted">{formatDateTime(t.created_at)}</td>
                    <td>{t.reason.replace("_", " ")}</td>
                    <td className={`num ${t.delta < 0 ? "neg" : "pos"}`}>{t.delta > 0 ? `+${t.delta}` : t.delta}</td>
                    <td className="num">{t.balance_after}</td>
                    <td className="muted">
                      {t.ref ? <span className="mono">{t.ref}</span> : null}
                      {t.note ? ` ${t.note}` : ""}
                      {t.actor_email ? ` — by ${t.actor_email}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="admin-grid-2 admin-section">
        <div>
          <div className="section-title">Sites</div>
          <div className="panel pages-panel">
            <table className="admin-table">
              <tbody>
                {detail.sites.map((s) => (
                  <tr key={s.id}>
                    <td>{s.domain}</td>
                    <td className="muted">{s.verified ? "verified" : "unverified"}</td>
                    <td className="num muted">{s.pages_count} pages</td>
                  </tr>
                ))}
                {detail.sites.length === 0 && (
                  <tr>
                    <td className="muted">No sites.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <div className="section-title">Admin activity on this user</div>
          <div className="panel pages-panel">
            <table className="admin-table">
              <tbody>
                {detail.audit.map((a) => (
                  <tr key={a.id}>
                    <td>{describeAudit(a)}</td>
                    <td className="num muted" style={{ whiteSpace: "nowrap" }}>
                      {formatDateTime(a.created_at)}
                    </td>
                  </tr>
                ))}
                {detail.audit.length === 0 && (
                  <tr>
                    <td className="muted">Nothing yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {(detail.dodo_customer_id || detail.dodo_subscription_id) && (
        <div className="admin-hint admin-section">
          Dodo customer <span className="admin-code">{detail.dodo_customer_id ?? "—"}</span> · subscription{" "}
          <span className="admin-code">{detail.dodo_subscription_id ?? "—"}</span>
        </div>
      )}
    </>
  );
}

function CreditsForm({ onSubmit }: { onSubmit: (delta: number, note: string) => Promise<boolean> }) {
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const n = Number(delta);
  const valid = Number.isInteger(n) && n !== 0 && Math.abs(n) <= 10000 && note.trim().length >= 3;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    if (await onSubmit(n, note.trim())) {
      setDelta("");
      setNote("");
    }
    setBusy(false);
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="section-title" style={{ marginBottom: 12 }}>
        Add or remove credits
      </div>
      <div className="admin-form-row">
        <label>
          Amount (negative removes)
          <input
            className="admin-input"
            type="number"
            placeholder="e.g. 25 or -5"
            value={delta}
            onChange={(e) => setDelta(e.target.value)}
          />
        </label>
        <label className="grow">
          Reason (recorded)
          <input className="admin-input" placeholder="e.g. beta tester gift" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="btn" disabled={!valid || busy}>
          Apply
        </button>
      </div>
    </form>
  );
}

function PaymentForm({
  onSubmit,
}: {
  onSubmit: (data: { amount_cents: number; credits: number; note: string }) => Promise<boolean>;
}) {
  const [amount, setAmount] = useState("");
  const [credits, setCredits] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const cents = parseUsdToCents(amount || "0");
  const creditsN = credits === "" ? 0 : Number(credits);
  const valid = cents !== null && Number.isInteger(creditsN) && creditsN >= 0 && note.trim().length >= 3;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid || cents === null) return;
    setBusy(true);
    const ok = await onSubmit({ amount_cents: cents, credits: creditsN, note: note.trim() });
    if (ok) {
      setAmount("");
      setCredits("");
      setNote("");
    }
    setBusy(false);
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="section-title" style={{ marginBottom: 12 }}>
        Record a payment (UPI, bank, invoice…)
      </div>
      <div className="admin-form-row">
        <label>
          Amount (USD)
          <input className="admin-input" placeholder="5.00" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 100 }} />
        </label>
        <label>
          Credits to grant
          <input className="admin-input" type="number" min={0} placeholder="0" value={credits} onChange={(e) => setCredits(e.target.value)} style={{ width: 100 }} />
        </label>
        <label className="grow">
          Note (e.g. UPI ref)
          <input className="admin-input" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="btn" disabled={!valid || busy}>
          Record
        </button>
      </div>
    </form>
  );
}
