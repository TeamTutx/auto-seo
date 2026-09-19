import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { API_URL } from "@/lib/site";

// Called by /admin/pricing after a change so the public landing page shows it
// immediately instead of waiting out its 5-minute cache. Only an admin's
// session may trigger it: we ask the API who the bearer token belongs to.
export async function POST(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });

  let me: { is_admin?: boolean } | null = null;
  try {
    const res = await fetch(`${API_URL}/auth/me`, { headers: { authorization }, cache: "no-store" });
    if (res.ok) me = await res.json();
  } catch {
    return NextResponse.json({ detail: "API unreachable" }, { status: 502 });
  }
  if (!me) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
  if (!me.is_admin) return NextResponse.json({ detail: "Admin access required" }, { status: 403 });

  revalidatePath("/");
  return NextResponse.json({ revalidated: true });
}
