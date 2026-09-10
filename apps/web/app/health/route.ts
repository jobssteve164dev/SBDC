import { NextResponse } from "next/server";

import { getAuthConfig } from "../../lib/auth";

export async function GET() {
  if (!getAuthConfig()) {
    return NextResponse.json({ status: "configuration_error" }, { status: 503 });
  }
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/health`, {
      cache: "no-store", signal: AbortSignal.timeout(3000),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") throw new Error("api unhealthy");
    return NextResponse.json({ status: "ok", service: "web", api: "ok" });
  } catch {
    return NextResponse.json({ status: "unavailable", service: "web", api: "unavailable" }, { status: 503 });
  }
}
