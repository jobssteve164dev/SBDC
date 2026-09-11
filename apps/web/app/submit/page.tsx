import type { Metadata } from "next";

import { pageMetadata } from "../i18n";
import { getRequestLocale } from "../../lib/request-locale";
import { PublicSubmission } from "./public-submission";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return pageMetadata(locale, "/submit", locale === "en" ? "Submit a paper for review" : "提交待核查论文", locale === "en" ? "Submit a paper you are entitled to provide and explain the research integrity concern that should be reviewed." : "提交你有权提供的论文，并说明希望由科研诚信审查者核查的具体问题。");
}

export default async function SubmitPage() {
  const locale = await getRequestLocale();
  const en = locale === "en";
  return (
    <main className="submit-shell" id="main-content">
      <section className="submit-intro">
        <p className="eyebrow">{en ? "Public-interest submission" : "公众科研监督投稿"}</p>
        <h1>{en ? "Put a paper that merits scrutiny before a reviewer." : "把值得核查的论文，交到审查者手中。"}</h1>
        <p>{en ? "Submit a PDF you are entitled to provide and explain the specific concern. Receipt does not mean the paper is problematic or that a formal investigation will follow." : "请提交你有权提供的论文 PDF，并说明希望核查的具体原因。收到投稿不代表论文存在问题，也不代表一定进入正式调查。"}</p>
        <div className="submit-boundaries"><p><strong>{en ? "We will" : "我们会做"}</strong><span>{en ? "Record the submission, confirm receipt and make it available to an authorized reviewer." : "保存投稿、确认收件、交由获授权审查者评估。"}</span></p><p><strong>{en ? "We will not" : "我们不会做"}</strong><span>{en ? "Publish submitter details or label an author based only on automated output." : "公开投稿人信息，或仅凭自动结果给作者定性。"}</span></p></div>
      </section>
      <PublicSubmission locale={locale} />
    </main>
  );
}
