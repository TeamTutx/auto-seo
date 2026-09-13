"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function DashboardHome() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [hasSites, setHasSites] = useState(false);

  useEffect(() => {
    api
      .listSites()
      .then((sites) => {
        if (sites.length > 0) {
          router.replace(`/sites/${sites[0].id}`);
        } else {
          setHasSites(false);
          setChecked(true);
        }
      })
      .catch(() => setChecked(true));
  }, [router]);

  if (!checked || hasSites) {
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
