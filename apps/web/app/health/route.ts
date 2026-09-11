import { NextResponse } from "next/server";

import { getAuthConfig } from "../../lib/auth";

export async function GET() {
  const auth = getAuthConfig();
  const internalSecret = process.env.SBDC_INTERNAL_API_SECRET;
  if (!auth || !internalSecret || internalSecret.length < 32) {
    return NextResponse.json({ status: "configuration_error" }, { status: 503 });
  }
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/submissions`, {
      cache: "no-store",
      headers: { "x-sbdc-internal-secret": internalSecret },
      signal: AbortSignal.timeout(3000),
    });
    const payload = await response.json();
    if (!response.ok || !Array.isArray(payload)) throw new Error("review queue unavailable");
    return NextResponse.json({ status: "ok", service: "web", api: "ok", review_queue: "ok" });
  } catch {
    return NextResponse.json({ status: "unavailable", service: "web", api: "unavailable" }, { status: 503 });
  }
}
