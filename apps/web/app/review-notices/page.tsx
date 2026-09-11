import type { Metadata } from "next";
import { pageMetadata } from "../i18n";
import { getRequestLocale } from "../../lib/request-locale";
import { ReviewNoticesList } from "../public-list";

export async function generateMetadata(): Promise<Metadata> { const locale = await getRequestLocale(); return pageMetadata(locale, "/review-notices", locale === "en" ? "Review notices" : "审查公示", locale === "en" ? "Human-reviewed outcome summaries with explicit evidence limits." : "由审查者决定公开、并明确现有证据边界的结果摘要。"); }

export default async function ReviewNoticesPage() {
  const locale = await getRequestLocale(); const en = locale === "en";
  return <main className="public-index" id="main-content">
    <header><p className="eyebrow">{en ? "Review notices" : "审查公示"}</p><h1>{en ? "Published review outcomes" : "审查结果公示"}</h1><p>{en ? "Reviewers may publish a summary based on material they have assessed. Every notice states the current evidence boundary and keeps automated analysis subordinate to human judgment." : "审查者可基于已核查材料选择公开结果摘要。每条公示都明确当前证据边界，不以自动分析替代人工判断。"}</p></header>
    <ReviewNoticesList locale={locale} />
  </main>;
}
