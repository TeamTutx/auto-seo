"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatDateTime, formatUsd } from "@/lib/format";
import type { AdminStats } from "@/lib/types";
import { describeAudit, Money } from "@/components/admin/AdminBits";

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminStats()
      .then(setStats)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load stats."));
  }, []);

  if (error) return <div className="form-error">{error}</div>;
  if (!stats) return <div className="loading-state">Loading…</div>;

  return (
    <>
      <div className="topbar">
        <h1 className="page-title">Overview</h1>
      </div>

      <div className="stat-row stat-row-4">
        <div className="stat-cell">
          <div className="stat-label">Users</div>
          <div className="stat-value">{stats.total_users}</div>
          <div className="admin-hint">
            +{stats.signups_7d} this week · +{stats.signups_30d} this month
          </div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Revenue, last 30 days</div>
          <div className="stat-value">{formatUsd(stats.revenue_30d_cents)}</div>
          <div className="admin-hint">{formatUsd(stats.revenue_all_cents)} all time (gross)</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Paying users</div>
          <div className="stat-value">{stats.paying_users}</div>
          <div className="admin-hint">
            {stats.total_users ? Math.round((stats.paying_users / stats.total_users) * 100) : 0}% of signups have bought
            credits
          </div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Credits sold, last 30 days</div>
          <div className="stat-value">{stats.credits_sold_30d.toLocaleString()}</div>
          <div className="admin-hint">{stats.credits_sold_all.toLocaleString()} all time</div>
        </div>
      </div>

      <div className="stat-row" style={{ marginTop: 16 }}>
        <div className="stat-cell">
          <div className="stat-label">Credits outstanding</div>
          <div className="stat-value">{stats.credits_outstanding.toLocaleString()}</div>
          <div className="admin-hint">bought or granted, not yet spent — a liability</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Credits spent, last 30 days</div>
          <div className="stat-value">{stats.credits_spent_30d.toLocaleString()}</div>
          <div className="admin-hint">each is a real SerpApi / AI call</div>
        </div>
        <div className="stat-cell">
          <div className="stat-label">Quick links</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
            <Link href="/admin/users" className="link-btn">
              Browse all users →
            </Link>
            <Link href="/admin/pricing" className="link-btn">
              Edit credit packs & Dodo setup →
            </Link>
          </div>
        </div>
      </div>

      {stats.top_packs.length > 0 && (
        <div className="panel pages-panel admin-section">
          <div className="pages-header">
            <h3>Revenue by pack</h3>
            <Link href="/admin/pricing" className="link-btn">
              Edit packs →
            </Link>
          </div>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Pack</th>
                <th className="num">Sold</th>
                <th className="num">Credits granted</th>
                <th className="num">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_packs.map((pack) => (
                <tr key={pack.product_key}>
                  <td>{pack.name}</td>
                  <td className="num">{pack.sales}</td>
                  <td className="num muted">{pack.credits_granted.toLocaleString()}</td>
                  <td className="num">
                    <Money cents={pack.revenue_cents} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="admin-grid-2 admin-section">
        <div className="panel pages-panel">
          <div className="pages-header">
            <h3>Recent signups</h3>
          </div>
          <div className="admin-scroll">
            <table className="admin-table">
              <tbody>
                {stats.recent_signups.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <Link href={`/admin/users/${u.id}`} className="link-btn">
                        {u.email}
                      </Link>
                    </td>
                    <td className="num muted">{u.credits_balance} cr</td>
                    <td className="num">
                      <Money cents={u.total_paid_cents} />
                    </td>
                    <td className="num muted">{formatDate(u.created_at)}</td>
                  </tr>
                ))}
                {stats.recent_signups.length === 0 && (
                  <tr>
                    <td className="muted">No users yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel pages-panel">
          <div className="pages-header">
            <h3>Recent activity</h3>
          </div>
          <div className="admin-scroll">
            <table className="admin-table">
              <tbody>
                {stats.recent_actions.map((a) => (
                  <tr key={a.id}>
                    <td>{describeAudit(a)}</td>
                    <td className="num muted" style={{ whiteSpace: "nowrap" }}>
                      {formatDateTime(a.created_at)}
                    </td>
                  </tr>
                ))}
                {stats.recent_actions.length === 0 && (
                  <tr>
                    <td className="muted">Nothing yet — admin actions and payments show up here.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
