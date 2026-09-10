import { NextRequest, NextResponse } from "next/server";

import { getAuthConfig, SESSION_COOKIE, safeNextPath, verifySessionToken } from "./lib/auth";

const PUBLIC_PATHS = new Set(["/", "/login", "/submit", "/public-submissions", "/review-notices", "/health", "/auth/login", "/auth/logout", "/icon.svg", "/favicon.ico"]);

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  if (
    PUBLIC_PATHS.has(pathname)
    || pathname.startsWith("/legal/")
    || pathname.startsWith("/backend/public/")
    || pathname.startsWith("/_next/")
  ) return NextResponse.next();

  const config = getAuthConfig();
  const authenticated = config
    ? await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value, config)
    : false;
  if (authenticated) return NextResponse.next();

  if (pathname === "/backend" || pathname.startsWith("/backend/")) {
    return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", safeNextPath(`${pathname}${request.nextUrl.search}`));
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
