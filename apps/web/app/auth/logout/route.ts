import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "../../../lib/auth";

export async function POST() {
  const response = new NextResponse(null, { status: 303, headers: { location: "/login" } });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
