"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { canApply, isFree } from "@/lib/use-fixes";
import type { ProposedChange, WriteTarget } from "@/lib/types";

/** One field's fix: write it, look at exactly what would change, then apply it
 *  or copy it in.
 *
 *  Used from the audit checklist, the opportunities list and the visibility page,
 *  so all three show the same thing - the before and the after, never just the
 *  after. "Add a meta description" is a diagnosis; "this one, replacing nothing"
 *  is a change someone can approve.
 *
 *  The Apply button only exists when the connected target can genuinely write
 *  this field. Otherwise the same change is shown with a copy button, which is
 *  what every unconnected site gets and is not a degraded mode. */
export default function FixPanel({
  pageId,
  field,
  label,
  target,
  changes,
  onChanged,
  priorSuggestion,
}: {
  pageId: number;
  field: string;
  /** Human name for this field, e.g. "meta description". */
  label: string;
  target: WriteTarget | null;
  /** Every change for this field. Alt text has one per image; the rest have one. */
  changes: ProposedChange[];
  onChanged: () => void | Promise<void>;
  /** A suggestion an earlier version of Signal already charged for, shown so that
   *  upgrading does not silently hide something the user paid for. */
  priorSuggestion?: string | null;
}) {
  const [busy, setBusy] = useState<null | "compile" | "apply" | "revert">(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const proposed = changes.filter((c) => c.status === "proposed" || c.status === "failed");
  const applied = changes.filter((c) => c.status === "applied");
  const writable = canApply(target, field);
  const free = isFree(field);

  async function run(kind: "compile" | "apply" | "revert", action: () => Promise<unknown>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not ${kind} the ${label}.`);
    } finally {
      setBusy(null);
    }
  }

  async function copy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
    } catch {
      // Clipboard permission denied; the text is on screen to select by hand.
    }
  }

  return (
    <div className="fix">
      {applied.length > 0 && (
        <div className="fix-applied">
          <div className="fix-applied-head">
            <span className="fix-badge">
              {applied[0].target_kind === "github" ? "Pull request opened" : "Applied"}
            </span>
            <span className="fix-applied-detail">
              {applied[0].receipt_detail || `Signal set the ${label} on your site.`}
            </span>
          </div>
          {applied[0].receipt_url && (
            <a className="fix-link" href={applied[0].receipt_url} target="_blank" rel="noreferrer">
              {applied[0].target_kind === "github" ? "Review the pull request" : "Open it on your site"} →
            </a>
          )}
          {applied.map((change) => (
            <Diff key={change.id} change={change} />
          ))}
          <div className="fix-actions">
            <button
              className="btn btn-ghost fix-btn"
              disabled={busy !== null}
              onClick={() => run("revert", () => api.revertChanges(pageId, applied.map((c) => c.id)))}
            >
              {busy === "revert" ? "Undoing…" : "Undo"}
            </button>
            <span className="fix-note">
              {applied[0].target_kind === "github"
                ? "Undo closes the pull request, or reverses it if it is already merged."
                : "Undo puts back exactly what was there before."}
            </span>
          </div>
        </div>
      )}

      {proposed.length > 0 && (
        <div className="fix-proposed">
          {proposed.map((change) => (
            <Diff
              key={change.id}
              change={change}
              onCopy={() => copy(String(change.id), change.after)}
              copied={copied === String(change.id)}
            />
          ))}
          <div className="fix-actions">
            {writable ? (
              <button
                className="btn fix-btn"
                disabled={busy !== null}
                onClick={() => run("apply", () => api.applyChanges(pageId, proposed.map((c) => c.id)))}
              >
                {busy === "apply"
                  ? "Applying…"
                  : target?.writes_immediately
                    ? `Apply to ${target.label}`
                    : `Open a pull request on ${target?.label}`}
              </button>
            ) : (
              <span className="fix-note">{whyNotWritable(target, field, label)}</span>
            )}
            <button
              className="btn btn-ghost fix-btn"
              disabled={busy !== null}
              onClick={() => run("compile", () => api.compileChange(pageId, field))}
            >
              {busy === "compile" ? "Rewriting…" : "Rewrite it"}
            </button>
            <button
              className="btn btn-ghost fix-btn"
              disabled={busy !== null}
              onClick={() =>
                run("compile", async () => {
                  for (const change of proposed) await api.discardChange(pageId, change.id);
                })
              }
            >
              Discard
            </button>
          </div>
        </div>
      )}

      {proposed.length === 0 && applied.length === 0 && (
        <>
          {priorSuggestion && (
            <div className="fix-prior">
              <div className="fix-prior-label">An earlier suggestion you already paid for</div>
              <div className="fix-value">{priorSuggestion}</div>
              <button className="btn btn-ghost fix-btn" onClick={() => copy("prior", priorSuggestion)}>
                {copied === "prior" ? "Copied" : "Copy"}
              </button>
            </div>
          )}
          <button
            className="fix-cta"
            disabled={busy !== null}
            onClick={() => run("compile", () => api.compileChange(pageId, field))}
          >
            {busy === "compile" ? "Working…" : `Write the ${label} fix`}
            <span className="fix-cost">{free ? "free" : "1 credit"}</span>
          </button>
        </>
      )}

      {error && <div className="fix-error">{error}</div>}
    </div>
  );
}

function Diff({
  change,
  onCopy,
  copied,
}: {
  change: ProposedChange;
  onCopy?: () => void;
  copied?: boolean;
}) {
  return (
    <div className="fix-diff">
      {change.subject && <div className="fix-subject">{change.subject}</div>}
      <div className="fix-row">
        <span className="fix-row-label">Now</span>
        <span className={`fix-value${change.before ? "" : " fix-value-empty"}`}>
          {change.before || "nothing — this is missing from the page"}
        </span>
      </div>
      <div className="fix-row">
        <span className="fix-row-label fix-row-label-new">New</span>
        <span className="fix-value fix-value-new">{change.after}</span>
      </div>
      {change.warning && <div className="fix-warning">{change.warning} Try “Rewrite it”.</div>}
      {change.error && <div className="fix-error">{change.error}</div>}
      {onCopy && (
        <button className="btn btn-ghost fix-btn" onClick={onCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  );
}

/** Why there is no Apply button, in a sentence that says what to do instead. */
function whyNotWritable(target: WriteTarget | null, field: string, label: string): string {
  if (!target) {
    return `Copy this in, or connect WordPress or GitHub in site settings and Signal can set the ${label} for you.`;
  }
  if (target.status !== "ok") {
    return `The connection to ${target.label} is not working, so copy this in for now. Site settings can retest it.`;
  }
  return `${target.label} does not expose the ${label} for writing, so copy this one in.`;
}
