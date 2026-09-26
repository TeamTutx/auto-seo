"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProposedChange, WriteTarget } from "@/lib/types";

/** Fields Signal can set, mirroring APPLICABLE_FIELDS in backend/app/models.py.
 *  Everything else is advice: the ones that edit prose stay drafts, because
 *  setting a tag wrongly produces a wrong tag while rewriting a paragraph
 *  wrongly produces a page that no longer says what the business meant. */
export const APPLICABLE_FIELDS = [
  "title_tag",
  "meta_description",
  "canonical_tag",
  "robots_meta_tag",
  "structured_data",
  "image_alt_text",
] as const;

/** No model runs for these, so compiling them is free. Keep in step with
 *  DETERMINISTIC_FIELDS in backend/app/services/changes.py. */
export const FREE_FIELDS = ["canonical_tag", "robots_meta_tag"] as const;

export function isApplicable(field: string): boolean {
  return (APPLICABLE_FIELDS as readonly string[]).includes(field);
}

export function isFree(field: string): boolean {
  return (FREE_FIELDS as readonly string[]).includes(field);
}

/** What each applicable field is called in a sentence, shared so the checklist
 *  and the opportunities list cannot drift apart on wording. */
export const FIX_LABEL: Record<string, string> = {
  title_tag: "title",
  meta_description: "meta description",
  canonical_tag: "canonical tag",
  robots_meta_tag: "robots tag",
  structured_data: "structured data",
  image_alt_text: "alt text",
};

export function fixLabel(field: string): string {
  return FIX_LABEL[field] ?? field.replace(/_/g, " ");
}

/** The write target and the changes for one page, with a reload for after an
 *  apply. `target === null` means the site is manual, which is the default for
 *  every site - `loaded` is what tells that apart from "not fetched yet". */
export function useFixes(pageId: number | null, siteId: number | null) {
  const [target, setTarget] = useState<WriteTarget | null>(null);
  const [changes, setChanges] = useState<ProposedChange[]>([]);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    if (pageId === null || siteId === null) return;
    const [nextTarget, nextChanges] = await Promise.all([
      // A missing connection is the normal case, and a failure to read it should
      // not hide the changes themselves.
      api.getWriteTarget(siteId).catch(() => null),
      api.pageChanges(pageId).catch(() => [] as ProposedChange[]),
    ]);
    setTarget(nextTarget);
    setChanges(nextChanges);
    setLoaded(true);
  }, [pageId, siteId]);

  useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    if (pageId === null || siteId === null) return;
    void (async () => {
      const [nextTarget, nextChanges] = await Promise.all([
        api.getWriteTarget(siteId).catch(() => null),
        api.pageChanges(pageId).catch(() => [] as ProposedChange[]),
      ]);
      if (cancelled) return;
      setTarget(nextTarget);
      setChanges(nextChanges);
      setLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [pageId, siteId]);

  return { target, changes, loaded, reload, setChanges };
}

/** Whether the connected target can actually set this field. A WordPress with no
 *  SEO plugin exposing its REST fields cannot set a meta description, and showing
 *  an Apply button for it would be a button that fails. */
export function canApply(target: WriteTarget | null, field: string): boolean {
  return Boolean(target && target.status === "ok" && target.capabilities.includes(field));
}


/** The same, for a surface that spans a whole site (the opportunities list). One
 *  request for every change on the site rather than one per page. */
export function useSiteFixes(siteId: number | null) {
  const [target, setTarget] = useState<WriteTarget | null>(null);
  const [changes, setChanges] = useState<ProposedChange[]>([]);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    if (siteId === null) return;
    const [nextTarget, nextChanges] = await Promise.all([
      api.getWriteTarget(siteId).catch(() => null),
      api.siteChanges(siteId).catch(() => [] as ProposedChange[]),
    ]);
    setTarget(nextTarget);
    setChanges(nextChanges);
    setLoaded(true);
  }, [siteId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { target, changes, loaded, reload };
}
