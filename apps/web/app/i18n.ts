import type { Metadata } from "next";

import { PRODUCT_NAME, PRODUCT_NAME_EN } from "./brand";

export type Locale = "zh-CN" | "en";
export const SITE_ORIGIN = "https://sbdc.szlk.uk";
export const SUBMISSION_TERMS_NOTICE: Record<Locale, string> = {
  "zh-CN": "我同意服务条款、隐私政策与产品法律补充；并理解投稿或自动分析均不代表论文存在问题，SBDC 不替代机构调查、同行评议或法律判断。",
  en: "I agree to the Terms, Privacy Policy and Product Legal Supplement; I understand that neither a submission nor automated analysis establishes wrongdoing and that SBDC does not replace institutional investigation, peer review or legal advice.",
};

export function pathFor(locale: Locale, path: string) {
  const normalized = path === "/" ? "" : path;
  return locale === "en" ? `/en${normalized}` || "/en" : path || "/";
}

export function pageMetadata(locale: Locale, path: string, title: string, description: string, noIndex = false): Metadata {
  const url = `${SITE_ORIGIN}${pathFor(locale, path)}`;
  const image = `${SITE_ORIGIN}/postcards/sbdc-postcard-${locale === "en" ? "en" : "zh"}.png`;
  return {
    metadataBase: new URL(SITE_ORIGIN),
    title: title.startsWith(`${PRODUCT_NAME} ·`) ? title : `${title} · ${PRODUCT_NAME}`,
    description,
    alternates: {
      canonical: url,
      languages: { "zh-CN": `${SITE_ORIGIN}${pathFor("zh-CN", path)}`, en: `${SITE_ORIGIN}${pathFor("en", path)}`, "x-default": `${SITE_ORIGIN}${pathFor("zh-CN", path)}` },
    },
    robots: noIndex ? { index: false, follow: false } : { index: true, follow: true },
    openGraph: { type: "website", url, siteName: `${PRODUCT_NAME} · ${PRODUCT_NAME_EN}`, title, description, locale: locale === "en" ? "en_GB" : "zh_CN", images: [{ url: image, width: 1200, height: 630, alt: locale === "en" ? "SBDC sharing postcard" : "SBDC 分享明信片" }] },
    twitter: { card: "summary_large_image", title, description, images: [image] },
  };
}
