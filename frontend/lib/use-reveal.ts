"use client";

import { useEffect } from "react";

/** Reveal elements as they scroll into view.
 *
 *  One IntersectionObserver for the whole page rather than a hook per component:
 *  a marketing page has dozens of these, and dozens of observers is measurably
 *  worse than one. Elements opt in with `data-reveal`.
 *
 *  Three things this is careful about, because a landing page is the one page
 *  that must not feel broken:
 *
 *  - **`prefers-reduced-motion` disables it entirely.** Animation that ignores
 *    that setting is not a flourish, it is a barrier - for some people it causes
 *    actual nausea. Everything is shown immediately instead.
 *  - **Content is visible without JavaScript.** The hidden state is applied by
 *    this hook, not by the stylesheet, so a failed bundle or a crawler that does
 *    not run scripts sees a complete page rather than an empty one. That matters
 *    more than usual here: this is an SEO product.
 *  - **It unobserves after revealing.** These animate once; leaving the observer
 *    attached would keep it working for the life of the page for nothing.
 */
export function useReveal() {
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (nodes.length === 0) return;

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const show = (node: HTMLElement) => node.setAttribute("data-revealed", "true");

    if (reduced?.matches || typeof IntersectionObserver === "undefined") {
      nodes.forEach(show);
      return;
    }

    // Arming happens here, not in CSS, so the page is readable if this never runs.
    nodes.forEach((node) => node.setAttribute("data-reveal-armed", "true"));

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          show(entry.target as HTMLElement);
          observer.unobserve(entry.target);
        }
      },
      // A little before the element arrives, so it has finished moving by the
      // time it is properly in view rather than animating under the reader's eye.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 },
    );
    nodes.forEach((node) => observer.observe(node));

    // Someone can turn the setting on mid-visit; honour it without a reload.
    const onPreferenceChange = (e: MediaQueryListEvent) => {
      if (!e.matches) return;
      observer.disconnect();
      nodes.forEach(show);
    };
    reduced?.addEventListener?.("change", onPreferenceChange);

    return () => {
      observer.disconnect();
      reduced?.removeEventListener?.("change", onPreferenceChange);
    };
  }, []);
}
