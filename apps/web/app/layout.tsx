import type { Metadata } from "next";
import "./globals.css";
import { SessionAction } from "./session-action";
import { SiteFooter } from "./site-footer";
import { PRODUCT_NAME_EN, PRODUCT_NAME_ZH } from "./brand";

export const metadata: Metadata = {
  title: `${PRODUCT_NAME_ZH} · ${PRODUCT_NAME_EN}`,
  description: "解析论文结构和参考文献，形成可回到原文复核的检查基础。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <header className="site-header">
          <div className="header-inner">
            <a className="brand" href="/" aria-label={`返回${PRODUCT_NAME_ZH}首页`}>
              <span className="brand-mark">证</span>
              <span className="brand-name"><strong>{PRODUCT_NAME_ZH}</strong><small>{PRODUCT_NAME_EN}</small></span>
            </a>
            <nav className="public-nav" aria-label="主要导航">
              <a href="/submit">我要投稿</a><a href="/public-submissions">公开投稿</a><a href="/review-notices">审查公示</a>
            </nav>
            <div className="header-actions"><SessionAction /></div>
          </div>
        </header>
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
