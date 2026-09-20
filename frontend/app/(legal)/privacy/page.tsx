import type { Metadata } from "next";
import { SUPPORT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy Policy — Signal",
  description: "What data Signal collects, how it uses Google data, who it shares it with, and how to delete it.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <article className="legal-body">
      <h1>Privacy Policy</h1>
      <p className="updated">Last updated: 19 September 2026</p>

      <p>
        This policy explains what personal data Signal SEO (“Signal”, “we”) collects through signal-seo.in and how we use it. We
        keep it as short and specific as we can.
      </p>

      <h2>1. What we collect</h2>
      <ul>
        <li>
          <b>Account data:</b> your email address. If you sign in with Google we receive your email address, name and
          profile picture URL from your Google profile, and store the email address; we never see your Google password. If
          you sign in with a password instead, we store it hashed, never in plain text.
        </li>
        <li>
          <b>Data you add:</b> the sites, pages and target keywords you enter, and the audit results, rank checks and suggestions
          Signal produces for them.
        </li>
        <li>
          <b>Usage and billing records:</b> your plan, credit balance and credit history, and payment records (amount, date, plan
          or credit pack). We do <b>not</b> receive or store your card number — payments are handled by Dodo Payments.
        </li>
        <li>
          <b>Google data (only if you connect Google):</b> from Search Console — search queries, clicks, impressions, average
          position and indexing status for your properties; from Google Analytics — traffic metrics such as sessions and pageviews
          for your properties; and your Google account’s email. Access is read-only.
        </li>
        <li>
          <b>Website analytics:</b> we use Google Analytics on our public website to understand visits (pages viewed, approximate
          location, device). It uses cookies.
        </li>
        <li>
          <b>Technical logs:</b> IP address and request details kept by our hosting providers for security and reliability.
        </li>
      </ul>

      <h2>2. How we use it</h2>
      <p>
        To provide and secure the Service, run audits and rank checks, show you your Google data, process payments and credits,
        answer support requests, and improve Signal. We don’t sell your personal data and we don’t use it for advertising.
      </p>

      <h2>3. Google user data (Limited Use)</h2>
      <p>
        Signal’s use and transfer to any other app of information received from Google APIs will adhere to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. Specifically: we use Google data only to display it to you inside Signal; we
        don’t transfer it to others except as needed to provide the Service, comply with law, or with your consent; we don’t use
        it for advertising; and no human reads it except with your permission, for security, or to comply with law. Your Google
        access and refresh tokens are stored encrypted. You can disconnect in Settings, or revoke access at{" "}
        <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
          myaccount.google.com/permissions
        </a>
        .
      </p>

      <h2>4. Who we share data with</h2>
      <p>These providers process data on our behalf, only as needed to run the Service:</p>
      <ul>
        <li>
          <b>Hosting</b> — Render (website, application and database; database in Singapore).
        </li>
        <li>
          <b>SerpApi</b> — receives the keyword, location and domain of a rank check you run.
        </li>
        <li>
          <b>OpenAI</b> — receives excerpts of a page’s content when you request an AI suggestion.
        </li>
        <li>
          <b>Dodo Payments</b> — our merchant of record; it collects your payment details and billing information directly and
          shares back payment status and a customer reference.
        </li>
        <li>
          <b>Google</b> — Analytics on our public site, and the Search Console / Analytics APIs if you connect your account.
        </li>
      </ul>
      <p>We may also disclose information if required by law.</p>

      <h2>5. Where data is stored</h2>
      <p>
        Data is stored on servers in Singapore and other locations used by the providers above. Signal is operated from India, so
        your data may be transferred to and processed in countries other than where you live.
      </p>

      <h2>6. How long we keep it</h2>
      <p>
        We keep your data while your account is open. When you ask us to delete your account we delete your account data and
        connected Google tokens; we retain payment records for as long as tax and accounting rules require.
      </p>

      <h2>7. Your choices and rights</h2>
      <ul>
        <li>Disconnect Google at any time in Settings.</li>
        <li>
          Ask us to access, correct or delete your data, or to delete your account, by emailing{" "}
          <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>. We’ll respond within a reasonable time.
        </li>
        <li>
          Depending on where you live (for example under India’s Digital Personal Data Protection Act, 2023, or the GDPR) you may
          have additional rights, including to complain to a data protection authority.
        </li>
        <li>You can block or clear cookies in your browser; the app’s core features don’t depend on analytics cookies.</li>
      </ul>

      <h2>8. Security</h2>
      <p>
        Passwords are hashed, Google tokens are encrypted at rest, traffic is served over HTTPS, and access to our admin tools is
        restricted. No system is perfectly secure; if a breach affecting you occurs we’ll notify you as the law requires.
      </p>

      <h2>9. Children</h2>
      <p>Signal is not intended for anyone under 18 and we don’t knowingly collect their data.</p>

      <h2>10. Changes</h2>
      <p>If we make a material change to this policy we’ll update the date above and notify you by email or in the app.</p>

      <h2>11. Contact</h2>
      <p>
        <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
      </p>
    </article>
  );
}
