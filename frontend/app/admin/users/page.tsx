"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AdminUserList } from "@/lib/types";
import { Money, PlanTag } from "@/components/admin/AdminBits";

type SortKey = "created_at" | "email" | "credits" | "total_paid" | "sites" | "last_scan";

const COLUMNS: { key: SortKey; label: string; num?: boolean }[] = [
  { key: "email", label: "Email" },
  { key: "credits", label: "Credits", num: true },
  { key: "sites", label: "Sites", num: true },
  { key: "total_paid", label: "Paid", num: true },
  { key: "last_scan", label: "Last scan" },
  { key: "created_at", label: "Joined" },
];

const PAGE_SIZE = 25;

export default function AdminUsersPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState("");
  const [paid, setPaid] = useState<"" | "paid" | "unpaid">("");
  const [sort, setSort] = useState<SortKey>("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AdminUserList | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Debounce the search box so we don't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .adminUsers({
        q: q || undefined,
        plan: plan || undefined,
        paid: paid === "" ? undefined : paid === "paid",
        sort,
        order,
        page,
        pageSize: PAGE_SIZE,
      })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "Could not load users."));
    return () => {
      cancelled = true;
    };
  }, [q, plan, paid, sort, order, page]);

  function toggleSort(key: SortKey) {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder(key === "email" ? "asc" : "desc");
    }
    setPage(1);
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <div className="topbar">
        <h1 className="page-title">Users</h1>
        {data && <span className="admin-hint">{data.total} total</span>}
      </div>

      <div className="panel pages-panel">
        <div className="admin-toolbar">
          <input
            className="admin-input grow"
            placeholder="Search by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="admin-select"
            value={plan}
            onChange={(e) => {
              setPlan(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All plans</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
            <option value="agency">Agency</option>
          </select>
          <select
            className="admin-select"
            value={paid}
            onChange={(e) => {
              setPaid(e.target.value as "" | "paid" | "unpaid");
              setPage(1);
            }}
          >
            <option value="">Paid or not</option>
            <option value="paid">Has paid</option>
            <option value="unpaid">Never paid</option>
          </select>
        </div>

        {error && (
          <div className="form-error" style={{ margin: 16 }}>
            {error}
          </div>
        )}

        <div className="admin-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                {COLUMNS.slice(0, 1).map((c) => (
                  <th key={c.key} className="sortable" onClick={() => toggleSort(c.key)}>
                    {c.label} {sort === c.key ? (order === "asc" ? "↑" : "↓") : ""}
                  </th>
                ))}
                <th>Plan</th>
                {COLUMNS.slice(1).map((c) => (
                  <th
                    key={c.key}
                    className={`sortable ${c.num ? "num" : ""}`}
                    style={c.num ? { textAlign: "right" } : undefined}
                    onClick={() => toggleSort(c.key)}
                  >
                    {c.label} {sort === c.key ? (order === "asc" ? "↑" : "↓") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id} className="clickable" onClick={() => router.push(`/admin/users/${u.id}`)}>
                  <td>
                    {u.email}
                    {u.is_admin && <span className="admin-tag">ADMIN</span>}
                  </td>
                  <td>
                    <PlanTag plan={u.plan} />
                  </td>
                  <td className="num">{u.credits_balance}</td>
                  <td className="num">{u.sites_count}</td>
                  <td className="num">
                    <Money cents={u.total_paid_cents} />
                  </td>
                  <td className="muted">{formatDate(u.last_active_at)}</td>
                  <td className="muted">{formatDate(u.created_at)}</td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-state">
                    No users match.
                  </td>
                </tr>
              )}
              {!data && !error && (
                <tr>
                  <td colSpan={7} className="empty-state">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {data && data.total > data.page_size && (
          <div className="pager">
            <span>
              Page {page} of {totalPages}
            </span>
            <span style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button className="btn btn-ghost btn-sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </span>
          </div>
        )}
      </div>
    </>
  );
}
