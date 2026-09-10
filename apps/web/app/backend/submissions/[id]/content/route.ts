import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getAuthConfig, SESSION_COOKIE, verifySessionToken } from "../../../../../lib/auth";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const config = getAuthConfig();
  const cookieStore = await cookies();
  if (!config || !(await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config))) {
    return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  }
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return NextResponse.json({ detail: "投稿不存在" }, { status: 404 });
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/submissions/${id}/content`, {
      cache: "no-store",
      headers: { "X-SBDC-Internal-Secret": process.env.SBDC_INTERNAL_API_SECRET ?? process.env.SBDC_SESSION_SECRET ?? "" },
    });
    if (!response.ok || !response.body) {
      return NextResponse.json({ detail: response.status === 404 ? "投稿不存在" : "论文暂时无法载入" }, { status: response.status });
    }
    return new NextResponse(response.body, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": 'inline; filename="submitted-paper.pdf"',
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json({ detail: "论文暂时无法载入" }, { status: 503 });
  }
}
