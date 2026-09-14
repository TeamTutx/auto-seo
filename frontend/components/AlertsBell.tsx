"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Alert } from "@/lib/types";

export default function AlertsBell() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      setAlerts(await api.listAlerts());
    } catch {
      setAlerts([]);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000); // pick up new scheduled-audit alerts without a manual refresh
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const unreadCount = alerts?.filter((a) => !a.read).length ?? 0;

  async function handleOpenAlert(alert: Alert) {
    if (!alert.read) {
      try {
        await api.markAlertRead(alert.id);
        setAlerts((prev) => prev?.map((a) => (a.id === alert.id ? { ...a, read: true } : a)) ?? null);
      } catch {
        // non-critical - the alert just stays marked unread until next load
      }
    }
    setOpen(false);
    router.push(`/sites/${alert.site_id}/pages/${alert.page_id}`);
  }

  if (alerts === null || alerts.length === 0) return null;

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        className="btn-ghost btn"
        style={{ fontSize: 11, padding: "5px 9px", position: "relative" }}
        onClick={() => setOpen((v) => !v)}
      >
        Alerts
        {unreadCount > 0 && (
          <span
            style={{
              marginLeft: 6,
              background: "var(--bad)",
              color: "#fff",
              borderRadius: 10,
              padding: "1px 6px",
              fontSize: 10.5,
              fontWeight: 600,
            }}
          >
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            bottom: "100%",
            left: 0,
            marginBottom: 8,
            width: 280,
            maxWidth: "80vw",
            maxHeight: 320,
            overflowY: "auto",
            overflowX: "hidden",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 8,
            zIndex: 50,
          }}
        >
          {alerts.map((alert) => (
            <div
              key={alert.id}
              onClick={() => handleOpenAlert(alert)}
              style={{
                padding: "8px 10px",
                borderRadius: 6,
                cursor: "pointer",
                background: alert.read ? "transparent" : "var(--surface-raised)",
                marginBottom: 4,
              }}
            >
              <div style={{ fontSize: 12, color: "var(--text)", wordBreak: "break-word" }}>{alert.message}</div>
              <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 3 }}>
                {new Date(alert.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
