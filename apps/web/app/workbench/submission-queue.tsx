type Submission = {
  id: string; title: string; authors: string | null; reason: string;
  status: string; submitter_email: string; created_at: string;
};

async function submissions(): Promise<{ items: Submission[]; available: boolean }> {
  try {
    const response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/submissions`, {
      cache: "no-store",
      headers: { "X-SBDC-Internal-Secret": process.env.SBDC_INTERNAL_API_SECRET ?? process.env.SBDC_SESSION_SECRET ?? "" },
    });
    return response.ok ? { items: await response.json(), available: true } : { items: [], available: false };
  } catch {
    return { items: [], available: false };
  }
}

export async function SubmissionQueue() {
  const { items, available } = await submissions();
  return (
    <section className="submission-queue" aria-labelledby="submission-queue-title">
      <div><p className="eyebrow">公众投稿</p><h2 id="submission-queue-title">待核查论文</h2></div>
      {!available ? <p className="empty-state error-state" role="alert">投稿队列暂时无法载入，请刷新重试。</p> : items.length === 0 ? <p className="empty-state">目前没有新的公众投稿。</p> : (
        <div className="queue-list">{items.map((item) => (
          <article key={item.id}>
            <div><span className="status-pill">已收件</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString("zh-CN")}</time></div>
            <h3>{item.title}</h3>
            {item.authors && <p>作者：{item.authors}</p>}
            <p>{item.reason}</p>
            <footer><small>提交账号（邮箱未验证）：{item.submitter_email}</small><a href={`/backend/submissions/${item.id}/content`} target="_blank" rel="noreferrer">查看论文</a></footer>
          </article>
        ))}</div>
      )}
    </section>
  );
}
