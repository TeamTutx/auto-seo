import type { Metadata } from "next";
import { SUPPORT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Refund & Cancellation Policy — Signal",
  description: "When Signal refunds a credit pack, and how to ask for one.",
  alternates: { canonical: "/refunds" },
};

export default function RefundsPage() {
  return (
    <article className="legal-body">
      <h1>Refund &amp; Cancellation Policy</h1>
      <p className="updated">Last updated: 19 September 2026</p>

      <p>
        We want you to be happy with Signal. This page explains when we’ll give your money back. Payments are processed by Dodo
        Payments, our merchant of record, and refunds are issued through them.
      </p>

      <h2>There is nothing to cancel</h2>
      <p>
        Signal has no subscription. Using the app is free, and you buy credits one pack at a time when you want them. Nothing
        renews, nothing is charged automatically, and credits you’ve bought don’t expire. If you simply stop buying credits,
        you’re not billed again.
      </p>

      <h2>Refunds</h2>
      <ul>
        <li>
          <b>Unused credit packs:</b> refundable in full within <b>7 days</b> of purchase, as long as none of that pack’s credits
          have been used.
        </li>
        <li>
          <b>Partly used packs:</b> email us within <b>7 days</b> and we’ll refund the unused portion at the price you paid per
          credit, at our discretion. Credits you’ve already spent can’t be refunded — each one triggers a paid third-party search
          or AI call that we’ve been charged for.
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
        depending on your bank they typically appear within 5–10 business days. When a pack is refunded in full, the credits it
        gave you are removed from your balance.
      </p>

      <h2>Disputes</h2>
      <p>
        If something looks wrong on your statement, please contact us first — we can usually fix it faster than a card dispute.
      </p>
    </article>
  );
}
