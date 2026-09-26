"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Site, WriteTarget, WriteTargetKind } from "@/lib/types";

/** Connect a site to where its content lives, so Signal can set a fix instead of
 *  only writing it out.
 *
 *  Shown only for a verified site: the API refuses otherwise, because attaching
 *  write access to a domain the account has not proven it owns is the one mistake
 *  here that cannot be walked back.
 *
 *  The credential is typed in by the owner and never returned by any endpoint -
 *  this panel shows the state of a connection, never its secret. */
export default function WriteTargetPanel({ site }: { site: Site }) {
  const [target, setTarget] = useState<WriteTarget | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [kind, setKind] = useState<WriteTargetKind>("wordpress");
  const [fields, setFields] = useState({ base_url: "", username: "", repo: "", branch: "", secret: "" });
  const [busy, setBusy] = useState<null | "connect" | "test" | "disconnect">(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getWriteTarget(site.id)
      .then((next) => !cancelled && setTarget(next))
      .catch(() => !cancelled && setTarget(null))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [site.id]);

  if (!site.verified || !loaded) return null;

  function set(key: keyof typeof fields, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  async function connect() {
    setBusy("connect");
    setError(null);
    try {
      const next = await api.connectWriteTarget(site.id, {
        kind,
        secret: fields.secret,
        ...(kind === "wordpress"
          ? { base_url: fields.base_url, username: fields.username }
          : { repo: fields.repo, branch: fields.branch || undefined }),
      });
      setTarget(next);
      // The secret is stored; keeping it in component state serves no purpose.
      setFields({ base_url: "", username: "", repo: "", branch: "", secret: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not connect.");
    } finally {
      setBusy(null);
    }
  }

  async function retest() {
    setBusy("test");
    setError(null);
    try {
      setTarget(await api.testWriteTarget(site.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not test the connection.");
    } finally {
      setBusy(null);
    }
  }

  async function disconnect() {
    if (!confirm(`Disconnect ${target?.label}? Changes Signal already applied stay on your site, and the record of them is kept.`)) return;
    setBusy("disconnect");
    setError(null);
    try {
      await api.disconnectWriteTarget(site.id);
      setTarget(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disconnect.");
    } finally {
      setBusy(null);
    }
  }

  if (target) {
    return (
      <div className="panel" style={{ padding: 18 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <h4 style={{ marginBottom: 0 }}>Applying fixes</h4>
          <span className={`status-pill ${target.status === "ok" ? "good" : "bad"}`}>
            {target.status === "ok" ? "Connected" : "Not working"}
          </span>
        </div>

        <div style={{ fontSize: 13, marginBottom: 4 }}>
          {target.kind === "wordpress" ? "WordPress" : "GitHub"} — <b>{target.label}</b>
        </div>
        {target.status_detail && (
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 12, lineHeight: 1.5 }}>
            {target.status_detail}
          </div>
        )}

        {!target.writes_immediately && (
          <div className="fix-note" style={{ marginBottom: 12 }}>
            Changes open a pull request for you to review. Nothing reaches your site until you merge it.
          </div>
        )}

        <div className="fix-actions">
          <button className="btn btn-ghost fix-btn" onClick={retest} disabled={busy !== null}>
            {busy === "test" ? "Testing…" : "Test again"}
          </button>
          <button className="btn btn-ghost fix-btn" onClick={disconnect} disabled={busy !== null}>
            {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
          </button>
        </div>
        {error && <div className="fix-error">{error}</div>}
      </div>
    );
  }

  const ready =
    fields.secret.trim().length >= 8 &&
    (kind === "wordpress" ? fields.base_url.trim() && fields.username.trim() : fields.repo.trim());

  return (
    <div className="panel" style={{ padding: 18 }}>
      <h4 style={{ marginBottom: 6 }}>Let Signal apply fixes for you</h4>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 14, lineHeight: 1.5 }}>
        Connect where this site&apos;s content lives and Signal can set titles, meta descriptions, alt text and
        the rest itself — with the before and after shown first, and one-click undo. Without a connection it
        still writes every fix for you to paste in.
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {(["wordpress", "github"] as WriteTargetKind[]).map((option) => (
          <button
            key={option}
            className={kind === option ? "btn" : "btn-ghost btn"}
            style={{ fontSize: 12, padding: "6px 12px" }}
            onClick={() => {
              setKind(option);
              setError(null);
            }}
          >
            {option === "wordpress" ? "WordPress" : "GitHub"}
          </button>
        ))}
      </div>

      {kind === "wordpress" ? (
        <>
          <Field label="WordPress address" value={fields.base_url} onChange={(v) => set("base_url", v)} placeholder="https://example.com" />
          <Field label="WordPress username" value={fields.username} onChange={(v) => set("username", v)} placeholder="the login name, not the email" />
          <Field
            label="Application password"
            value={fields.secret}
            onChange={(v) => set("secret", v)}
            placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
            secret
            hint="In WordPress: Users → Profile → Application Passwords. It is separate from your real password and you can revoke it there at any time."
          />
        </>
      ) : (
        <>
          <Field label="Repository" value={fields.repo} onChange={(v) => set("repo", v)} placeholder="owner/name" />
          <Field label="Branch" value={fields.branch} onChange={(v) => set("branch", v)} placeholder="leave blank for the default branch" />
          <Field
            label="Access token"
            value={fields.secret}
            onChange={(v) => set("secret", v)}
            placeholder="github_pat_…"
            secret
            hint="A fine-grained token listing this repository, with Contents: read and write, and Pull requests: read and write. Signal opens a pull request and never pushes to your default branch."
          />
        </>
      )}

      {error && <div className="form-error" style={{ fontSize: 12.5, marginBottom: 12 }}>{error}</div>}

      <button className="btn" onClick={connect} disabled={busy !== null || !ready}>
        {busy === "connect" ? "Checking…" : "Connect and test"}
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  secret,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  secret?: boolean;
  hint?: string;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</label>
      <input
        type={secret ? "password" : "text"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={secret ? "new-password" : "off"}
        spellCheck={false}
        style={{ width: "100%" }}
      />
      {hint && <div style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 4, lineHeight: 1.45 }}>{hint}</div>}
    </div>
  );
}
