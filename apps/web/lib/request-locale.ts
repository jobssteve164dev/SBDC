import { headers } from "next/headers";
import { cookies } from "next/headers";

import type { Locale } from "../app/i18n";

export async function getRequestLocale(): Promise<Locale> {
  const [requestHeaders, requestCookies] = await Promise.all([headers(), cookies()]);
  return requestHeaders.get("x-sbdc-locale") === "en" || requestCookies.get("sbdc_locale")?.value === "en" ? "en" : "zh-CN";
}

export async function getRequestPath(): Promise<string> {
  return (await headers()).get("x-sbdc-path") ?? "/";
}
