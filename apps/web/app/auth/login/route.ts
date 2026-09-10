import { NextRequest, NextResponse } from "next/server";

import {
  createSessionToken,
  getAuthConfig,
  safeNextPath,
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  verifyCredentials,
} from "../../../lib/auth";
import {
  clearLoginFailures,
  loginClientKey,
  recordLoginFailure,
  retryAfterSeconds,
} from "../../../lib/login-rate-limit";

type LoginError = "configuration" | "credentials" | "rate_limit";

function loginRedirect(error: LoginError, next: string, retryAfter = 0) {
  const location = new URL("/login", "https://sbdc.local");
  location.searchParams.set("error", error);
  if (next !== "/workbench") location.searchParams.set("next", next);
  const headers: Record<string, string> = { location: `${location.pathname}${location.search}` };
  if (retryAfter) headers["retry-after"] = String(retryAfter);
  return new NextResponse(null, { status: 303, headers });
}

export async function POST(request: NextRequest) {
  const form = await request.formData();
  const next = safeNextPath(form.get("next"));
  const config = getAuthConfig();
  if (!config) return loginRedirect("configuration", next);
  const clientKey = loginClientKey(request.headers);
  const retryAfter = retryAfterSeconds(clientKey);
  if (retryAfter) return loginRedirect("rate_limit", next, retryAfter);

  const username = form.get("username");
  const password = form.get("password");
  const validCredentials = (
    typeof username !== "string"
    || typeof password !== "string"
  ) ? false : await verifyCredentials(username, password, config);
  if (!validCredentials) {
    recordLoginFailure(clientKey);
    return loginRedirect("credentials", next);
  }

  clearLoginFailures(clientKey);
  const response = new NextResponse(null, { status: 303, headers: { location: next } });
  response.cookies.set(SESSION_COOKIE, await createSessionToken(config), {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  return response;
}
