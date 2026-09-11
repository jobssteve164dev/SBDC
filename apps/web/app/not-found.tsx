import { getRequestLocale } from "../lib/request-locale";
import { pathFor } from "./i18n";

export default async function NotFound() {
  const locale = await getRequestLocale(); const en = locale === "en";
  return <main className="loading-screen"><p>{en ? "This page or review task could not be found." : "没有找到这个页面或检查任务。"}</p><a className="secondary-button" href={pathFor(locale, "/")}>{en ? "Return home" : "返回首页"}</a></main>;
}
