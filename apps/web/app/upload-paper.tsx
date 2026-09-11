"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Locale } from "./i18n";
import { pathFor } from "./i18n";

const MAX_BYTES = 50 * 1024 * 1024;

type Stage = "idle" | "creating" | "uploading" | "starting";

export function UploadPaper({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);

  function choose(next: File | null) {
    setError(null);
    if (!next) return;
    if (next.type !== "application/pdf" && !next.name.toLowerCase().endsWith(".pdf")) {
      setError(en ? "Choose a PDF file" : "请选择 PDF 文件");
      return;
    }
    if (next.size > MAX_BYTES) {
      setError(en ? "The PDF cannot exceed 50 MB" : "PDF 不能超过 50 MB");
      return;
    }
    setFile(next);
  }

  async function readError(response: Response) {
    try {
      const body = (await response.json()) as { detail?: string };
      return body.detail ?? "请求未能完成";
    } catch {
      return "服务暂时不可用，请稍后重试";
    }
  }

  async function submit() {
    if (!file || stage !== "idle") return;
    setError(null);
    let taskId: string | null = null;
    try {
      setStage("creating");
      const created = await fetch("/backend/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evidence_level: "L1", retention_policy: "task_scoped" }),
      });
      if (!created.ok) throw new Error(await readError(created));
      const task = (await created.json()) as { id: string };
      taskId = task.id;

      setStage("uploading");
      const form = new FormData();
      form.set("file", file);
      const uploaded = await fetch(`/backend/tasks/${task.id}/assets`, { method: "POST", body: form });
      if (!uploaded.ok) throw new Error(await readError(uploaded));

      setStage("starting");
      const parsing = await fetch(`/backend/tasks/${task.id}/parse`, { method: "POST" });
      if (!parsing.ok) throw new Error(await readError(parsing));
      router.push(pathFor(locale, `/tasks/${task.id}`));
    } catch (reason) {
      setStage("idle");
      setError(en ? "The request could not be completed" : reason instanceof Error ? reason.message : "请求未能完成");
      if (taskId) router.push(pathFor(locale, `/tasks/${taskId}`));
    }
  }

  const stageLabel = {
    idle: en ? "Start parsing" : "开始解析",
    creating: en ? "Creating review…" : "正在创建检查…",
    uploading: en ? "Uploading and validating…" : "正在上传并验证…",
    starting: en ? "Starting parser…" : "正在启动解析…",
  }[stage];

  return (
    <section className="upload-card" aria-labelledby="upload-title">
      <div className="step-number">01</div>
      <div>
        <h2 id="upload-title">{en ? "Upload a paper" : "上传待检论文"}</h2>
        <p>{en ? "Digital PDFs are supported, up to 50 MB and 500 pages." : "当前支持数字版 PDF，单份不超过 50 MB、500 页。"}</p>
      </div>
      <div
        className={`drop-zone ${file ? "has-file" : ""}`}
        onDragOver={(event: DragEvent) => event.preventDefault()}
        onDrop={(event: DragEvent) => { event.preventDefault(); choose(event.dataTransfer.files[0] ?? null); }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event: ChangeEvent<HTMLInputElement>) => choose(event.target.files?.[0] ?? null)}
        />
        {file ? (
          <div className="file-choice">
            <span className="file-icon">PDF</span>
            <span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></span>
            <button type="button" onClick={() => inputRef.current?.click()}>{en ? "Change" : "更换"}</button>
          </div>
        ) : (
          <button className="pick-file" type="button" onClick={() => inputRef.current?.click()}>
            <span aria-hidden="true">↑</span>
            <strong>{en ? "Choose PDF" : "选择 PDF"}</strong>
            <small>{en ? "or drop it here" : "也可以拖放到这里"}</small>
          </button>
        )}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button" type="button" disabled={!file || stage !== "idle"} onClick={submit}>
        {stageLabel}<span aria-hidden="true">→</span>
      </button>
      <p className="privacy-note">{en ? "Paper content is not sent to third-party language models or added to a shared full-text repository." : "论文内容不会发送给第三方大模型，也不会进入共享全文库。"}</p>
    </section>
  );
}
