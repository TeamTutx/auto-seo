"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const LINKS = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/pricing", label: "Credit packs" },
];

export default function AdminSidebar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="sidebar">
      <Link href="/admin" className="brand" style={{ textDecoration: "none" }}>
        <div className="brand-mark" />
        <div className="brand-name">
          Signal<span className="admin-tag">ADMIN</span>
        </div>
      </Link>

      <div className="nav-section" style={{ flex: 1 }}>
        <div className="nav-label">MANAGE</div>
        <div className="site-list">
          {LINKS.map((l) => {
            const active = l.exact ? pathname === l.href : pathname.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href} className={`site-item ${active ? "active" : ""}`}>
                <div className="site-item-name">{l.label}</div>
              </Link>
            );
          })}
        </div>
        <Link href="/dashboard" className="add-site-btn" style={{ textDecoration: "none", marginTop: 12 }}>
          ← Back to app
        </Link>
      </div>

      <div className="sidebar-footer">
        <div className="footer-user">
          <div className="avatar">{user?.email.slice(0, 2).toUpperCase() ?? "?"}</div>
          <div className="footer-text">{user?.email}</div>
        </div>
        <button
          className="logout-btn"
          onClick={() => {
            logout();
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
