"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { API_URL } from "@/lib/site";
import { formatRate, parseUsdToCents } from "@/lib/format";
import type { AdminProduct, ProductVerifyResult } from "@/lib/types";

export default function AdminPricingPage() {
  const [packs, setPacks] = useState<AdminProduct[] | null>(null);
  const [billingEnabled, setBillingEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reordering, setReordering] = useState(false);

  async function load(publish = false) {
    if (publish) await api.revalidatePublicPricing();
    try {
      const [list, pricing] = await Promise.all([api.adminProducts(), api.getPricing()]);
      setPacks(list);
      setBillingEnabled(pricing.billing_enabled);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the packs.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  /** Swap a pack with its neighbour and send the whole order in one call. */
  async function move(index: number, direction: -1 | 1) {
    if (!packs) return;
    const next = [...packs];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setPacks(next);
    setReordering(true);
    try {
      setPacks(await api.adminReorderProducts(next.map((p) => p.id)));
      await api.revalidatePublicPricing();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reorder.");
      await load();
    } finally {
      setReordering(false);
    }
  }

  if (error) return <div className="form-error">{error}</div>;
  if (!packs) return <div className="loading-state">Loading…</div>;

  return (
    <>
      <div className="topbar">
        <h1 className="page-title">Credit packs</h1>
        <Link href="/#plans" target="_blank" className="link-btn">
          View public pricing ↗
        </Link>
      </div>

      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="section-title" style={{ marginBottom: 10 }}>
          Dodo Payments setup{" "}
          {billingEnabled === null ? "" : billingEnabled ? "· API keys configured ✓" : "· not configured yet"}
        </div>
        <ol className="admin-hint" style={{ marginLeft: 18, display: "grid", gap: 6 }}>
          <li>
            In the Dodo dashboard create one <b>one-time</b> product per pack below, priced in USD. Start in{" "}
            <b>test mode</b>.
          </li>
          <li>
            Add a webhook endpoint in Dodo pointing at <span className="admin-code">{API_URL}/webhooks/dodo</span> and
            enable the payment and refund events.
          </li>
          <li>
            Set <span className="admin-code">DODO_API_KEY</span>, <span className="admin-code">DODO_WEBHOOK_KEY</span>{" "}
            (the webhook’s signing secret) and <span className="admin-code">DODO_ENVIRONMENT</span> (
            <code>test_mode</code> or <code>live_mode</code>) on the backend, then redeploy.
          </li>
          <li>
            Paste each Dodo product’s ID (<code>pdt_…</code>) below and press <b>Check against Dodo</b> — the price
            shown to visitors must equal what Dodo charges.
          </li>
        </ol>
        <div className="admin-hint" style={{ marginTop: 10 }}>
          The price here is what visitors <i>see</i>. What they’re <i>charged</i> comes from the Dodo product, so keep
          them equal. Saving updates the public page right away.
        </div>
      </div>

      <div className="section-title" style={{ marginBottom: 10 }}>
        {packs.length} pack{packs.length === 1 ? "" : "s"} · shown on the landing page in this order
      </div>
      <div style={{ display: "grid", gap: 16 }}>
        {packs.map((p, i) => (
          <PackEditor
            key={p.id}
            pack={p}
            onSaved={() => load(true)}
            onMoveUp={i > 0 && !reordering ? () => move(i, -1) : undefined}
            onMoveDown={i < packs.length - 1 && !reordering ? () => move(i, 1) : undefined}
          />
        ))}
        <NewPackForm onCreated={() => load(true)} />
      </div>
    </>
  );
}

function PackEditor({
  pack,
  onSaved,
  onMoveUp,
  onMoveDown,
}: {
  pack: AdminProduct;
  onSaved: () => Promise<void>;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}) {
  const [name, setName] = useState(pack.name);
  const [price, setPrice] = useState((pack.price_cents / 100).toString());
  const [credits, setCredits] = useState(String(pack.credits));
  const [dodoId, setDodoId] = useState(pack.dodo_product_id ?? "");
  const [description, setDescription] = useState(pack.description ?? "");
  const [badge, setBadge] = useState(pack.badge ?? "");
  const [active, setActive] = useState(pack.active);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [verify, setVerify] = useState<ProductVerifyResult | null>(null);

  const cents = parseUsdToCents(price);
  const creditsN = Number(credits);
  const valid = name.trim().length > 0 && cents !== null && Number.isInteger(creditsN) && creditsN > 0;
  const perCredit = cents !== null && creditsN > 0 ? cents / creditsN : null;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!valid || cents === null) return;
    setBusy(true);
    setMsg(null);
    setVerify(null);
    try {
      await api.adminUpdateProduct(pack.id, {
        name: name.trim(),
        price_cents: cents,
        credits: creditsN,
        dodo_product_id: dodoId.trim(),
        description: description.trim(),
        badge: badge.trim(),
        active,
      });
      setMsg({ kind: "ok", text: "Saved." });
      await onSaved();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Could not save." });
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setVerify(null);
    try {
      setVerify(await api.adminVerifyProduct(pack.id));
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Could not check." });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setMsg(null);
    try {
      await api.adminDeleteProduct(pack.id);
      await onSaved();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof ApiError ? err.message : "Could not delete." });
      setConfirmingDelete(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={`panel${active ? "" : " admin-dimmed"}`} onSubmit={save}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <div>
          <b>{pack.name}</b>{" "}
          <span className="admin-hint">
            key: {pack.key} · {pack.sales} sold
          </span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="admin-reorder">
            <button type="button" onClick={onMoveUp} disabled={!onMoveUp} aria-label="Move up">
              ↑
            </button>
            <button type="button" onClick={onMoveDown} disabled={!onMoveDown} aria-label="Move down">
              ↓
            </button>
          </span>
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5, color: "var(--text-muted)" }}>
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Shown on the public page
          </label>
        </div>
      </div>
      <div className="admin-form-row">
        <label>
          Name
          <input className="admin-input" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 150 }} />
        </label>
        <label>
          Price (USD)
          <input className="admin-input" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 100 }} />
        </label>
        <label>
          Credits
          <input
            className="admin-input"
            type="number"
            min={1}
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            style={{ width: 90 }}
          />
        </label>
        <label>
          Badge (optional)
          <input
            className="admin-input"
            placeholder="Best value"
            maxLength={24}
            value={badge}
            onChange={(e) => setBadge(e.target.value)}
            style={{ width: 120 }}
          />
        </label>
        <label className="grow">
          Dodo product ID
          <input className="admin-input mono" placeholder="pdt_…" value={dodoId} onChange={(e) => setDodoId(e.target.value)} />
        </label>
        <label className="grow">
          Short description (optional)
          <input className="admin-input" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
        <button className="btn btn-sm" disabled={!valid || busy}>
          Save
        </button>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={check}>
          Check against Dodo
        </button>
        {perCredit !== null && <span className="admin-hint">{formatRate(perCredit)} per credit</span>}
        {confirmingDelete ? (
          <>
            <span className="admin-hint">Delete this pack for good?</span>
            <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={remove}>
              Yes, delete
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmingDelete(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ marginLeft: "auto" }}
            onClick={() => setConfirmingDelete(true)}
          >
            Delete
          </button>
        )}
        {msg && (
          <span className={msg.kind === "ok" ? "pos" : "neg"} style={{ fontSize: 12.5 }}>
            {msg.text}
          </span>
        )}
        {verify && (
          <span className={verify.ok ? "pos" : "neg"} style={{ fontSize: 12.5 }}>
            {verify.ok ? "✓ " : "✗ "}
            {verify.message}
          </span>
        )}
      </div>
    </form>
  );
}

function NewPackForm({ onCreated }: { onCreated: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [credits, setCredits] = useState("");
  const [badge, setBadge] = useState("");
  const [description, setDescription] = useState("");
  const [dodoId, setDodoId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const cents = parseUsdToCents(price);
  const creditsN = Number(credits);
  const valid = /^[a-z0-9_]{2,40}$/.test(key) && name.trim() && cents !== null && Number.isInteger(creditsN) && creditsN > 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid || cents === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.adminCreateCreditPack({
        key,
        name: name.trim(),
        price_cents: cents,
        credits: creditsN,
        description: description.trim() || null,
        badge: badge.trim() || null,
        dodo_product_id: dodoId.trim() || null,
      });
      setOpen(false);
      setKey("");
      setName("");
      setPrice("");
      setCredits("");
      setBadge("");
      setDescription("");
      setDodoId("");
      await onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the pack.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }} onClick={() => setOpen(true)}>
        + Add a credit pack
      </button>
    );
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="section-title" style={{ marginBottom: 12 }}>
        New credit pack
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="admin-form-row">
        <label>
          Key (lowercase, a-z 0-9 _)
          <input
            className="admin-input mono"
            placeholder="credits_500"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            style={{ width: 150 }}
          />
        </label>
        <label>
          Name
          <input
            className="admin-input"
            placeholder="500 credits"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: 150 }}
          />
        </label>
        <label>
          Price (USD)
          <input className="admin-input" placeholder="29" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 90 }} />
        </label>
        <label>
          Credits
          <input
            className="admin-input"
            type="number"
            min={1}
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            style={{ width: 90 }}
          />
        </label>
        <label>
          Badge (optional)
          <input className="admin-input" placeholder="Best value" maxLength={24} value={badge} onChange={(e) => setBadge(e.target.value)} style={{ width: 120 }} />
        </label>
        <label className="grow">
          Short description (optional)
          <input className="admin-input" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="grow">
          Dodo product ID (optional)
          <input className="admin-input mono" placeholder="pdt_…" value={dodoId} onChange={(e) => setDodoId(e.target.value)} />
        </label>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <button className="btn btn-sm" disabled={!valid || busy}>
          Add pack
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
