import type { Metadata } from "next";
import { pageMetadata } from "../i18n";
import { getRequestLocale } from "../../lib/request-locale";
import { PublicSubmissionsList } from "../public-list";

export async function generateMetadata(): Promise<Metadata> { const locale = await getRequestLocale(); return pageMetadata(locale, "/public-submissions", locale === "en" ? "Public submissions" : "公开投稿", locale === "en" ? "Papers and review reasons that submitters have chosen to make public; publication is not an allegation." : "投稿人主动选择公开的论文题名、作者与核查理由；公开不代表论文存在问题。"); }

export default async function PublicSubmissionsPage() {
  const locale = await getRequestLocale(); const en = locale === "en";
  return <main className="public-index" id="main-content">
    <header><p className="eyebrow">{en ? "Public submissions" : "公众投稿"}</p><h1>{en ? "Papers submitted publicly" : "公开投稿论文"}</h1><p>{en ? "Only titles, authors and review reasons that submitters choose to publish appear here. Publication does not mean a paper is problematic or that SBDC accepts the submitter's claim." : "这里只展示投稿人主动选择公开的题名、作者与核查理由。公开不代表论文存在问题，也不代表 SBDC 已接受其主张。"}</p></header>
    <PublicSubmissionsList locale={locale} />
  </main>;
}
