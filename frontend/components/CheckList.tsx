import type { Check } from "@/lib/types";

const ICON: Record<Check["status"], { cls: string; glyph: string }> = {
  pass: { cls: "good", glyph: "✓" },
  warning: { cls: "warn", glyph: "!" },
  fail: { cls: "bad", glyph: "✕" },
};

function humanize(checkType: string): string {
  return checkType
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export default function CheckList({ checks }: { checks: Check[] }) {
  const passing = checks.filter((c) => c.status === "pass").length;

  return (
    <div className="checklist-group">
      <div className="checklist-group-title">
        ON-PAGE AUDIT — {passing} of {checks.length} passing
      </div>
      {checks.map((check) => {
        const icon = ICON[check.status];
        return (
          <div className="check-item" key={check.check_type}>
            <div className={`check-icon ${icon.cls}`}>{icon.glyph}</div>
            <div className="check-body">
              <div className="check-title">{humanize(check.check_type)}</div>
              <div className="check-desc">{check.message}</div>
              {check.suggested_fix && <div className="check-fix">{check.suggested_fix}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
