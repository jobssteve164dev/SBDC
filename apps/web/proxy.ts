import { NextRequest, NextResponse } from "next/server";

import { getAuthConfig, SESSION_COOKIE, safeNextPath, verifySessionToken } from "./lib/auth";

const PUBLIC_PATHS = new Set(["/", "/about", "/login", "/submit", "/public-submissions", "/review-notices", "/health", "/robots.txt", "/sitemap.xml", "/auth/login", "/auth/logout", "/icon.svg", "/favicon.ico"]);

function localizedResponse(request: NextRequest, locale: "zh-CN" | "en") {
  const headers = new Headers(request.headers);
  headers.set("x-sbdc-locale", locale);
  headers.set("x-sbdc-path", request.nextUrl.pathname);
  return NextResponse.next({ request: { headers } });
}

export async function proxy(request: NextRequest) {
  const requestedPath = request.nextUrl.pathname;
  const locale = requestedPath === "/en" || requestedPath.startsWith("/en/") ? "en" : "zh-CN";
  const pathname = locale === "en" ? requestedPath.slice(3) || "/" : requestedPath;
  if (
    PUBLIC_PATHS.has(pathname)
    || pathname.startsWith("/legal/")
    || pathname.startsWith("/backend/public/")
    || pathname.startsWith("/_next/")
    || pathname.startsWith("/postcards/")
  ) return localizedResponse(request, locale);

  const config = getAuthConfig();
  const authenticated = config
    ? await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value, config)
    : false;
  if (authenticated) return localizedResponse(request, locale);

  if (pathname === "/backend" || pathname.startsWith("/backend/")) {
    return NextResponse.json({ detail: locale === "en" ? "Please sign in" : "请先登录" }, { status: 401 });
  }

  const loginUrl = new URL(locale === "en" ? "/en/login" : "/login", request.url);
  loginUrl.searchParams.set("next", safeNextPath(`${requestedPath}${request.nextUrl.search}`));
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
