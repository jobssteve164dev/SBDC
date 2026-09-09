import { NextResponse } from "next/server";

import { getAuthConfig } from "../../lib/auth";

export function GET() {
  if (!getAuthConfig()) {
    return NextResponse.json({ status: "configuration_error" }, { status: 503 });
  }
  return NextResponse.json({ status: "ok" });
}
