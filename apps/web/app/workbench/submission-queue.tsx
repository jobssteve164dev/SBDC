import { ReviewPublicationControl } from "./review-publication-control";
import type { Locale } from "../i18n";

type Submission = {
  id: string; title: string; authors: string | null; reason: string;
  status: string; submitter_email: string; created_at: string; is_public: boolean;
  review_outcome: string | null; review_summary: string | null; review_published: boolean;
  terms_version: string | null; terms_locale: string | null; terms_accepted_at: string | null;
};

async function submissions(): Promise<{ items: Submission[]; available: boolean }> {
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/submissions`, {
      cache: "no-store",
      headers: { "X-SBDC-Internal-Secret": process.env.SBDC_INTERNAL_API_SECRET ?? "" },
    });
    return response.ok ? { items: await response.json(), available: true } : { items: [], available: false };
  } catch {
    return { items: [], available: false };
  }
}

export async function SubmissionQueue({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const { items, available } = await submissions();
  return (
    <section className="submission-queue" aria-labelledby="submission-queue-title">
      <div><p className="eyebrow">{en ? "Public submissions" : "公众投稿"}</p><h2 id="submission-queue-title">{en ? "Submitted papers" : "公众投稿论文"}</h2></div>
      {!available ? <p className="empty-state error-state" role="alert">{en ? "The submission queue could not be loaded. Please refresh." : "投稿队列暂时无法载入，请刷新重试。"}</p> : items.length === 0 ? <p className="empty-state">{en ? "There are no new public submissions." : "目前没有新的公众投稿。"}</p> : (
        <div className="queue-list">{items.map((item) => (
          <article key={item.id}>
            <div><span className="status-pill">{en ? "Received" : "已收件"}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString(locale)}</time></div>
            <h3>{item.title}</h3>
            {item.authors && <p>{en ? "Authors" : "作者"}：{item.authors}</p>}
            <p>{item.reason}</p>
            <p className="consent-evidence">{item.terms_accepted_at ? (en ? `Terms accepted · ${item.terms_version} · ${new Date(item.terms_accepted_at).toLocaleString("en-GB")}` : `已同意投稿条款 · ${item.terms_version} · ${new Date(item.terms_accepted_at).toLocaleString("zh-CN")}`) : (en ? "Submitted before terms evidence was introduced" : "提交时尚未启用新版条款留证")}</p>
            <footer><small>{en ? "Contact email (unverified)" : "联系邮箱（未经验证）"}：{item.submitter_email}</small><a href={`/backend/submissions/${item.id}/content`} target="_blank" rel="noreferrer">{en ? "View paper" : "查看论文"}</a></footer>
            <ReviewPublicationControl id={item.id} outcome={item.review_outcome} summary={item.review_summary} published={item.review_published} locale={locale} />
          </article>
        ))}</div>
      )}
    </section>
  );
}
