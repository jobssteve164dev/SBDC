import type { Metadata } from "next";

import { pageTitle } from "../brand";
import { PublicSubmission } from "./public-submission";

export const metadata: Metadata = {
  title: pageTitle("提交待核查论文"),
  description: "提交你希望由科研诚信审查者核查的论文。",
};

export default function SubmitPage() {
  return (
    <main className="submit-shell" id="main-content">
      <section className="submit-intro">
        <p className="eyebrow">公众科研监督投稿</p>
        <h1>把值得核查的论文，交到审查者手中。</h1>
        <p>请提交你有权提供的论文 PDF，并说明希望核查的具体原因。收到投稿不代表论文存在问题，也不代表一定进入正式调查。</p>
        <div className="submit-boundaries"><p><strong>我们会做</strong><span>保存投稿、确认收件、交由获授权审查者评估。</span></p><p><strong>我们不会做</strong><span>公开投稿人信息，或仅凭自动结果给作者定性。</span></p></div>
      </section>
      <PublicSubmission />
    </main>
  );
}
