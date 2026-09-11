import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { pageMetadata } from "../../i18n";
import type { Locale } from "../../i18n";
import { getRequestLocale } from "../../../lib/request-locale";

const documentTypes = {
  terms: "terms_of_service", privacy: "privacy_policy", cookies: "cookie_policy",
  refund: "refund_cancellation_policy", "data-rights": "data_rights_notice",
  "do-not-sell": "do_not_sell_share_notice", "ai-disclaimer": "ai_entertainment_disclaimer",
} as const;

type LegalSection = { id: string; title: string; body_markdown: string };
type LegalDocument = { title: string; version: string; effective_at: string; composition: Array<{ sections: LegalSection[] }> };

async function legalDocument(slug: string, locale: Locale): Promise<LegalDocument | null> {
  const type = documentTypes[slug as keyof typeof documentTypes];
  const endpoint = slug === "product-supplement"
    ? `/api/legal/product-supplement?product=sbdc&locale=${locale}`
    : type ? `/api/legal/document?product=sbdc&type=${type}&locale=${locale}` : null;
  if (!endpoint) return null;
  try {
    const response = await fetch(`${process.env.LEGAL_PUBLIC_ORIGIN ?? "https://laws.szlk.ai"}${endpoint}`, { next: { revalidate: 300 } });
    if (!response.ok) return null;
    const payload = await response.json();
    return slug === "product-supplement" ? payload.supplement : payload.document;
  } catch { return null; }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const locale = await getRequestLocale();
  const document = await legalDocument(slug, locale);
  return pageMetadata(locale, `/legal/${slug}`, document?.title ?? (locale === "en" ? "Legal information" : "法律信息"), locale === "en" ? "Current legal terms and product notices for SBDC." : "SBDC 当前适用的法律条款与产品说明。");
}

function Body({ text }: { text: string }) {
  return <div className="legal-body">{text.split(/\n{2,}/).filter(Boolean).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>;
}

export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const locale = await getRequestLocale(); const en = locale === "en";
  if (!(slug in documentTypes) && slug !== "product-supplement") notFound();
  const document = await legalDocument(slug, locale);
  return (
    <main className="legal-shell" id="main-content">
      {document ? <>
        <header><p className="eyebrow">{en ? "SZLK legal document" : "SZLK 法律文件"}</p><h1>{document.title}</h1><p>{en ? "Version" : "版本"} {document.version} · {en ? "Effective" : "生效日期"} {document.effective_at}</p></header>
        {document.composition.flatMap((part) => part.sections).map((section) => <section key={section.id}><h2>{section.title}</h2><Body text={section.body_markdown} /></section>)}
      </> : <section className="legal-unavailable"><p className="eyebrow">{en ? "Legal information" : "法律信息"}</p><h1>{en ? "This document is temporarily unavailable" : "该文件暂时无法载入"}</h1><p>{en ? <>Refresh later or email <a href="mailto:hello@szlk.ai">hello@szlk.ai</a> for the current version.</> : <>请稍后刷新，或通过 <a href="mailto:hello@szlk.ai">hello@szlk.ai</a> 联系我们获取当前版本。</>}</p></section>}
    </main>
  );
}
