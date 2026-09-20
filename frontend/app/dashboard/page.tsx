"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { routes } from "@/lib/routes";
import { useSites } from "@/lib/sites-context";

export default function DashboardHome() {
  const router = useRouter();
  const { sites } = useSites();

  useEffect(() => {
    if (sites && sites.length > 0) {
      router.replace(routes.site(sites[0].id));
    }
  }, [sites, router]);

  if (sites === null || sites.length > 0) {
    return <div className="loading-state">Loading…</div>;
  }

  return (
    <div className="panel" style={{ textAlign: "center", padding: "60px 40px" }}>
      <div className="page-title" style={{ marginBottom: 8 }}>
        Add your first site
      </div>
      <div className="page-sub">
        Use “+ Add site” in the sidebar to start auditing a domain — no verification needed to try it out.
      </div>
    </div>
  );
}
