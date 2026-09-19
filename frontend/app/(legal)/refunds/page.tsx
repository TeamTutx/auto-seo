import type { Metadata } from "next";
import { SUPPORT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy — Signal",
  description: "How to cancel a Signal subscription and when we refund plans and credit packs.",
  alternates: { canonical: "/refunds" },
};

export default function RefundsPage() {
  return (
    <article className="legal-body">
      <h1>Refund &amp; Cancellation Policy</h1>
      <p className="updated">Last updated: 19 September 2026</p>

      <p>
        We want you to be happy with Signal. This page explains how to cancel and when we’ll give your money back. Payments are
        processed by Dodo Payments, our merchant of record, and refunds are issued through them.
      </p>

      <h2>Cancelling a subscription</h2>
      <ul>
        <li>Cancel any time in Signal under Billing → Manage billing (this opens your Dodo customer portal).</li>
        <li>You keep your paid plan until the end of the period you’ve already paid for, then your account returns to the Free plan.</li>
        <li>Cancelling stops future renewals. It doesn’t automatically refund the current period.</li>
      </ul>

      <h2>Refunds</h2>
      <ul>
        <li>
          <b>New subscriptions:</b> if you’re not satisfied, email us within <b>7 days</b> of your first payment for a plan and
          we’ll refund it in full.
        </li>
        <li>
          <b>Renewals:</b> if you were charged for a renewal you didn’t intend, email us within <b>3 days</b> of the charge and
          we’ll refund it, provided you cancel the subscription.
        </li>
        <li>
          <b>Credit packs:</b> refundable within <b>7 days</b> of purchase if none of that pack’s credits have been used. Credits
          that have already been used (each triggers a paid third-party search or AI call) can’t be refunded.
        </li>
        <li>
          <b>Free credits</b> have no cash value.
        </li>
        <li>
          <b>Duplicate or mistaken charges</b> and payments made because of a technical error on our side are always refunded in
          full.
        </li>
      </ul>

      <h2>How to request a refund</h2>
      <p>
        Email <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a> from the address on your Signal account, saying which charge
        you’d like refunded. We aim to reply within 2 business days. Approved refunds go back to your original payment method;
        depending on your bank they typically appear within 5–10 business days. When a refund is issued, any credits or plan that
        purchase gave you are removed.
      </p>

      <h2>Disputes</h2>
      <p>
        If something looks wrong on your statement, please contact us first — we can usually fix it faster than a card dispute.
      </p>
    </article>
  );
}
