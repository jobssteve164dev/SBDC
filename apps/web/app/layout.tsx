import type { Metadata } from "next";
import "./globals.css";
import { SessionAction } from "./session-action";
import { SiteFooter } from "./site-footer";

export const metadata: Metadata = {
  title: "SBDC · 论文证据工作台",
  description: "解析论文结构和参考文献，形成可回到原文复核的检查基础。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <header className="site-header">
          <a className="brand" href="/" aria-label="返回 SBDC 首页">
            <span className="brand-mark">S</span>
            <span>SBDC</span>
          </a>
          <div className="header-actions">
            <a className="header-note" href="/submit">公众投稿</a>
            <SessionAction />
          </div>
        </header>
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
