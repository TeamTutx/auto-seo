"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import AdminSidebar from "@/components/AdminSidebar";

// Client-side gate for the *experience*: signed-out visitors go to /login and
// non-admins back to the app. The real protection is server-side - every
// /admin/* API route answers 403 to anyone not in ADMIN_EMAILS.
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (!user.is_admin) router.replace("/dashboard");
  }, [loading, user, router]);

  if (loading || !user || !user.is_admin) {
    return <div className="loading-state">Loading…</div>;
  }

  return (
    <div className="app">
      <AdminSidebar />
      <main className="main">{children}</main>
    </div>
  );
}
