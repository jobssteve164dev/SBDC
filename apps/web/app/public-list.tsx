type PublicSubmission = { id: string; title: string; authors: string | null; reason: string; created_at: string };
type ReviewNotice = { id: string; title: string; authors: string | null; review_outcome: string; review_summary: string; review_published_at: string };

const outcomeLabels: Record<string, string> = {
  needs_further_review: "建议进一步复核",
  insufficient_evidence: "现有证据不足",
  no_issue_identified: "暂未发现明确问题",
};

async function publicData<T>(path: string): Promise<{ items: T[]; available: boolean }> {
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}${path}`, { cache: "no-store" });
    return response.ok ? { items: await response.json(), available: true } : { items: [], available: false };
  } catch { return { items: [], available: false }; }
}

export async function PublicSubmissionsList() {
  const { items, available } = await publicData<PublicSubmission>("/public/submissions/published");
  if (!available) return <p className="empty-state error-state" role="alert">公开投稿暂时无法载入，请稍后刷新。</p>;
  if (!items.length) return <p className="empty-state">目前还没有公开投稿。</p>;
  return <div className="public-card-list">{items.map((item) => <article key={item.id}>
    <div className="card-meta"><span>投稿人选择公开</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString("zh-CN")}</time></div>
    <h2>{item.title}</h2>{item.authors && <p className="card-authors">作者：{item.authors}</p>}
    <p>{item.reason}</p><small>公开内容不包括投稿人的联系邮箱和论文文件。</small>
  </article>)}</div>;
}

export async function ReviewNoticesList() {
  const { items, available } = await publicData<ReviewNotice>("/public/review-notices");
  if (!available) return <p className="empty-state error-state" role="alert">审查公示暂时无法载入，请稍后刷新。</p>;
  if (!items.length) return <p className="empty-state">目前还没有审查结果公示。</p>;
  return <div className="public-card-list notice-list">{items.map((item) => <article key={item.id}>
    <div className="card-meta"><strong>{outcomeLabels[item.review_outcome] ?? "审查结果"}</strong><time dateTime={item.review_published_at}>{new Date(item.review_published_at).toLocaleDateString("zh-CN")}</time></div>
    <h2>{item.title}</h2>{item.authors && <p className="card-authors">作者：{item.authors}</p>}
    <p>{item.review_summary}</p><small>本公示是基于现有材料的待复核结论，不等同于机构调查或责任认定。</small>
  </article>)}</div>;
}
