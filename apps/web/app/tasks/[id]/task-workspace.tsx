"use client";

import { useCallback, useEffect, useState } from "react";
import type { Locale } from "../../i18n";
import { pathFor } from "../../i18n";

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

export function TaskWorkspace({ taskId, locale }: { taskId: string; locale: Locale }) {
  const en = locale === "en";
  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"structure" | "references">("structure");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    const response = await fetch(`/backend/tasks/${taskId}`, { cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 404 ? (en ? "Review task not found" : "检查任务不存在") : (en ? "Review progress is temporarily unavailable" : "暂时无法读取检查进度"));
    const next = (await response.json()) as Task;
    setTask(next);
    setLoadError(null);
    return next;
  }, [taskId, en]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const next = await load();
        if (!cancelled && !terminal.has(next.status)) timer = setTimeout(poll, 1500);
      } catch (reason) {
        if (!cancelled) {
          setLoadError(en ? "Review progress is temporarily unavailable" : reason instanceof Error ? reason.message : "暂时无法读取检查进度");
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
      setLoadError(en ? "The parser could not be restarted" : data.detail ?? "暂时无法重新解析");
      return;
    }
    await load();
  }

  const pdfUrl = task?.source_asset
    ? `/backend/tasks/${task.id}/assets/${task.source_asset.id}/content#page=${page}&view=FitH`
    : null;

  if (!task) {
    return <main className="loading-screen" id="main-content"><div className="spinner" /><p>{loadError ?? (en ? "Loading review progress…" : "正在读取检查进度…")}</p></main>;
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
    <main className="workspace-shell" id="main-content">
      <div className="workspace-topline">
        <a href={pathFor(locale, "/")} className="back-link">← {en ? "New review" : "新建检查"}</a>
        {task.source_asset && <span className="asset-fingerprint">{en ? "File checksum" : "文件校验"} {task.source_asset.sha256.slice(0, 12)}…</span>}
      </div>

      {!complete && (
        <section className={`progress-panel ${failed ? "failed" : ""}`} aria-live="polite">
          <div className={failed ? "status-cross" : "spinner"}>{failed ? "!" : ""}</div>
          <div>
            <p className="eyebrow">{failed ? (en ? "Action needed" : "需要处理") : (en ? "Review in progress" : "检查进行中")}</p>
            <h1>{en ? ({ created: "Waiting for paper upload", uploaded: "Paper uploaded", parsing: "Parsing paper structure and references", references_ready: "Parsing complete", validation_failed: "The PDF could not be validated", parsing_failed: "Parsing failed" }[task.status] ?? "Processing paper") : task.stage_message}</h1>
            {failed ? <p>{en ? "The paper could not be processed. Review the file and try again." : task.error_message}</p> : <p>{en ? "This page updates automatically; you can leave it open." : "页面会自动更新，可以保持打开。"}</p>}
            {(task.status === "parsing_failed") && <button type="button" className="secondary-button" onClick={retry}>{en ? "Parse again" : "重新解析"}</button>}
            {loadError && <p className="form-error">{loadError}</p>}
          </div>
        </section>
      )}

      {complete && task.document && (
        <>
          <section className="paper-heading">
            <p className="eyebrow">{en ? "Parsed result" : "解析结果"}</p>
            <h1>{task.document.title || (en ? "Paper title not identified" : "未识别到论文题名")}</h1>
            <p className="authors">{task.document.authors.length ? task.document.authors.join(" · ") : (en ? "Author information not identified" : "未识别到作者信息")}</p>
            {task.document.abstract && <p className="abstract">{task.document.abstract}</p>}
          </section>

          <section className="coverage-grid" aria-label={en ? "Actual parsing coverage" : "实际解析覆盖率"}>
            <article><span>{en ? "References" : "参考文献"}</span><strong>{total}</strong><small>{en ? "identified" : "识别总数"}</small></article>
            <article><span>{en ? "Parsed" : "成功解析"}</span><strong>{parsed}</strong><small>{total ? `${Math.round(parsed / total * 100)}%` : (en ? "No references" : "暂无引用")}</small></article>
            <article><span>{en ? "Failed" : "解析失败"}</span><strong>{failedRefs}</strong><small>{failedRefs ? (en ? "See reference list" : "原因见引用清单") : (en ? "None" : "无")}</small></article>
            <article><span>{en ? "Body locations" : "正文定位"}</span><strong>{located}/{sections}</strong><small>{en ? "sections located" : "已定位章节"}</small></article>
          </section>

          <section className="review-grid">
            <div className="result-panel">
              <div className="tabs" role="tablist">
                <button role="tab" aria-selected={activeTab === "structure"} className={activeTab === "structure" ? "active" : ""} onClick={() => setActiveTab("structure")}>{en ? "Paper structure" : "正文结构"} <span>{sections}</span></button>
                <button role="tab" aria-selected={activeTab === "references"} className={activeTab === "references" ? "active" : ""} onClick={() => setActiveTab("references")}>{en ? "References" : "参考文献"} <span>{total}</span></button>
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
                      {section.page ? <button className="page-link" onClick={() => setPage(section.page!)}>{en ? `Page ${section.page}` : `第 ${section.page} 页`} ↗</button> : <span className="not-located">{en ? "Location not identified" : "位置未识别"}</span>}
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
                        {reference.failure_reason && <small className="failure-reason">{en ? "Bibliographic parsing failed" : failureText[reference.failure_reason] ?? "书目信息解析失败"}</small>}
                        {reference.doi && <small className="doi">DOI {reference.doi}</small>}
                      </div>
                      {reference.page ? <button className="page-link" onClick={() => setPage(reference.page!)}>{en ? `Page ${reference.page}` : `第 ${reference.page} 页`} ↗</button> : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
            <aside className="pdf-panel">
              <div className="pdf-toolbar"><strong>{en ? "Source PDF" : "原文"}</strong><span>{en ? `Page ${page}` : `第 ${page} 页`}</span></div>
              {pdfUrl && <iframe key={pdfUrl} src={pdfUrl} title={en ? `Paper source, page ${page}` : `论文原文，第 ${page} 页`} />}
            </aside>
          </section>
          <p className="result-boundary">{en ? "These results show structured parsing coverage only and are not a research integrity determination." : "当前结果仅表示结构化解析覆盖范围，不构成对论文科研诚信的判断。"}</p>
        </>
      )}
    </main>
  );
}
