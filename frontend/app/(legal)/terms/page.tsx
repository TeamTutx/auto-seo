import type { Metadata } from "next";
import { SUPPORT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Terms of Service — Signal",
  description: "The terms that apply when you use Signal, including plans, credits, payments and acceptable use.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <article className="legal-body">
      <h1>Terms of Service</h1>
      <p className="updated">Last updated: 19 September 2026</p>

      <p>
        These terms apply to your use of Signal at signal-seo.in (the “Service”), operated by Signal SEO (“Signal”, “we”, “us”).
        By creating an account or using the Service you agree to them. If you don’t agree, please don’t use the Service.
      </p>

      <h2>1. What Signal does</h2>
      <p>
        Signal runs on-page SEO audits on web pages you add, tracks keyword rankings, generates AI-assisted suggestions, and — if
        you connect your Google account — shows Google Search Console and Google Analytics data for your own sites. Signal
        reports and suggests; it does not change your websites for you.
      </p>

      <h2>2. Your account</h2>
      <ul>
        <li>You must be at least 18 and able to enter a binding contract.</li>
        <li>Give us a valid email address and keep your password secure. You’re responsible for activity on your account.</li>
        <li>One person, one free account. Creating multiple free accounts to collect free credits is not allowed.</li>
      </ul>

      <h2>3. Plans, credits and payments</h2>
      <ul>
        <li>
          <b>Free plan.</b> Includes limited sites, pages and tracked keywords and a small one-time allowance of credits. Free
          credits have no cash value and don’t renew.
        </li>
        <li>
          <b>Paid plans (Pro, Agency)</b> are monthly subscriptions that renew automatically until you cancel. The current price,
          billing interval and plan limits are shown on our <a href="/#plans">pricing section</a> and on the Billing page in your
          account.
        </li>
        <li>
          <b>Credits.</b> One credit pays for one keyword rank check or one AI suggestion (some actions use two). You can buy
          additional credit packs as one-time purchases. Credits don’t expire while your account is active, aren’t transferable
          and aren’t redeemable for cash.
        </li>
        <li>
          <b>Prices and taxes.</b> Prices are in US dollars. Our payments are processed by Dodo Payments, our merchant of record,
          which collects any applicable sales tax, VAT or GST at checkout and issues your receipt. We may change prices; a change
          never affects a billing period you’ve already paid for, and we’ll tell you before it applies to your next renewal.
        </li>
        <li>
          <b>Cancelling.</b> Cancel any time from Billing → Manage billing. You keep the plan until the end of the period you’ve
          paid for; it then returns to Free. Refunds are covered in our <a href="/refunds">Refund Policy</a>.
        </li>
      </ul>

      <h2>4. Acceptable use</h2>
      <ul>
        <li>Only add sites and pages you own or are authorised to analyse.</li>
        <li>Don’t use the Service to break the law, attack or overload other sites, or attempt to bypass limits, credits or billing.</li>
        <li>Don’t resell or republish the Service’s data as a competing product.</li>
        <li>We may suspend accounts that abuse the Service, with notice where we reasonably can.</li>
      </ul>

      <h2>5. Google data</h2>
      <p>
        If you connect Google, we request read-only access to Search Console and Analytics data and use it only to show you that
        data inside Signal. How we handle it is described in our <a href="/privacy">Privacy Policy</a>. You can disconnect at any
        time in Settings or from your Google Account.
      </p>

      <h2>6. Third-party services</h2>
      <p>
        The Service relies on providers including Google, SerpApi (search result data), OpenAI (AI suggestions), our hosting
        providers and Dodo Payments. Their availability and terms are outside our control, and features that depend on them may
        occasionally be unavailable.
      </p>

      <h2>7. Accuracy and no guarantees</h2>
      <p>
        SEO results depend on many factors outside our control. Audit findings, rank positions and AI-generated suggestions are
        provided to inform your decisions; we don’t guarantee any ranking, traffic or business outcome, and AI suggestions can be
        wrong — please review them before applying them.
      </p>

      <h2>8. Availability and changes</h2>
      <p>
        We work to keep Signal available but don’t promise uninterrupted service. We may add, change or remove features. We may
        update these terms; if a change is material we’ll notify you by email or in the app, and continued use after that means you
        accept it.
      </p>

      <h2>9. Termination</h2>
      <p>
        You can stop using the Service and ask us to delete your account at any time (email us). We may suspend or end your access
        if you breach these terms. On termination your right to use the Service ends; sections that by their nature should survive
        (such as liability limits) do.
      </p>

      <h2>10. Disclaimers and liability</h2>
      <p>
        The Service is provided “as is” without warranties of any kind, to the extent permitted by law. To the extent permitted by
        law, our total liability to you for any claim relating to the Service is limited to the amount you paid us in the 12 months
        before the claim, and we’re not liable for indirect or consequential losses such as lost profits or lost data.
      </p>

      <h2>11. Governing law</h2>
      <p>These terms are governed by the laws of India, and the courts of India have jurisdiction, unless mandatory consumer law where you live says otherwise.</p>

      <h2>12. Contact</h2>
      <p>
        Questions about these terms: <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
      </p>
    </article>
  );
}
