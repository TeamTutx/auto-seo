"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Site, VerificationMethod } from "@/lib/types";

const METHODS: { value: VerificationMethod; label: string }[] = [
  { value: "dns_txt", label: "DNS TXT record" },
  { value: "meta_tag", label: "Meta tag" },
  { value: "file_upload", label: "File upload" },
];

function instructions(method: VerificationMethod, site: Site): { text: string; code: string } {
  switch (method) {
    case "dns_txt":
      return {
        text: `Add a TXT record at the root of ${site.domain} with this value:`,
        code: site.verification_token,
      };
    case "meta_tag":
      return {
        text: `Add this tag inside the <head> of ${site.domain}'s homepage:`,
        code: `<meta name="signal-site-verification" content="${site.verification_token}">`,
      };
    case "file_upload":
      return {
        text: `Create a file at this exact URL containing only the token below:`,
        code: `https://${site.domain}/signal-verification.txt`,
      };
  }
}

export default function SiteVerification({ site, onVerified }: { site: Site; onVerified: () => void }) {
  const [method, setMethod] = useState<VerificationMethod>(site.verification_method ?? "dns_txt");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<{ verified: boolean; message: string } | null>(null);

  async function handleVerify() {
    setChecking(true);
    setResult(null);
    try {
      const res = await api.verifySite(site.id, method);
      setResult(res);
      if (res.verified) onVerified();
    } catch (err) {
      setResult({ verified: false, message: err instanceof ApiError ? err.message : "Verification check failed." });
    } finally {
      setChecking(false);
    }
  }

  if (site.verified) {
    return (
      <div className="panel" style={{ padding: "14px 18px", display: "flex", alignItems: "center", gap: 10 }}>
        <span className="status-pill good">Verified</span>
        <span style={{ color: "var(--text-muted)", fontSize: 12.5 }}>
          via {METHODS.find((m) => m.value === site.verification_method)?.label ?? site.verification_method}
        </span>
      </div>
    );
  }

  const { text, code } = instructions(method, site);

  return (
    <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h4 style={{ marginBottom: 0 }}>Verify domain ownership</h4>
        <span className="status-pill neutral">Not verified</span>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {METHODS.map((m) => (
          <button
            key={m.value}
            className={method === m.value ? "btn" : "btn-ghost btn"}
            style={{ fontSize: 12, padding: "6px 12px" }}
            onClick={() => {
              setMethod(m.value);
              setResult(null);
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 8 }}>{text}</div>
      <div
        style={{
          background: "var(--bg)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 12px",
          fontFamily: "monospace",
          fontSize: 12,
          wordBreak: "break-all",
          marginBottom: 14,
        }}
      >
        {code}
      </div>

      {result && (
        <div
          className={result.verified ? "" : "form-error"}
          style={
            result.verified
              ? { color: "var(--good)", fontSize: 12.5, marginBottom: 12 }
              : { fontSize: 12.5, marginBottom: 12 }
          }
        >
          {result.message}
        </div>
      )}

      <button className="btn" onClick={handleVerify} disabled={checking}>
        {checking ? "Checking…" : "Check now"}
      </button>
    </div>
  );
}
