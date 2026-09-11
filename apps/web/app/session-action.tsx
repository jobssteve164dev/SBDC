import { cookies } from "next/headers";

import { getAuthConfig, SESSION_COOKIE, verifySessionToken } from "../lib/auth";
import { Locale, pathFor } from "./i18n";

export async function SessionAction({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const config = getAuthConfig();
  if (!config) return <a className="header-action" href={pathFor(locale, "/login")}>{en ? "Reviewer sign in" : "审查者登录"}</a>;
  const cookieStore = await cookies();
  if (!(await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config))) {
    return <a className="header-action" href={pathFor(locale, "/login")}>{en ? "Reviewer sign in" : "审查者登录"}</a>;
  }

  return (
    <><a className="header-action" href={pathFor(locale, "/workbench")}>{en ? "Workbench" : "工作台"}</a><form action={`/auth/logout?locale=${locale}`} method="post"><button className="header-action" type="submit">{en ? "Sign out" : "退出"}</button></form></>
  );
}
