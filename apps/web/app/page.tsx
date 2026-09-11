import type { Metadata } from "next";
import Link from "next/link";
import { PRODUCT_DESCRIPTOR_ZH, PRODUCT_NAME, PRODUCT_NAME_EN } from "./brand";
import { pageMetadata, pathFor } from "./i18n";
import { getRequestLocale } from "../lib/request-locale";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return pageMetadata(locale, "/", `${PRODUCT_NAME} · ${PRODUCT_NAME_EN}`, locale === "en" ? "Trace research integrity concerns back to paper structure, references and reviewable source locations." : "把科研诚信疑点带回论文结构、参考文献和可复核的原文位置。基础解析现已开放使用。");
}

export default async function Home() {
  const locale = await getRequestLocale();
  const en = locale === "en";
  return (
    <main id="main-content">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({ "@context": "https://schema.org", "@type": "WebSite", name: "SBDC", alternateName: PRODUCT_NAME_EN, url: `https://sbdc.szlk.uk${pathFor(locale, "/")}`, description: en ? "Evidence-led research integrity review with traceable source locations and human decisions." : "面向科研诚信审查的证据工作台，让问题、依据与人工复核都能回到原文。", publisher: { "@type": "Organization", name: "SZLK LTD", url: "https://szlk.ai" }, inLanguage: locale }).replaceAll("<", "\\u003c") }} />
      <section className="marketing-hero">
        <div>
          <p className="eyebrow">{en ? "Research integrity evidence review" : PRODUCT_DESCRIPTOR_ZH}</p>
          <h1>{PRODUCT_NAME}</h1>
          <p className="hero-lead">{PRODUCT_NAME_EN}</p>
          <p className="hero-copy">{en ? "Take every concern back to the source. SBDC organizes paper structure, references and review leads into evidence that people can locate, trace and independently assess." : "让每一项疑点，都能回到原文与依据。面向科研审查者与公众监督者，将论文结构、参考文献和核查线索整理成可定位、可追溯、可由人复核的证据基础。"}</p>
          <div className="hero-actions">
            <Link className="primary-link" href={pathFor(locale, "/submit")}>{en ? "Submit a paper" : "提交待核查论文"} <span aria-hidden="true">→</span></Link>
            <Link className="text-link" href={pathFor(locale, "/login")}>{en ? "Reviewer sign in" : "审查者登录"}</Link>
          </div>
        </div>
        <aside className="evidence-preview" aria-label={en ? "Current review scope" : "当前检查范围"}>
          <p className="preview-kicker">Evidence first · {en ? "reviewable by design" : "证据先行"}</p>
          <blockquote>{en ? <>Not an arbitrary score,<br />but a path others can review.</> : <>不是给出一个武断分数，<br />而是保留一条复核路径。</>}</blockquote>
          <div className="evidence-line"><span>{en ? "Paper structure" : "论文结构"}</span><strong>{en ? "Title · sections · pages" : "题名 · 章节 · 页码"}</strong></div>
          <div className="evidence-line"><span>{en ? "References" : "参考文献"}</span><strong>{en ? "Entries · identifiers · locations" : "条目 · 标识符 · 位置"}</strong></div>
          <p className="preview-boundary">{en ? "Textual, statistical and image-evidence checks are still being built and are not included in current results." : "文本、统计与图片证据检查仍在后续建设中；当前结果不包含这些结论。"}</p>
        </aside>
      </section>

      <section className="value-section" aria-labelledby="value-title">
        <p className="eyebrow">{en ? "Why SBDC" : "SBDC 的价值"}</p>
        <h2 id="value-title">{en ? "Evidence before conclusions, with clear limits." : "证据先于结论，边界同样清楚。"}</h2>
        <div className="value-grid">
          <article><span>01</span><h3>{en ? "Locate, don't guess" : "定位，而非猜测"}</h3><p>{en ? "Parse titles, sections and pages so each lead can return to the source." : "解析论文题名、章节与页码，让每一条线索都能回到原文。"}</p></article>
          <article><span>02</span><h3>{en ? "Show evidence and gaps" : "呈现依据与缺口"}</h3><p>{en ? "Organize reference entries, identifiers and locations while disclosing unavailable or unparsed material." : "整理参考文献条目、标识符和位置，也如实说明无法取得或无法解析的材料。"}</p></article>
          <article><span>03</span><h3>{en ? "Leave decisions to people" : "把判断留给人"}</h3><p>{en ? "SBDC organizes evidence and review questions; it does not automatically allege fabrication, plagiarism or intent." : "SBDC 整理证据和待复核事项，不自动认定造假、抄袭或主观故意。"}</p></article>
        </div>
      </section>

      <section className="process-section" aria-labelledby="process-title">
        <div><p className="eyebrow">{en ? "Public research oversight" : "公众科研监督"}</p><h2 id="process-title">{en ? "Found a concern? Put the paper before a reviewer." : "发现疑点，可以把论文交给审查者。"}</h2></div>
        <div className="process-copy">
          <p>{en ? "No account is required. Provide an email, a PDF you are entitled to submit, and a specific reason for review. You decide whether the submission summary is public." : "无需注册账号。留下联系邮箱，提交你有权提供的 PDF 和具体核查理由；你可以自行决定是否公开这条投稿。"}</p>
          <ol><li><strong>{en ? "Submit material" : "提交材料"}</strong><span>{en ? "Paper PDF, contact email and review reason" : "论文 PDF、联系邮箱与核查理由"}</span></li><li><strong>{en ? "Choose visibility" : "自主公开"}</strong><span>{en ? "Email and PDF remain private even for public submissions" : "公开时也不会展示邮箱和论文文件"}</span></li><li><strong>{en ? "Human review" : "人工复核"}</strong><span>{en ? "An authorized reviewer decides whether to publish an outcome" : "审查者独立决定是否公示审查结果"}</span></li></ol>
          <div className="section-actions"><Link className="secondary-button" href={pathFor(locale, "/submit")}>{en ? "Start a submission" : "开始投稿"}</Link><Link className="text-link" href={pathFor(locale, "/review-notices")}>{en ? "View review notices" : "查看审查公示"}</Link></div>
        </div>
      </section>
    </main>
  );
}
