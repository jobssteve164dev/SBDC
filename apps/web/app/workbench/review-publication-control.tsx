"use client";

import { FormEvent, useState } from "react";

type Props = { id: string; outcome: string | null; summary: string | null; published: boolean };

export function ReviewPublicationControl({ id, outcome, summary, published }: Props) {
  const [isPublished, setPublished] = useState(published);
  const [message, setMessage] = useState(published ? "当前已在审查公示页展示" : "");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); setFailed(false);
    const form = new FormData(event.currentTarget);
    form.set("publish", isPublished ? "false" : "true");
    try {
      const response = await fetch(`/backend/submissions/${id}/publication`, { method: "POST", body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? "保存失败，请稍后重试");
      setPublished(payload.review_published);
      setMessage(payload.review_published ? "已发布到审查公示页" : "已从审查公示页撤下");
    } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "保存失败，请稍后重试"); }
    finally { setBusy(false); }
  }

  return <form className="publication-form" onSubmit={save}>
    <label>审查结果<select name="review_outcome" defaultValue={outcome ?? "insufficient_evidence"}>
      <option value="needs_further_review">建议进一步复核</option>
      <option value="insufficient_evidence">现有证据不足</option>
      <option value="no_issue_identified">暂未发现明确问题</option>
    </select></label>
    <label>公示说明<textarea name="review_summary" defaultValue={summary ?? ""} minLength={10} maxLength={2000} required rows={3} placeholder="说明依据、结论与当前材料边界" /></label>
    {message && <p className={failed ? "error" : ""} role={failed ? "alert" : "status"}>{message}</p>}
    <button type="submit" disabled={busy}>{busy ? "正在保存…" : isPublished ? "撤下审查公示" : "发布到审查公示"}</button>
  </form>;
}
