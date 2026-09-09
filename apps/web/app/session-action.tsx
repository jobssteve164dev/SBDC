import { cookies } from "next/headers";

import { getAuthConfig, SESSION_COOKIE, verifySessionToken } from "../lib/auth";

export async function SessionAction() {
  const config = getAuthConfig();
  if (!config) return null;
  const cookieStore = await cookies();
  if (!(await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config))) return null;

  return (
    <form action="/auth/logout" method="post">
      <button className="header-action" type="submit">退出登录</button>
    </form>
  );
}
