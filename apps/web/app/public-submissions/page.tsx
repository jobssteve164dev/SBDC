import type { Metadata } from "next";
import { PublicSubmissionsList } from "../public-list";

export const metadata: Metadata = { title: "公开投稿 · 科研诚信证据核查平台" };

export default function PublicSubmissionsPage() {
  return <main className="public-index" id="main-content">
    <header><p className="eyebrow">Public submissions</p><h1>公开投稿论文</h1><p>这里只展示投稿人主动选择公开的题名、作者与核查理由。公开不代表论文存在问题，也不代表平台已接受其主张。</p></header>
    <PublicSubmissionsList />
  </main>;
}
