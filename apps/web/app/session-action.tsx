import { cookies } from "next/headers";

import { getAuthConfig, SESSION_COOKIE, verifySessionToken } from "../lib/auth";

export async function SessionAction() {
  const config = getAuthConfig();
  if (!config) return <a className="header-action" href="/login">审查者登录</a>;
  const cookieStore = await cookies();
  if (!(await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config))) {
    return <a className="header-action" href="/login">审查者登录</a>;
  }

  return (
    <><a className="header-action" href="/workbench">工作台</a><form action="/auth/logout" method="post"><button className="header-action" type="submit">退出</button></form></>
  );
}
