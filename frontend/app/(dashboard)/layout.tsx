"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { SitesProvider } from "@/lib/sites-context";
import Sidebar from "@/components/Sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return <div className="loading-state">Loading…</div>;
  }

  return (
    <SitesProvider>
      <div className="app">
        <Sidebar />
        <main className="main">{children}</main>
      </div>
    </SitesProvider>
  );
}
