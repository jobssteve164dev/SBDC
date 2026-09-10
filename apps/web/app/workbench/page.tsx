import type { Metadata } from "next";

import { UploadPaper } from "../upload-paper";
import { SubmissionQueue } from "./submission-queue";

export const metadata: Metadata = { title: "审查工作台 · 科研诚信证据核查平台" };

export default function WorkbenchPage() {
  return (
    <main className="home-shell" id="main-content">
      <section className="hero">
        <p className="eyebrow">从原文开始复核</p>
        <h1>看清论文结构与引用，<br />再作判断。</h1>
        <p className="hero-copy">上传一篇 PDF，我们会解析论文题名、正文结构和参考文献，并标明实际覆盖范围。所有结果都能回到原文位置核对。</p>
      </section>
      <UploadPaper />
      <section className="trust-row" aria-label="处理边界">
        <div><strong>任务内处理</strong><span>论文只用于当前检查</span></div>
        <div><strong>不做自动定性</strong><span>解析结果需要人工复核</span></div>
        <div><strong>真实覆盖范围</strong><span>失败与缺失会如实显示</span></div>
      </section>
      <SubmissionQueue />
    </main>
  );
}
