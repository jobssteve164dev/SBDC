import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getAuthConfig, SESSION_COOKIE, verifySessionToken } from "../../../../../lib/auth";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const config = getAuthConfig();
  const cookieStore = await cookies();
  if (!config || !(await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config))) {
    return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  }
  if (request.headers.get("sec-fetch-site")?.toLowerCase() === "cross-site") {
    return NextResponse.json({ detail: "请求来源无效" }, { status: 403 });
  }
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return NextResponse.json({ detail: "投稿不存在" }, { status: 404 });
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/submissions/${id}/publication`, {
      method: "POST", cache: "no-store", body: await request.formData(),
      headers: { "X-SBDC-Internal-Secret": process.env.SBDC_INTERNAL_API_SECRET ?? process.env.SBDC_SESSION_SECRET ?? "" },
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "公示状态暂时无法保存" }, { status: 503 });
  }
}
