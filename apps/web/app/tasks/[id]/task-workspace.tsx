"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Locale } from "../../i18n";
import { pathFor } from "../../i18n";

type Location = { page: number | null; bbox: number[] | null };
type Section = Location & { ordinal: number; heading: string; paragraphs: Array<Location & { text: string }> };
type Reference = Location & {
  id: string; ordinal: number; raw_citation: string; title: string | null; authors: string[];
  year: string | null; venue: string | null; doi: string | null; parse_status: string; failure_reason: string | null;
  metadata_status: string; full_text_status: string; full_text_asset_id: string | null; access_url: string | null;
};
type Task = {
  id: string; status: string; stage_message: string; error_message: string | null;
  coverage_summary: Record<string, unknown>;
  source_asset: { id: string; sha256: string; size_bytes: number; page_count: number } | null;
  document: { title: string | null; authors: string[]; abstract: string | null; sections: Section[]; parser_version: string | null } | null;
  references: Reference[];
  report_asset: { id: string } | null;
};

type Decision = { decision: string; reason: string };
type Evidence = {
  id: string; code: string; status: string; severity: string; confidence: number;
  subject_location: { document_id: string; page: number | null; bbox: number[] | null };
  source_location: { document_id: string; page: number | null; bbox: number[] | null } | null;
  subject_excerpt: string; source_excerpt: string | null; explanation: string; limitations: string[]; decision: Decision | null;
};

const terminal = new Set(["review_ready", "reviewed", "completed", "purged", "purge_failed", "validation_failed", "parsing_failed", "checking_failed"]);
const failureText: Record<string, [string, string]> = {
  bibliographic_fields_missing: ["未识别出足够的书目信息", "Insufficient bibliographic information"],
  open_full_text_unavailable_or_invalid: ["开放全文无法安全读取", "The open copy could not be read safely"],
};
const fullTextStatus: Record<string, [string, string]> = {
  not_checked: ["等待检查", "Pending"], available: ["已找到开放全文", "Open copy found"],
  obtained: ["已取得并进入检查", "Obtained and checked"], not_open_access: ["未发现合法开放全文", "No lawful open copy found"],
  identifier_missing: ["缺少稳定标识，未能定位全文", "No stable identifier for full-text lookup"],
  metadata_unavailable: ["书目信息不足", "Bibliographic metadata unavailable"], oa_lookup_failed: ["开放来源查询失败，可重试", "Open-source lookup failed; retry available"],
  download_failed: ["开放全文无法安全读取", "Open copy could not be read safely"], purged: ["临时全文已清理", "Temporary full text cleared"],
  obtained_no_text: ["已取得，但没有可提取文本", "Obtained, but no extractable text"],
  budget_exceeded: ["超出本任务处理上限，未进入对照", "Skipped because this task reached its processing limit"],
};
const evidenceTitle: Record<string, [string, string]> = {
  cross_condition_subject_mismatch: ["不同条件的结果来自不同研究对象", "Different conditions use different study subjects"],
  measurement_condition_inconsistency: ["同一数值结果关联多个条件标签", "One result is linked to multiple condition labels"],
  data_not_directly_available: ["关键原始数据未直接提供", "Key raw data are not directly available"],
  embedded_image_reuse_candidate: ["PDF 内出现相同位图候选", "An identical embedded bitmap appears more than once"],
  reference_text_reuse_candidate: ["与引用来源存在连续文本重合", "Continuous text overlaps a cited source"],
  reference_semantic_similarity_candidate: ["与引用来源存在语义近似候选", "Semantically similar wording appears in a cited source"],
  citation_numeric_mismatch_candidate: ["引用论断与来源数值需要核对", "A cited claim and source value need review"],
  citation_direction_conflict_candidate: ["引用论断与来源方向需要核对", "A cited claim and source direction need review"],
  statistical_threshold_uncertainty: ["统计阈值在不确定度范围内需要复核", "A statistical threshold needs uncertainty review"],
  statistical_average_inconsistency: ["报告平均值与所列数值不一致", "A reported average differs from the listed values"],
  image_region_reuse_candidate: ["图片内存在局部区域复用候选", "A figure contains a repeated-region candidate"],
};

export function TaskWorkspace({ taskId, locale }: { taskId: string; locale: Locale }) {
  const en = locale === "en";
  const [task, setTask] = useState<Task | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"evidence" | "structure" | "references">("structure");
  const [page, setPage] = useState(1);
  const [decisionDrafts, setDecisionDrafts] = useState<Record<string, Decision>>({});
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [activePdfAssetId, setActivePdfAssetId] = useState<string | null>(null);
  const checksStarted = useRef(false);

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

  useEffect(() => {
    if (task?.status !== "references_ready" || checksStarted.current) return;
    checksStarted.current = true;
    void fetch(`/backend/tasks/${taskId}/checks`, { method: "POST" })
      .then(async (response) => {
        if (!response.ok) {
          const data = await response.json().catch(() => ({})) as { detail?: string };
          throw new Error(data.detail ?? (en ? "The deep review could not start" : "深度检查未能启动"));
        }
        return load();
      })
      .catch((reason) => setLoadError(reason instanceof Error ? reason.message : (en ? "The deep review could not start" : "深度检查未能启动")));
  }, [task?.status, taskId, en, load]);

  useEffect(() => {
    if (!task || !["review_ready", "reviewed", "completed", "retention_pending", "purged", "purge_failed"].includes(task.status)) return;
    void fetch(`/backend/tasks/${taskId}/evidence`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(en ? "Evidence is temporarily unavailable" : "暂时无法读取证据");
        const items = (await response.json()) as Evidence[];
        setEvidence(items);
        setActiveTab("evidence");
        setDecisionDrafts(Object.fromEntries(items.map((item) => [item.id, item.decision ?? { decision: "", reason: "" }])));
      })
      .catch((reason) => setLoadError(reason instanceof Error ? reason.message : (en ? "Evidence is temporarily unavailable" : "暂时无法读取证据")));
  }, [task?.status, taskId, en]);

  useEffect(() => {
    if (task?.status === "purged" && task.source_asset) {
      setActivePdfAssetId(task.source_asset.id);
      setPage(1);
    }
  }, [task?.status, task?.source_asset]);

  async function retry() {
    setLoadError(null);
    const endpoint = task?.status === "checking_failed" ? "checks" : "parse";
    if (endpoint === "checks") checksStarted.current = true;
    const response = await fetch(`/backend/tasks/${taskId}/${endpoint}`, { method: "POST" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as { detail?: string };
      setLoadError(en ? "The parser could not be restarted" : data.detail ?? "暂时无法重新解析");
      return;
    }
    await load();
  }

  async function saveDecision(item: Evidence) {
    const draft = decisionDrafts[item.id];
    if (!draft?.decision || draft.reason.trim().length < 10) {
      setLoadError(en ? "Choose a decision and add a specific reason" : "请选择复核决定，并填写至少 10 个字符的理由");
      return;
    }
    const response = await fetch(`/backend/evidence/${item.id}/decisions`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as { detail?: string };
      setLoadError(data.detail ?? (en ? "The decision could not be saved" : "复核决定未能保存"));
      return;
    }
    setLoadError(null);
    const nextTask = await load();
    const refreshed = await fetch(`/backend/tasks/${taskId}/evidence`, { cache: "no-store" });
    if (refreshed.ok) setEvidence(await refreshed.json() as Evidence[]);
    if (nextTask.status === "reviewed") setActiveTab("evidence");
  }

  async function generateReport() {
    const response = await fetch(`/backend/tasks/${taskId}/reports`, { method: "POST" });
    const data = await response.json().catch(() => ({})) as { detail?: string; download_url?: string };
    if (!response.ok || !data.download_url) {
      setLoadError(data.detail ?? (en ? "The report could not be generated" : "报告未能生成"));
      return;
    }
    setReportUrl(data.download_url);
    setLoadError(null);
    await load();
  }

  async function purgeTemporaryAssets() {
    const response = await fetch(`/backend/tasks/${taskId}/retention`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "purge_temporary" }),
    });
    const data = await response.json().catch(() => ({})) as { detail?: string; status?: string };
    if (!response.ok) {
      setLoadError(data.detail ?? (en ? "Temporary materials could not be cleared" : "临时材料未能清理"));
      return;
    }
    setLoadError(data.status === "purge_failed" ? (en ? "Some temporary materials could not be cleared; retry is available." : "部分临时材料清理失败，可以安全重试。") : null);
    await load();
  }

  const displayedAssetId = activePdfAssetId ?? task?.source_asset?.id;
  const pdfUrl = task && displayedAssetId
    ? `/backend/tasks/${task.id}/assets/${displayedAssetId}/content#page=${page}&view=FitH`
    : null;

  if (!task) {
    return <main className="loading-screen" id="main-content"><div className="spinner" /><p>{loadError ?? (en ? "Loading review progress…" : "正在读取检查进度…")}</p></main>;
  }

  const parsedReady = ["references_ready", "fetching_sources", "indexing", "checking", "checking_failed", "review_ready", "reviewed", "reporting", "completed", "retention_pending", "purged", "purge_failed"].includes(task.status);
  const reviewing = ["review_ready", "reviewed", "completed", "retention_pending", "purged", "purge_failed"].includes(task.status);
  const failed = task.status.endsWith("_failed");
  const coverage = task.coverage_summary;
  const total = Number(coverage.references_total ?? 0);
  const refsParsed = Number(coverage.references_parsed ?? 0);
  const failedRefs = Number(coverage.references_failed ?? 0);
  const fullTexts = Number(coverage.reference_full_texts_obtained ?? 0);
  const comparedFullTexts = Number(coverage.reference_full_texts_compared ?? 0);
  const lexicalComparisons = Number(coverage.reference_candidate_comparisons ?? 0);
  const lexicalBudget = Number(coverage.reference_candidate_budget ?? 0);
  const comparisonBudgetExhausted = [
    coverage.reference_candidate_budget_exhausted,
    coverage.semantic_candidate_budget_exhausted,
    coverage.citation_candidate_budget_exhausted,
    coverage.statistical_review_budget_exhausted,
    coverage.image_region_budget_exhausted,
    coverage.image_resource_budget_exhausted,
  ].some((value) => Number(value ?? 0) === 1);
  const semanticCandidates = Number(coverage.semantic_similarity_candidates ?? 0);
  const semanticComparisons = Number(coverage.semantic_candidate_comparisons ?? 0);
  const semanticBudget = Number(coverage.semantic_candidate_budget ?? 0);
  const citationContexts = Number(coverage.citation_contexts_detected ?? 0);
  const citationMatches = Number(coverage.citation_support_matches ?? 0);
  const citationComparisons = Number(coverage.citation_candidate_comparisons ?? 0);
  const citationBudget = Number(coverage.citation_candidate_budget ?? 0);
  const statisticalMentions = Number(coverage.statistical_mentions_detected ?? 0);
  const statisticalRecomputed = Number(coverage.statistical_mentions_recomputed ?? 0);
  const statisticalThresholds = Number(coverage.statistical_threshold_claims_examined ?? 0);
  const statisticalThresholdBudget = Number(coverage.statistical_threshold_claim_budget ?? 0);
  const statisticalAverages = Number(coverage.statistical_average_claims_examined ?? 0);
  const statisticalAverageBudget = Number(coverage.statistical_average_claim_budget ?? 0);
  const statisticalListComparisons = Number(coverage.statistical_value_list_comparisons ?? 0);
  const statisticalListBudget = Number(coverage.statistical_value_list_comparison_budget ?? 0);
  const imageComparisons = Number(coverage.image_regions_compared ?? 0);
  const imageCandidates = Number(coverage.image_region_reuse_candidates ?? 0);
  const imageBudget = Number(coverage.image_region_comparison_budget ?? 0);
  const imageSkipped = Math.max(
    Number(coverage.advanced_images_skipped_resource_limit ?? 0),
    Number(coverage.embedded_images_skipped_resource_limit ?? 0),
  );
  const imageSampled = Number(coverage.image_tile_sampling_adjusted ?? 0);
  const imageDecodedPixels = Number(coverage.image_task_decoded_pixels ?? 0);
  const imageDecodedPixelBudget = Number(coverage.image_task_decoded_pixel_budget ?? 0);
  const imageTiles = Number(coverage.image_tiles_generated ?? 0);
  const imageTileBudget = Number(coverage.image_task_tile_budget ?? 0);
  const sections = Number(coverage.body_sections ?? 0);
  const located = Number(coverage.located_sections ?? 0);

  return (
    <main className="workspace-shell" id="main-content">
      <div className="workspace-topline">
        <a href={pathFor(locale, "/")} className="back-link">← {en ? "New review" : "新建检查"}</a>
        {task.source_asset && <span className="asset-fingerprint">{en ? "File checksum" : "文件校验"} {task.source_asset.sha256.slice(0, 12)}…</span>}
      </div>

      {!parsedReady && (
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

      {parsedReady && task.document && (
        <>
          <section className="paper-heading">
            <p className="eyebrow">{en ? "Parsed result" : "解析结果"}</p>
            <h1>{task.document.title || (en ? "Paper title not identified" : "未识别到论文题名")}</h1>
            <p className="authors">{task.document.authors.length ? task.document.authors.join(" · ") : (en ? "Author information not identified" : "未识别到作者信息")}</p>
            {task.document.abstract && <p className="abstract">{task.document.abstract}</p>}
          </section>

          <section className="coverage-grid" aria-label={en ? "Actual parsing coverage" : "实际解析覆盖率"}>
            <article><span>{en ? "References" : "参考文献"}</span><strong>{total}</strong><small>{en ? "identified" : "识别总数"}</small></article>
            <article><span>{en ? "Parsed" : "成功解析"}</span><strong>{refsParsed}</strong><small>{total ? `${Math.round(refsParsed / total * 100)}%` : (en ? "No references" : "暂无引用")}</small></article>
            <article><span>{en ? "Failed" : "解析失败"}</span><strong>{failedRefs}</strong><small>{failedRefs ? (en ? "See reference list" : "原因见引用清单") : (en ? "None" : "无")}</small></article>
            <article><span>{en ? "Open full text" : "开放全文"}</span><strong>{fullTexts}/{total}</strong><small>{en ? "legally obtained" : "合法取得"}</small></article>
            <article><span>{en ? "Compared sources" : "进入文本对照"}</span><strong>{comparedFullTexts}</strong><small>{en ? `${lexicalComparisons}/${lexicalBudget} lexical comparisons` : `词面比较 ${lexicalComparisons}/${lexicalBudget}`}</small></article>
            <article><span>{en ? "Semantic similarity" : "语义近似"}</span><strong>{semanticCandidates}</strong><small>{en ? `${semanticComparisons}/${semanticBudget} comparisons` : `比较 ${semanticComparisons}/${semanticBudget}`}</small></article>
            <article><span>{en ? "Citation alignment" : "引用论断核对"}</span><strong>{citationMatches}/{citationContexts}</strong><small>{en ? `${citationComparisons}/${citationBudget} comparisons` : `文本对齐；比较 ${citationComparisons}/${citationBudget}`}</small></article>
            <article><span>{en ? "Statistical recomputation" : "统计复算"}</span><strong>{statisticalRecomputed}/{statisticalMentions}</strong><small>{en ? `thresholds ${statisticalThresholds}/${statisticalThresholdBudget}; averages ${statisticalAverages}/${statisticalAverageBudget}; list comparisons ${statisticalListComparisons}/${statisticalListBudget}` : `阈值 ${statisticalThresholds}/${statisticalThresholdBudget}；均值 ${statisticalAverages}/${statisticalAverageBudget}；列表比较 ${statisticalListComparisons}/${statisticalListBudget}`}</small></article>
            <article><span>{en ? "Figure-region review" : "图片局部核对"}</span><strong>{imageComparisons}/{imageBudget}</strong><small>{en ? `${imageCandidates} candidates; ${imageSkipped} skipped; ${imageSampled} sampled; pixels ${imageDecodedPixels}/${imageDecodedPixelBudget}; tiles ${imageTiles}/${imageTileBudget}` : `${imageCandidates} 项候选；跳过 ${imageSkipped}；稀疏采样 ${imageSampled}；像素 ${imageDecodedPixels}/${imageDecodedPixelBudget}；图块 ${imageTiles}/${imageTileBudget}`}</small></article>
            <article><span>{en ? "Body locations" : "正文定位"}</span><strong>{located}/{sections}</strong><small>{en ? "sections located" : "已定位章节"}</small></article>
          </section>

          {["fetching_sources", "indexing", "checking"].includes(task.status) && (
            <section className="review-action" aria-live="polite"><div className="spinner" /><div><strong>{task.stage_message}</strong><p>{en ? "Open sources are checked, indexed only for this task, then compared with the submitted paper." : "系统只获取合法开放来源，在当前任务内建立临时索引并与待检论文逐项对照。"}</p></div></section>
          )}
          {task.status === "checking_failed" && (
            <section className="review-action failed"><div><strong>{en ? "The deep review stopped" : "深度检查未完成"}</strong><p>{task.error_message}</p><button type="button" className="secondary-button" onClick={retry}>{en ? "Try again" : "重新检查"}</button><button type="button" className="secondary-button" onClick={purgeTemporaryAssets}>{en ? "Clear temporary material and close" : "清理临时材料并结束"}</button></div></section>
          )}
          {comparisonBudgetExhausted && (
            <section className="review-action failed"><div><strong>{en ? "Part of the analysis reached its computation limit" : "部分分析达到计算上限"}</strong><p>{en ? "The report records the actual coverage for each check; no conclusion is drawn for the unprocessed remainder." : "报告会逐项记录实际覆盖范围，未处理部分不作结论。"}</p></div></section>
          )}

          <section className="review-grid">
            <div className="result-panel">
              <div className="tabs" role="tablist">
                {reviewing && <button role="tab" aria-selected={activeTab === "evidence"} className={activeTab === "evidence" ? "active" : ""} onClick={() => setActiveTab("evidence")}>{en ? "Evidence" : "待复核证据"} <span>{evidence.length}</span></button>}
                <button role="tab" aria-selected={activeTab === "structure"} className={activeTab === "structure" ? "active" : ""} onClick={() => setActiveTab("structure")}>{en ? "Paper structure" : "正文结构"} <span>{sections}</span></button>
                <button role="tab" aria-selected={activeTab === "references"} className={activeTab === "references" ? "active" : ""} onClick={() => setActiveTab("references")}>{en ? "References" : "参考文献"} <span>{total}</span></button>
              </div>
              {activeTab === "evidence" && reviewing ? (
                <div className="evidence-list">
                  {evidence.map((item, index) => {
                    const draft = decisionDrafts[item.id] ?? { decision: "", reason: "" };
                    const title = evidenceTitle[item.code]?.[en ? 1 : 0] ?? item.code;
                    return <article className="evidence-card" key={item.id}>
                      <div className="evidence-card-heading"><span>{String(index + 1).padStart(2, "0")}</span><div><small>{item.severity === "high" ? (en ? "Material limitation" : "重要限制") : (en ? "Needs review" : "待复核")}</small><h3>{title}</h3></div>{item.subject_location.page && <button className="page-link" onClick={() => { setActivePdfAssetId(task.source_asset!.id); setPage(item.subject_location.page!); }}>{en ? `Page ${item.subject_location.page}` : `第 ${item.subject_location.page} 页`} ↗</button>}</div>
                      <p className="evidence-explanation">{item.explanation}</p>
                      <blockquote>{item.subject_excerpt}</blockquote>
                      {item.source_excerpt && <blockquote className="source-excerpt">{item.source_excerpt}</blockquote>}
                      {item.source_location?.page && !["purged", "purge_failed"].includes(task.status) && <button className="page-link comparison-link" onClick={() => { setActivePdfAssetId(item.source_location!.document_id); setPage(item.source_location!.page!); }}>{en ? `Open source page ${item.source_location.page}` : `打开来源第 ${item.source_location.page} 页`} ↗</button>}
                      {item.source_location?.page && ["purged", "purge_failed"].includes(task.status) && <small>{en ? "The source file may have been cleared; its excerpt and checksum remain in the report." : "来源全文可能已清理；来源片段与文件校验值仍保留在报告中。"}</small>}
                      {item.decision ? <div className="decision-saved"><strong>{en ? "Decision saved" : "已完成裁决"}</strong><span>{item.decision.reason}</span></div> : <div className="decision-form">
                        <label>{en ? "Your decision" : "复核决定"}<select value={draft.decision} onChange={(event) => setDecisionDrafts((current) => ({ ...current, [item.id]: { ...draft, decision: event.target.value } }))}><option value="">{en ? "Choose…" : "请选择…"}</option><option value="confirmed">{en ? "Confirm discrepancy" : "确认存在差异"}</option><option value="needs_material">{en ? "Request material" : "要求补充材料"}</option><option value="insufficient">{en ? "Insufficient evidence" : "证据不足"}</option><option value="reasonable">{en ? "Reasonable explanation" : "合理或可接受"}</option></select></label>
                        <label>{en ? "Reason" : "裁决理由"}<textarea value={draft.reason} onChange={(event) => setDecisionDrafts((current) => ({ ...current, [item.id]: { ...draft, reason: event.target.value } }))} placeholder={en ? "State what the evidence does and does not establish" : "写明这项证据能说明什么、不能说明什么"} /></label>
                        <button type="button" className="secondary-button" onClick={() => saveDecision(item)}>{en ? "Save decision" : "保存裁决"}</button>
                      </div>}
                    </article>;
                  })}
                  {!evidence.length && <p className="empty-evidence">{en ? "No reviewable evidence was produced." : "本轮未产生需要人工裁决的证据。"}</p>}
                </div>
              ) : activeTab === "structure" ? (
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
                        {reference.failure_reason && <small className="failure-reason">{(failureText[reference.failure_reason] ?? ["当前来源未能处理", "This source could not be processed"])[en ? 1 : 0]}</small>}
                        {reference.doi && <small className="doi">DOI {reference.doi}</small>}
                        <small className="doi">{en ? "Full text" : "全文"}: {(fullTextStatus[reference.full_text_status] ?? ["状态待确认", "Status unavailable"])[en ? 1 : 0]}</small>
                      </div>
                      {reference.page ? <button className="page-link" onClick={() => setPage(reference.page!)}>{en ? `Page ${reference.page}` : `第 ${reference.page} 页`} ↗</button> : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
            <aside className="pdf-panel">
              <div className="pdf-toolbar"><strong>{displayedAssetId === task.source_asset?.id ? (en ? "Submitted PDF" : "待检原文") : (en ? "Cited source PDF" : "引用来源")}</strong><span>{en ? `Page ${page}` : `第 ${page} 页`}</span>{displayedAssetId !== task.source_asset?.id && <button className="page-link" onClick={() => { setActivePdfAssetId(task.source_asset!.id); setPage(1); }}>{en ? "Back to submitted paper" : "返回待检论文"}</button>}</div>
              {pdfUrl && <iframe key={pdfUrl} src={pdfUrl} title={en ? `Paper source, page ${page}` : `论文原文，第 ${page} 页`} />}
            </aside>
          </section>
          {task.status === "reviewed" && <section className="report-action"><div><strong>{en ? "All evidence has been reviewed" : "全部证据已完成裁决"}</strong><p>{en ? "Generate a fixed report from the exact evidence and decisions shown above." : "现在可以按当前证据版本和裁决生成固定报告。"}</p></div><button type="button" className="secondary-button" onClick={generateReport}>{en ? "Generate report" : "生成可信报告"}</button></section>}
          {(reportUrl || task.report_asset) && <section className="report-action ready"><div><strong>{en ? "The review report is ready" : "可信报告已生成"}</strong><p>{en ? "The report records actual coverage, evidence, decisions and limitations." : "报告已固定实际覆盖率、证据、人工裁决和能力边界。"}</p></div><a className="secondary-button" href={reportUrl ?? `/backend/tasks/${task.id}/assets/${task.report_asset!.id}/content`} target="_blank" rel="noreferrer">{en ? "Open PDF report" : "打开 PDF 报告"}</a></section>}
          {task.status === "completed" && <section className="report-action"><div><strong>{en ? "Temporary source material is still retained" : "临时引用材料尚待处置"}</strong><p>{en ? "The report is fixed. Clear downloaded source PDFs and the task index to close this review." : "报告已经固定；清理下载的引用全文与任务索引后，本次检查才完成生命周期收口。"}</p></div><button type="button" className="secondary-button" onClick={purgeTemporaryAssets}>{en ? "Clear temporary material" : "清理临时材料"}</button></section>}
          {task.status === "purge_failed" && <section className="report-action failed"><div><strong>{en ? "Temporary cleanup is incomplete" : "临时材料未完全清理"}</strong><p>{task.stage_message}</p></div><button type="button" className="secondary-button" onClick={purgeTemporaryAssets}>{en ? "Retry cleanup" : "重试清理"}</button></section>}
          {task.status === "purged" && <section className="report-action ready"><div><strong>{en ? "Temporary material cleared" : "临时材料已清理"}</strong><p>{task.report_asset ? (en ? "The report and audit record remain available; downloaded references and the task index were removed." : "可信报告与审计记录继续保留；下载的引用全文和任务索引已经移除。") : (en ? "Downloaded references and the task index were removed; the submitted paper and audit record remain available." : "下载的引用全文和任务索引已经移除；待检论文与审计记录继续保留。")}</p></div></section>}
          {loadError && <p className="form-error">{loadError}</p>}
          <p className="result-boundary">{en ? "Evidence and anomalies require human review; they are not automatic findings of misconduct." : "证据与异常仍需人工复核，不构成对作者主观故意或学术不端的自动判定。"}</p>
        </>
      )}
    </main>
  );
}
