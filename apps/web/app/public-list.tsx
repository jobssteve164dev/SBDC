type PublicSubmission = { id: string; title: string; authors: string | null; reason: string; created_at: string };
type ReviewNotice = { id: string; title: string; authors: string | null; review_outcome: string; review_summary: string; review_published_at: string };
import type { Locale } from "./i18n";

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

export async function PublicSubmissionsList({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const { items, available } = await publicData<PublicSubmission>("/public/submissions/published");
  if (!available) return <p className="empty-state error-state" role="alert">{en ? "Public submissions are temporarily unavailable. Please refresh later." : "公开投稿暂时无法载入，请稍后刷新。"}</p>;
  if (!items.length) return <p className="empty-state">{en ? "There are no public submissions yet." : "目前还没有公开投稿。"}</p>;
  return <div className="public-card-list">{items.map((item) => <article key={item.id}>
    <div className="card-meta"><span>{en ? "Published by submitter choice" : "投稿人选择公开"}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString(locale)}</time></div>
    <h2>{item.title}</h2>{item.authors && <p className="card-authors">{en ? "Authors" : "作者"}：{item.authors}</p>}
    <p>{item.reason}</p><small>{en ? "Public content excludes the submitter's email and the paper file." : "公开内容不包括投稿人的联系邮箱和论文文件。"}</small>
  </article>)}</div>;
}

export async function ReviewNoticesList({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const labels = en ? { needs_further_review: "Further review advised", insufficient_evidence: "Evidence currently insufficient", no_issue_identified: "No clear issue identified" } : outcomeLabels;
  const { items, available } = await publicData<ReviewNotice>("/public/review-notices");
  if (!available) return <p className="empty-state error-state" role="alert">{en ? "Review notices are temporarily unavailable. Please refresh later." : "审查公示暂时无法载入，请稍后刷新。"}</p>;
  if (!items.length) return <p className="empty-state">{en ? "There are no published review outcomes yet." : "目前还没有审查结果公示。"}</p>;
  return <div className="public-card-list notice-list">{items.map((item) => <article key={item.id}>
    <div className="card-meta"><strong>{labels[item.review_outcome as keyof typeof labels] ?? (en ? "Review outcome" : "审查结果")}</strong><time dateTime={item.review_published_at}>{new Date(item.review_published_at).toLocaleDateString(locale)}</time></div>
    <h2>{item.title}</h2>{item.authors && <p className="card-authors">{en ? "Authors" : "作者"}：{item.authors}</p>}
    <p>{item.review_summary}</p><small>{en ? "This is a provisional outcome based on available material, not an institutional finding or attribution of responsibility." : "本公示是基于现有材料的待复核结论，不等同于机构调查或责任认定。"}</small>
  </article>)}</div>;
}
