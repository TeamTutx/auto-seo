import Link from "next/link";
import { SUPPORT_EMAIL } from "@/lib/site";

// Shared shell for /terms, /privacy and /refunds (a route group - it doesn't
// appear in the URLs). These pages are public and required by our payment
// provider (Dodo Payments) before it approves the account.
export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="legal-shell">
      <header className="legal-nav">
        <div className="legal-nav-inner">
          <Link href="/" className="brand" style={{ padding: 0, textDecoration: "none" }}>
            <div className="brand-mark" />
            <div className="brand-name">Signal</div>
          </Link>
          <Link href="/" className="back">
            ← Back to home
          </Link>
        </div>
      </header>
      {children}
      <footer className="legal-footer">
        <Link href="/terms">Terms</Link>
        <Link href="/privacy">Privacy</Link>
        <Link href="/refunds">Refunds</Link>
        <a href={`mailto:${SUPPORT_EMAIL}`}>Contact</a>
      </footer>
    </div>
  );
}
