"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import FixPanel from "@/components/FixPanel";
import { useFixes, fixLabel, isApplicable } from "@/lib/use-fixes";
import { useGeneratedResults } from "@/lib/use-generated-results";
import type { AltTextSuggestion, Check } from "@/lib/types";

const ICON: Record<Check["status"], { cls: string; glyph: string }> = {
  pass: { cls: "good", glyph: "✓" },
  warning: { cls: "warn", glyph: "!" },
  fail: { cls: "bad", glyph: "✕" },
};

type TextSuggestable = {
  label: string;
  kind: "text";
  generate: (pageId: number) => Promise<{ suggestion: string }>;
  /** What the backend files this under in `generatedresult` — the audit's check
   *  names and the stored kinds grew up apart and don't all match. */
  stored: string;
};
type ListSuggestable = {
  label: string;
  kind: "list";
  generate: (pageId: number) => Promise<AltTextSuggestion[]>;
  stored: string;
};

/** Checks whose fix edits the page's *copy*, so Signal drafts it and a person
 *  applies it. The fields Signal can set itself - title, meta description, alt
 *  text, canonical, robots, structured data - are not here: they go through
 *  FixPanel, which shows what is on the page now as well as what would replace
 *  it, and can write it where the site is connected. Keep this split in step with
 *  APPLICABLE_FIELDS in lib/use-fixes.ts and backend/app/models.py. */
const SUGGESTABLE: Record<string, TextSuggestable | ListSuggestable> = {
  heading_structure: { label: "heading outline", kind: "text", generate: api.suggestHeading, stored: "heading" },
  readability: { label: "simpler rewrite", kind: "text", generate: api.suggestReadability, stored: "readability" },
  link_analysis: { label: "internal link", kind: "text", generate: api.suggestInternalLinks, stored: "internal_links" },
};

/** Suggestions an earlier version of Signal charged for, so upgrading does not
 *  hide something already paid for. Keyed by check type, valued by the
 *  `generatedresult` kind it was filed under. */
const PRIOR_SUGGESTION_KIND: Record<string, string> = {
  title_tag: "title_tag",
  meta_description: "meta_description",
};

/** A suggestion the user already paid for under the old flow, if there is one. */
function priorSuggestion(stored: Record<string, unknown> | null, checkType: string): string | null {
  const kind = PRIOR_SUGGESTION_KIND[checkType];
  if (!kind || !stored) return null;
  const payload = stored[kind] as { suggestion?: string } | undefined;
  return payload?.suggestion ?? null;
}

function humanize(checkType: string): string {
  return checkType
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function withArticle(label: string): string {
  return `${/^[aeiou]/i.test(label) ? "an" : "a"} ${label}`;
}

interface SuggestionState {
  loading: boolean;
  error: string | null;
  text: string | null;
  items: AltTextSuggestion[] | null;
  copied: string | null; // which item (src, or "text") was last copied
}

export default function CheckList({
  checks,
  pageId,
  siteId,
}: {
  checks: Check[];
  pageId: number;
  siteId: number;
}) {
  const { target, changes, reload } = useFixes(pageId, siteId);
  const passing = checks.filter((c) => c.status === "pass").length;
  const [suggestions, setSuggestions] = useState<Record<string, SuggestionState>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(checks.map((c) => [c.check_type, c.status !== "pass"]))
  );
  const [bulkAction, setBulkAction] = useState<"collapse" | "expand">("collapse");

  // Restore anything already paid for, so a refresh doesn't cost a credit to
  // see the same suggestion again.
  const stored = useGeneratedResults(pageId);
  useEffect(() => {
    if (!stored) return;
    setSuggestions((current) => {
      const restored: Record<string, SuggestionState> = {};
      for (const [checkType, config] of Object.entries(SUGGESTABLE)) {
        if (current[checkType]) continue;  // don't clobber something just generated
        const payload = stored[config.stored];
        if (payload === undefined) continue;
        restored[checkType] = {
          loading: false,
          error: null,
          text: config.kind === "text" ? ((payload as { suggestion?: string }).suggestion ?? null) : null,
          items: config.kind === "list" ? (payload as AltTextSuggestion[]) : null,
          copied: null,
        };
      }
      return Object.keys(restored).length ? { ...current, ...restored } : current;
    });
  }, [stored]);

  function toggleCard(checkType: string) {
    setExpanded((prev) => ({ ...prev, [checkType]: !prev[checkType] }));
  }

  function handleBulkToggle() {
    const collapsing = bulkAction === "collapse";
    setExpanded(Object.fromEntries(checks.map((c) => [c.check_type, !collapsing])));
    setBulkAction(collapsing ? "expand" : "collapse");
  }

  async function handleGenerate(checkType: string) {
    const entry = SUGGESTABLE[checkType];
    if (!entry) return;
    setSuggestions((prev) => ({
      ...prev,
      [checkType]: { loading: true, error: null, text: null, items: null, copied: null },
    }));
    try {
      if (entry.kind === "list") {
        const items = await entry.generate(pageId);
        setSuggestions((prev) => ({
          ...prev,
          [checkType]: { loading: false, error: null, text: null, items, copied: null },
        }));
      } else {
        const { suggestion } = await entry.generate(pageId);
        setSuggestions((prev) => ({
          ...prev,
          [checkType]: { loading: false, error: null, text: suggestion, items: null, copied: null },
        }));
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not generate a suggestion.";
      setSuggestions((prev) => ({
        ...prev,
        [checkType]: { loading: false, error: message, text: null, items: null, copied: null },
      }));
    }
  }

  async function handleCopy(checkType: string, key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setSuggestions((prev) => ({ ...prev, [checkType]: { ...prev[checkType], copied: key } }));
    } catch {
      // clipboard permission denied - the text is still visible to select/copy by hand
    }
  }

  return (
    <div>
      <div className="section-toolbar">
        <div className="section-title">On-page audit — {passing} of {checks.length} passing</div>
        <button className="toolbar-btn" onClick={handleBulkToggle}>
          {bulkAction === "collapse" ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="card-grid">
        {checks.map((check) => {
          const icon = ICON[check.status];
          const suggestable = SUGGESTABLE[check.check_type];
          // A passing check needs no fix; an applicable one gets the change flow,
          // and only what is left falls back to a prose suggestion.
          const applicable = isApplicable(check.check_type) && check.status !== "pass";
          const canSuggest = Boolean(suggestable) && check.status !== "pass";
          const suggestion = suggestions[check.check_type];
          const hasResult = Boolean(suggestion?.text) || Boolean(suggestion?.items);
          const isOpen = Boolean(expanded[check.check_type]);

          return (
            <div className={`check-card${isOpen ? " open" : ""}`} key={check.check_type}>
              <button className="check-head" onClick={() => toggleCard(check.check_type)}>
                <div className={`check-icon ${icon.cls}`}>{icon.glyph}</div>
                <div className="check-head-body">
                  <div className="check-title">{humanize(check.check_type)}</div>
                  <div className="check-summary">{check.message}</div>
                </div>
                <div className="chevron">▾</div>
              </button>

              {isOpen && (
                <div className="check-card-content">
                  {check.suggested_fix && <div className="check-fix">{check.suggested_fix}</div>}

                  {applicable && (
                    <FixPanel
                      pageId={pageId}
                      field={check.check_type}
                      label={fixLabel(check.check_type)}
                      target={target}
                      changes={changes.filter((c) => c.field === check.check_type)}
                      onChanged={reload}
                      priorSuggestion={priorSuggestion(stored, check.check_type)}
                    />
                  )}

                  {canSuggest && !hasResult && (
                    <div
                      className="check-fix"
                      style={{ cursor: suggestion?.loading ? "default" : "pointer" }}
                      onClick={() => !suggestion?.loading && handleGenerate(check.check_type)}
                    >
                      {suggestion?.loading ? "Generating…" : `Generate ${withArticle(suggestable.label)} suggestion →`}
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
                      <div style={{ marginBottom: 8, whiteSpace: "pre-wrap" }}>{suggestion.text}</div>
                      <button
                        className="btn-ghost btn"
                        style={{ fontSize: 11.5, padding: "5px 10px" }}
                        onClick={() => handleCopy(check.check_type, "text", suggestion.text!)}
                      >
                        {suggestion.copied === "text" ? "Copied!" : "Copy"}
                      </button>
                    </div>
                  )}

                  {suggestion?.items && (
                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                      {suggestion.items.length === 0 ? (
                        <div className="check-fix">No images are missing alt text.</div>
                      ) : (
                        suggestion.items.map((item) => (
                          <div
                            key={item.src}
                            style={{
                              padding: "10px 12px",
                              background: "var(--surface-raised)",
                              border: "1px solid var(--border)",
                              borderRadius: 6,
                              fontSize: 12.5,
                            }}
                          >
                            <div style={{ color: "var(--text-muted)", fontSize: 11, marginBottom: 4, wordBreak: "break-all" }}>
                              {item.src}
                            </div>
                            <div style={{ marginBottom: 8 }}>{item.suggested_alt}</div>
                            <button
                              className="btn-ghost btn"
                              style={{ fontSize: 11.5, padding: "5px 10px" }}
                              onClick={() => handleCopy(check.check_type, item.src, item.suggested_alt)}
                            >
                              {suggestion.copied === item.src ? "Copied!" : "Copy"}
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
