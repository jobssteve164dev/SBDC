import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { SessionAction } from "./session-action";
import { SiteFooter } from "./site-footer";
import { PRODUCT_NAME, PRODUCT_NAME_EN } from "./brand";
import { pageMetadata, pathFor } from "./i18n";
import { getRequestLocale, getRequestPath } from "../lib/request-locale";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return pageMetadata(locale, "/", `${PRODUCT_NAME} · ${PRODUCT_NAME_EN}`, locale === "en"
    ? "Evidence-led research integrity review with traceable source locations and human decisions."
    : "面向科研诚信审查的证据工作台，让问题、依据与人工复核都能回到原文。");
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [locale, requestPath] = await Promise.all([getRequestLocale(), getRequestPath()]);
  const en = locale === "en";
  const alternateLanguagePath = en ? (requestPath.slice(3) || "/") : pathFor("en", requestPath);
  return (
    <html lang={locale}>
      <body>
        <a className="skip-link" href="#main-content">{en ? "Skip to main content" : "跳到主要内容"}</a>
        <header className="site-header">
          <div className="header-inner">
            <Link className="brand" href={pathFor(locale, "/")} aria-label={en ? `Return to ${PRODUCT_NAME} home` : `返回${PRODUCT_NAME}首页`}>
              <span className="brand-mark">S</span>
              <span className="brand-name"><strong>{PRODUCT_NAME}</strong><small>{PRODUCT_NAME_EN}</small></span>
            </Link>
            <nav className="site-nav" aria-label={en ? "Primary navigation" : "主要导航"}>
              <Link href={pathFor(locale, "/submit")}>{en ? "Submit" : "我要投稿"}</Link>
              <Link href={pathFor(locale, "/public-submissions")}>{en ? "Public submissions" : "公开投稿"}</Link>
              <Link href={pathFor(locale, "/review-notices")}>{en ? "Review notices" : "审查公示"}</Link>
              <Link href={pathFor(locale, "/about")}>{en ? "About" : "关于"}</Link>
              <SessionAction locale={locale} />
              <Link className="language-link" href={alternateLanguagePath} hrefLang={en ? "zh-CN" : "en"}>{en ? "中文" : "EN"}</Link>
            </nav>
          </div>
        </header>
        {children}
        <SiteFooter locale={locale} />
      </body>
    </html>
  );
}
