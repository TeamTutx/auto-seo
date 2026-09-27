"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { LIMITS, STEPS } from "./content";

/** The end-to-end tour. Client-side only for the CTAs, which branch on whether
 *  someone is signed in - the same rule the landing page follows. */
export default function HowItWorksPage() {
  const { user } = useAuth();
  const primaryHref = user ? "/dashboard" : "/login?mode=register";
  const primaryLabel = user ? "Go to dashboard" : "Start free";

  return (
    <div className="lp-page">
      <nav className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" className="brand">
            <span className="brand-mark" />
            <span className="brand-name">Signal</span>
          </Link>
          <div className="lp-nav-links">
            <Link href="/#features">Features</Link>
            <Link href="/how-it-works">How it works</Link>
            <Link href="/#plans">Pricing</Link>
            <Link href="/auto-seo-tools">Auto SEO</Link>
          </div>
          <div className="lp-nav-actions">
            {user ? (
              <Link className="btn" href="/dashboard">Go to dashboard</Link>
            ) : (
              <>
                <Link className="btn btn-ghost" href="/login">Sign in</Link>
                <Link className="btn" href="/login?mode=register">Start free</Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <main className="lp-doc">
        <header className="lp-doc-head">
          <h1>How Signal works, end to end</h1>
          <p className="lp-doc-lead">
            From a bare domain to a change made on your live site, in nine steps. Every screenshot below is
            Signal&apos;s actual interface — not a mock-up — showing real audit output for a demo site we
            built to have problems worth fixing.
          </p>
          <p className="lp-doc-lead-note">
            The demo runs on a local address, which is why you will see a{" "}
            <span className="lp-mono">localhost</span> domain in a couple of shots. Everything else is exactly
            what you get.
          </p>
        </header>

        <nav className="tour-contents" aria-label="Steps">
          {STEPS.map((step) => (
            <a key={step.id} href={`#${step.id}`}>
              <span className="tour-contents-num">{step.n}</span>
              {step.title}
            </a>
          ))}
        </nav>

        {STEPS.map((step) => (
          <section className="lp-doc-section tour-step" id={step.id} key={step.id}>
            <div className="tour-step-head">
              <span className="tour-step-num">{step.n}</span>
              <h2>{step.title}</h2>
            </div>
            <p>{step.body}</p>
            {step.note && <p className="lp-doc-note">{step.note}</p>}
            <figure className={`tour-figure${step.narrow ? " narrow" : ""}`}>
              {/* Plain <img>, deliberately. next/image needs an optimiser, and
                  under output: "export" there is no server to run one - it would
                  need unoptimized: true and then do nothing but add JS. Width and
                  height are set so the layout does not shift, and every shot below
                  the first is lazy so opening the page is not a 1MB download. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={step.image.src}
                alt={step.image.alt}
                width={step.image.width}
                height={step.image.height}
                loading={step.n === 1 ? "eager" : "lazy"}
                decoding="async"
              />
            </figure>
          </section>
        ))}

        <section className="lp-doc-section" id="limits">
          <h2>Where Signal stops</h2>
          <p>
            The useful question about any tool in this category is where it stops. Signal&apos;s answer,
            without hedging:
          </p>
          <ul className="lp-doc-list lp-doc-list-cross">
            {LIMITS.map((limit) => (
              <li key={limit.title}>
                <b>{limit.title}.</b> {limit.body}
              </li>
            ))}
          </ul>
        </section>

        <section className="lp-doc-section tour-cta">
          <h2>Try it on your own site</h2>
          <p>
            New accounts start with free credits, and the parts that cost nothing — crawling, auditing,
            scoring, index checks — stay free however much you use them.
          </p>
          <div className="tour-cta-actions">
            <Link className="btn" href={primaryHref}>{primaryLabel}</Link>
            <Link className="btn btn-ghost" href="/auto-seo-tools">What auto SEO tools actually do</Link>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <span>© {new Date().getFullYear()} Signal</span>
          <div className="lp-footer-links">
            <Link href="/terms">Terms</Link>
            <Link href="/privacy">Privacy</Link>
            <Link href="/refunds">Refunds</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
