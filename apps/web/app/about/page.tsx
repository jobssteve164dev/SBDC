import type { Metadata } from "next";

import { PRODUCT_NAME_EN } from "../brand";
import { pageMetadata } from "../i18n";
import { getRequestLocale } from "../../lib/request-locale";
import { Postcard } from "./postcard";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return pageMetadata(locale, "/about", locale === "en" ? "About SBDC" : "关于 SBDC", locale === "en" ? "What SBDC checks, who it serves, and why every result remains reviewable by people." : "了解 SBDC 检查什么、服务谁，以及为什么所有结果都必须由人复核。");
}

export default async function AboutPage() {
  const locale = await getRequestLocale();
  const en = locale === "en";
  const faq = en ? [
    ["What is SBDC?", `SBDC means ${PRODUCT_NAME_EN}. It is an evidence workspace for finding concerns in a paper, tracing supporting material and making a human review decision.`],
    ["Does SBDC decide that a paper is fraudulent or plagiarized?", "No. SBDC presents evidence and provisional review outcomes. It does not determine intent, misconduct or legal liability."],
    ["What does SBDC check today?", "The current release parses a submitted PDF's structure and reference list, records coverage and preserves locations that a reviewer can revisit."],
    ["Are submitted papers made public?", "No. The PDF and contact email remain private. A submitter may separately choose to publish only the title, authors and reason for review."],
  ] : [
    ["什么是 SBDC？", `SBDC 的全称是 ${PRODUCT_NAME_EN}。它是科研诚信证据工作台，帮助用户发现论文疑点、查看依据并作出人工复核决定。`],
    ["SBDC 会认定论文造假或抄袭吗？", "不会。SBDC 只呈现证据与待复核结论，不判断主观故意、学术不端责任或法律责任。"],
    ["SBDC 目前检查什么？", "当前版本解析用户提交 PDF 的论文结构与参考文献，记录实际覆盖范围，并保留审查者可以返回核对的位置。"],
    ["投稿论文会被公开吗？", "不会公开 PDF 和联系邮箱。投稿人可以另行选择只公开题名、作者与核查理由。"],
  ];
  const jsonLd = [
    { "@context": "https://schema.org", "@type": "Organization", name: "SBDC", alternateName: PRODUCT_NAME_EN, url: "https://sbdc.szlk.uk", parentOrganization: { "@type": "Organization", name: "SZLK LTD", url: "https://szlk.ai" } },
    { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faq.map(([name, text]) => ({ "@type": "Question", name, acceptedAnswer: { "@type": "Answer", text } })) },
  ];
  return <main className="about-shell" id="main-content">
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }} />
    <header className="about-hero"><p className="eyebrow">{en ? "About SBDC" : "关于 SBDC"}</p><h1>{en ? "Research integrity review should begin with evidence people can revisit." : "科研诚信审查，应从人人可复核的证据开始。"}</h1><p>{en ? "SBDC helps reviewers and public-interest submitters move from a concern to its source, understand what was and was not checked, and keep the final decision with a person." : "SBDC 帮助审查者与公众监督者把疑点带回原文，明确哪些内容已经检查、哪些尚未覆盖，并始终把最终判断留给人。"}</p></header>
    <section className="about-principles" aria-labelledby="principles-title"><p className="eyebrow">{en ? "How it works" : "工作原则"}</p><h2 id="principles-title">{en ? "A short path from concern to review" : "从疑点到复核，路径清楚而克制"}</h2><div><article><span>01</span><h3>{en ? "Start with one paper" : "从一篇论文开始"}</h3><p>{en ? "Each task is scoped to the submitted paper and its cited sources." : "每个任务围绕用户提交的论文及其引用来源展开。"}</p></article><article><span>02</span><h3>{en ? "Preserve the trail" : "保留证据路径"}</h3><p>{en ? "Evidence retains source locations, method limits and reviewable assets." : "证据保留原文位置、方法边界和可复核资产。"}</p></article><article><span>03</span><h3>{en ? "Let people decide" : "由人作出判断"}</h3><p>{en ? "Automated analysis supports review; it never becomes an allegation by itself." : "自动分析只辅助复核，不会自行成为对作者的指控。"}</p></article></div></section>
    <section className="faq-section" aria-labelledby="faq-title"><p className="eyebrow">{en ? "Questions answered" : "常见问题"}</p><h2 id="faq-title">{en ? "Clear answers about scope and responsibility" : "关于范围与责任的直接回答"}</h2>{faq.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</section>
    <Postcard locale={locale} />
  </main>;
}
