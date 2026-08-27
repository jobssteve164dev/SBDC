import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SBDC · 论文证据工作台",
  description: "解析论文结构和参考文献，形成可回到原文复核的检查基础。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site-header">
          <a className="brand" href="/" aria-label="返回 SBDC 首页">
            <span className="brand-mark">S</span>
            <span>SBDC</span>
          </a>
          <span className="header-note">论文证据工作台</span>
        </header>
        {children}
      </body>
    </html>
  );
}
