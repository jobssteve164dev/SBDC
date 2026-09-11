import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "../../../lib/auth";

export async function POST(request: Request) {
  const locale = new URL(request.url).searchParams.get("locale");
  const response = new NextResponse(null, { status: 303, headers: { location: locale === "en" ? "/en/login" : "/login" } });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
