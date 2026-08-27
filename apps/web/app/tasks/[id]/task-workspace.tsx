"use client";

import { useCallback, useEffect, useState } from "react";

type Location = { page: number | null; bbox: number[] | null };
type Section = Location & { ordinal: number; heading: string; paragraphs: Array<Location & { text: string }> };
type Reference = Location & {
  id: string; ordinal: number; raw_citation: string; title: string | null; authors: string[];
  year: string | null; venue: string | null; doi: string | null; parse_status: string; failure_reason: string | null;
};
type Task = {
  id: string; status: string; stage_message: string; error_message: string | null;
  coverage_summary: Record<string, number | Record<string, number>>;
  source_asset: { id: string; sha256: string; size_bytes: number; page_count: number } | null;
  document: { title: string | null; authors: string[]; abstract: string | null; sections: Section[]; parser_version: string | null } | null;
  references: Reference[];
};

const terminal = new Set(["references_ready", "validation_failed", "parsing_failed"]);
const failureText: Record<string, string> = { bibliographic_fields_missing: "未识别出足够的书目信息" };

export function TaskWorkspace({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"structure" | "references">("structure");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    const response = await fetch(`/backend/tasks/${taskId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 404 ? "检查任务不存在" : "暂时无法读取检查进度");
    const next = (await response.json()) as Task;
    setTask(next);
    setLoadError(null);
    return next;
  }, [taskId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const next = await load();
        if (!cancelled && !terminal.has(next.status)) timer = setTimeout(poll, 1500);
      } catch (reason) {
        if (!cancelled) {
          setLoadError(reason instanceof Error ? reason.message : "暂时无法读取检查进度");
          timer = setTimeout(poll, 3000);
        }
      }
    }
    void poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [load]);

  async function retry() {
    setLoadError(null);
    const response = await fetch(`/backend/tasks/${taskId}/parse`, { method: "POST" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as { detail?: string };
      setLoadError(data.detail ?? "暂时无法重新解析");
      return;
    }
    await load();
  }

  const pdfUrl = task?.source_asset
    ? `/backend/tasks/${task.id}/assets/${task.source_asset.id}/content#page=${page}&view=FitH`
    : null;

  if (!task) {
    return <main className="loading-screen"><div className="spinner" /><p>{loadError ?? "正在读取检查进度…"}</p></main>;
  }

  const complete = task.status === "references_ready";
  const failed = task.status.endsWith("_failed");
  const coverage = task.coverage_summary;
  const total = Number(coverage.references_total ?? 0);
  const parsed = Number(coverage.references_parsed ?? 0);
  const failedRefs = Number(coverage.references_failed ?? 0);
  const sections = Number(coverage.body_sections ?? 0);
  const located = Number(coverage.located_sections ?? 0);

  return (
    <main className="workspace-shell">
      <div className="workspace-topline">
        <a href="/" className="back-link">← 新建检查</a>
        {task.source_asset && <span className="asset-fingerprint">文件校验 {task.source_asset.sha256.slice(0, 12)}…</span>}
      </div>

      {!complete && (
        <section className={`progress-panel ${failed ? "failed" : ""}`} aria-live="polite">
          <div className={failed ? "status-cross" : "spinner"}>{failed ? "!" : ""}</div>
          <div>
            <p className="eyebrow">{failed ? "需要处理" : "检查进行中"}</p>
            <h1>{task.stage_message}</h1>
            {failed ? <p>{task.error_message}</p> : <p>页面会自动更新，可以保持打开。</p>}
            {(task.status === "parsing_failed") && <button type="button" className="secondary-button" onClick={retry}>重新解析</button>}
            {loadError && <p className="form-error">{loadError}</p>}
          </div>
        </section>
      )}

      {complete && task.document && (
        <>
          <section className="paper-heading">
            <p className="eyebrow">解析结果</p>
            <h1>{task.document.title || "未识别到论文题名"}</h1>
            <p className="authors">{task.document.authors.length ? task.document.authors.join(" · ") : "未识别到作者信息"}</p>
            {task.document.abstract && <p className="abstract">{task.document.abstract}</p>}
          </section>

          <section className="coverage-grid" aria-label="实际解析覆盖率">
            <article><span>参考文献</span><strong>{total}</strong><small>识别总数</small></article>
            <article><span>成功解析</span><strong>{parsed}</strong><small>{total ? `${Math.round(parsed / total * 100)}%` : "暂无引用"}</small></article>
            <article><span>解析失败</span><strong>{failedRefs}</strong><small>{failedRefs ? "原因见引用清单" : "无"}</small></article>
            <article><span>正文定位</span><strong>{located}/{sections}</strong><small>已定位章节</small></article>
          </section>

          <section className="review-grid">
            <div className="result-panel">
              <div className="tabs" role="tablist">
                <button role="tab" aria-selected={activeTab === "structure"} className={activeTab === "structure" ? "active" : ""} onClick={() => setActiveTab("structure")}>正文结构 <span>{sections}</span></button>
                <button role="tab" aria-selected={activeTab === "references"} className={activeTab === "references" ? "active" : ""} onClick={() => setActiveTab("references")}>参考文献 <span>{total}</span></button>
              </div>
              {activeTab === "structure" ? (
                <div className="result-list">
                  {task.document.sections.map((section) => (
                    <article className="result-item" key={section.ordinal}>
                      <div className="item-number">{String(section.ordinal).padStart(2, "0")}</div>
                      <div>
                        <h3>{section.heading}</h3>
                        {section.paragraphs[0]?.text && <p>{section.paragraphs[0].text}</p>}
                      </div>
                      {section.page ? <button className="page-link" onClick={() => setPage(section.page!)}>第 {section.page} 页 ↗</button> : <span className="not-located">位置未识别</span>}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="result-list">
                  {task.references.map((reference) => (
                    <article className={`result-item reference ${reference.parse_status === "failed" ? "item-failed" : ""}`} key={reference.id}>
                      <div className="item-number">{reference.ordinal}</div>
                      <div>
                        <h3>{reference.title || reference.raw_citation}</h3>
                        {reference.title && <p>{[reference.authors.join(", "), reference.venue, reference.year].filter(Boolean).join(" · ")}</p>}
                        {reference.failure_reason && <small className="failure-reason">{failureText[reference.failure_reason] ?? "书目信息解析失败"}</small>}
                        {reference.doi && <small className="doi">DOI {reference.doi}</small>}
                      </div>
                      {reference.page ? <button className="page-link" onClick={() => setPage(reference.page!)}>第 {reference.page} 页 ↗</button> : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
            <aside className="pdf-panel">
              <div className="pdf-toolbar"><strong>原文</strong><span>第 {page} 页</span></div>
              {pdfUrl && <iframe key={pdfUrl} src={pdfUrl} title={`论文原文，第 ${page} 页`} />}
            </aside>
          </section>
          <p className="result-boundary">当前结果仅表示结构化解析覆盖范围，不构成对论文科研诚信的判断。</p>
        </>
      )}
    </main>
  );
}
