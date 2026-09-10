import type { Metadata } from "next";
import { ReviewNoticesList } from "../public-list";

export const metadata: Metadata = { title: "审查公示 · 科研诚信证据核查平台" };

export default function ReviewNoticesPage() {
  return <main className="public-index" id="main-content">
    <header><p className="eyebrow">Review notices</p><h1>审查结果公示</h1><p>审查者可基于已核查材料选择公开结果摘要。每条公示都明确当前证据边界，不以自动分析替代人工判断。</p></header>
    <ReviewNoticesList />
  </main>;
}
