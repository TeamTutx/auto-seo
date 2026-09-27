"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { SearchLocation } from "@/lib/types";

/** Manage the countries Signal can measure a search in.
 *
 *  This list used to be an array in the frontend bundle, so adding a market was
 *  a code change and a deploy. A country is retired rather than deleted: rank
 *  and visibility readings store its code, and a reading whose country cannot be
 *  named is worse than one from a market no longer offered. The code itself is
 *  not editable for the same reason — changing it would relabel history as
 *  having been measured somewhere else. */
function LocationsContent() {
  const [rows, setRows] = useState<SearchLocation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setRows(await api.adminLocations());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the list.");
      setRows([]);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    const codeN = Number(code);
    if (!Number.isInteger(codeN) || codeN <= 0 || label.trim().length < 2) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.adminCreateLocation({ code: codeN, label: label.trim(), sort_order: (rows?.length ?? 0) * 10 + 10 });
      setCode("");
      setLabel("");
      setNotice(`${label.trim()} is now selectable.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add it.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(row: SearchLocation) {
    setError(null);
    setNotice(null);
    try {
      await api.adminUpdateLocation(row.id, { active: !row.active });
      setNotice(row.active ? `${row.label} retired — existing readings keep their label.` : `${row.label} is selectable again.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change it.");
    }
  }

  if (rows === null) return <div className="loading-state">Loading…</div>;

  return (
    <>
      <div className="section-title">Countries</div>
      <div className="admin-hint" style={{ marginBottom: 16, maxWidth: 640, lineHeight: 1.55 }}>
        Where a keyword&apos;s rank and a site&apos;s visibility are measured. The code is the search
        provider&apos;s location id — SerpApi and DataForSEO both use Google&apos;s numbering, so 2356 is
        India and 2840 the United States. A wrong code measures a real country, just not the one on the
        label.
      </div>

      {error && <div className="form-error" style={{ marginBottom: 12 }}>{error}</div>}
      {notice && <div className="admin-hint" style={{ marginBottom: 12, color: "var(--good)" }}>{notice}</div>}

      <form className="panel admin-section" onSubmit={add} style={{ padding: 16 }}>
        <div className="admin-form-row">
          <label>
            Location code
            <input
              className="admin-input"
              type="number"
              placeholder="e.g. 2276"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <label className="grow">
            Country name
            <input
              className="admin-input admin-input-full"
              placeholder="e.g. Germany"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>
          <button className="btn" disabled={busy || !code || label.trim().length < 2}>
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </form>

      <div className="panel pages-panel">
        <div className="admin-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Country</th>
                <th className="num">Code</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.label}</td>
                  <td className="num admin-code">{row.code}</td>
                  <td>
                    <span className={`status-pill ${row.active ? "good" : "neutral"}`}>
                      {row.active ? "Selectable" : "Retired"}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-ghost" style={{ fontSize: 11.5, padding: "4px 9px" }} onClick={() => toggle(row)}>
                      {row.active ? "Retire" : "Restore"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default function LocationsPage() {
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <LocationsContent />
    </Suspense>
  );
}
