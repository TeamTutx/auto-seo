"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Check } from "@/lib/types";

const ICON: Record<Check["status"], { cls: string; glyph: string }> = {
  pass: { cls: "good", glyph: "✓" },
  warning: { cls: "warn", glyph: "!" },
  fail: { cls: "bad", glyph: "✕" },
};

// Check types with an AI suggestion available, and the generator to call.
const SUGGESTABLE: Record<string, { label: string; generate: (pageId: number) => Promise<{ suggestion: string }> }> = {
  meta_description: { label: "meta description", generate: api.suggestMetaDescription },
  title_tag: { label: "title", generate: api.suggestTitleTag },
};

function humanize(checkType: string): string {
  return checkType
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

interface SuggestionState {
  loading: boolean;
  error: string | null;
  text: string | null;
  copied: boolean;
}

export default function CheckList({ checks, pageId }: { checks: Check[]; pageId: number }) {
  const passing = checks.filter((c) => c.status === "pass").length;
  const [suggestions, setSuggestions] = useState<Record<string, SuggestionState>>({});

  async function handleGenerate(checkType: string) {
    const entry = SUGGESTABLE[checkType];
    if (!entry) return;
    setSuggestions((prev) => ({ ...prev, [checkType]: { loading: true, error: null, text: null, copied: false } }));
    try {
      const { suggestion } = await entry.generate(pageId);
      setSuggestions((prev) => ({
        ...prev,
        [checkType]: { loading: false, error: null, text: suggestion, copied: false },
      }));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not generate a suggestion.";
      setSuggestions((prev) => ({ ...prev, [checkType]: { loading: false, error: message, text: null, copied: false } }));
    }
  }

  async function handleCopy(checkType: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setSuggestions((prev) => ({ ...prev, [checkType]: { ...prev[checkType], copied: true } }));
    } catch {
      // clipboard permission denied - the text is still visible to select/copy by hand
    }
  }

  return (
    <div className="checklist-group">
      <div className="checklist-group-title">
        ON-PAGE AUDIT — {passing} of {checks.length} passing
      </div>
      {checks.map((check) => {
        const icon = ICON[check.status];
        const suggestable = SUGGESTABLE[check.check_type];
        const canSuggest = Boolean(suggestable) && check.status !== "pass";
        const suggestion = suggestions[check.check_type];

        return (
          <div className="check-item" key={check.check_type}>
            <div className={`check-icon ${icon.cls}`}>{icon.glyph}</div>
            <div className="check-body">
              <div className="check-title">{humanize(check.check_type)}</div>
              <div className="check-desc">{check.message}</div>
              {check.suggested_fix && <div className="check-fix">{check.suggested_fix}</div>}

              {canSuggest && !suggestion?.text && (
                <div
                  className="check-fix"
                  style={{ cursor: suggestion?.loading ? "default" : "pointer" }}
                  onClick={() => !suggestion?.loading && handleGenerate(check.check_type)}
                >
                  {suggestion?.loading ? "Generating…" : `Generate a ${suggestable.label} suggestion →`}
                </div>
              )}

              {suggestion?.error && (
                <div className="check-fix" style={{ color: "var(--bad)" }}>
                  {suggestion.error}
                </div>
              )}

              {suggestion?.text && (
                <div
                  style={{
                    marginTop: 8,
                    padding: "10px 12px",
                    background: "var(--surface-raised)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    fontSize: 12.5,
                  }}
                >
                  <div style={{ marginBottom: 8 }}>{suggestion.text}</div>
                  <button
                    className="btn-ghost btn"
                    style={{ fontSize: 11.5, padding: "5px 10px" }}
                    onClick={() => handleCopy(check.check_type, suggestion.text!)}
                  >
                    {suggestion.copied ? "Copied!" : "Copy"}
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
