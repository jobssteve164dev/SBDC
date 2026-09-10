"use client";

import { FormEvent, useState } from "react";

type Submission = { id: string; title: string; status: string };

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/backend/public${path}`, init);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail ?? "暂时无法完成，请稍后重试");
  return payload;
}

export function PublicSubmission() {
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true); setMessage(""); setFailed(false);
    try {
      const item = await request("/submissions", { method: "POST", body: new FormData(form) }) as Submission;
      form.reset();
      setMessage(`投稿已收到，凭证号：${item.id}`);
    } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "暂时无法提交"); }
    finally { setBusy(false); }
  }

  return (
    <section className="public-form-card" aria-labelledby="submission-title">
      <h2 id="submission-title">提交待核查论文</h2>
      <p className="form-help">无需注册。联系邮箱仅用于确认材料或反馈进展，不会在公开页面展示。</p>
      <form onSubmit={submit}>
        <label>联系邮箱<input name="contact_email" type="email" autoComplete="email" required maxLength={254} /></label>
        <label>论文题名<input name="title" required minLength={2} maxLength={500} /></label>
        <label>作者（选填）<input name="authors" maxLength={1000} /></label>
        <label>希望核查的原因<textarea name="reason" required minLength={10} maxLength={4000} rows={6} /></label>
        <label className="file-field">论文 PDF<input name="file" type="file" accept="application/pdf,.pdf" required /><small>最大 50 MB、500 页；不接受加密或损坏文件。</small></label>
        <label className="check-field public-choice"><input name="is_public" type="checkbox" value="true" /><span><strong>公开这条投稿</strong><small>勾选后，论文题名、作者和投稿理由会出现在公开投稿页面；邮箱和论文文件始终不会公开。</small></span></label>
        <label className="check-field"><input name="rights_confirmed" type="checkbox" value="true" required /><span>我确认有权提交此文件用于科研诚信审查，并已阅读隐私政策。</span></label>
        {message && <p className={`form-message${failed ? " error" : ""}`} role={failed ? "alert" : "status"}>{message}</p>}
        <button className="primary-button" disabled={busy}>{busy ? "正在提交…" : "确认投稿"}</button>
      </form>
    </section>
  );
}
