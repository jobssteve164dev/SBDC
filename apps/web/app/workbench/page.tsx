import type { Metadata } from "next";

import { pageMetadata } from "../i18n";
import { getRequestLocale } from "../../lib/request-locale";
import { UploadPaper } from "../upload-paper";
import { SubmissionQueue } from "./submission-queue";

export async function generateMetadata(): Promise<Metadata> { const locale = await getRequestLocale(); return pageMetadata(locale, "/workbench", locale === "en" ? "Review workbench" : "审查工作台", locale === "en" ? "Authorized SBDC evidence review workspace." : "SBDC 获授权论文证据审查工作台。", true); }

export default async function WorkbenchPage() {
  const locale = await getRequestLocale(); const en = locale === "en";
  return (
    <main className="home-shell" id="main-content">
      <section className="hero">
        <p className="eyebrow">{en ? "Review from the source" : "从原文开始复核"}</p>
        <h1>{en ? <>Inspect structure and references,<br />then make a decision.</> : <>看清论文结构与引用，<br />再作判断。</>}</h1>
        <p className="hero-copy">{en ? "Upload one PDF. SBDC parses the title, body structure and references, discloses actual coverage and keeps each result tied to its source location." : "上传一篇 PDF，我们会解析论文题名、正文结构和参考文献，并标明实际覆盖范围。所有结果都能回到原文位置核对。"}</p>
      </section>
      <UploadPaper locale={locale} />
      <section className="trust-row" aria-label={en ? "Processing boundaries" : "处理边界"}>
        <div><strong>{en ? "Task-scoped" : "任务内处理"}</strong><span>{en ? "The paper is used only for this review" : "论文只用于当前检查"}</span></div>
        <div><strong>{en ? "No automatic allegation" : "不做自动定性"}</strong><span>{en ? "People must review parsed results" : "解析结果需要人工复核"}</span></div>
        <div><strong>{en ? "Honest coverage" : "真实覆盖范围"}</strong><span>{en ? "Failures and gaps remain visible" : "失败与缺失会如实显示"}</span></div>
      </section>
      <SubmissionQueue locale={locale} />
    </main>
  );
}
