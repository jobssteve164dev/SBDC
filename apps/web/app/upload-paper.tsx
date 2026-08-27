"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const MAX_BYTES = 50 * 1024 * 1024;

type Stage = "idle" | "creating" | "uploading" | "starting";

export function UploadPaper() {
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);

  function choose(next: File | null) {
    setError(null);
    if (!next) return;
    if (next.type !== "application/pdf" && !next.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件");
      return;
    }
    if (next.size > MAX_BYTES) {
      setError("PDF 不能超过 50 MB");
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
      router.push(`/tasks/${task.id}`);
    } catch (reason) {
      setStage("idle");
      setError(reason instanceof Error ? reason.message : "请求未能完成");
      if (taskId) router.push(`/tasks/${taskId}`);
    }
  }

  const stageLabel = {
    idle: "开始解析",
    creating: "正在创建检查…",
    uploading: "正在上传并验证…",
    starting: "正在启动解析…",
  }[stage];

  return (
    <section className="upload-card" aria-labelledby="upload-title">
      <div className="step-number">01</div>
      <div>
        <h2 id="upload-title">上传待检论文</h2>
        <p>当前支持数字版 PDF，单份不超过 50 MB、500 页。</p>
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
            <button type="button" onClick={() => inputRef.current?.click()}>更换</button>
          </div>
        ) : (
          <button className="pick-file" type="button" onClick={() => inputRef.current?.click()}>
            <span aria-hidden="true">↑</span>
            <strong>选择 PDF</strong>
            <small>也可以拖放到这里</small>
          </button>
        )}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button" type="button" disabled={!file || stage !== "idle"} onClick={submit}>
        {stageLabel}<span aria-hidden="true">→</span>
      </button>
      <p className="privacy-note">论文内容不会发送给第三方大模型，也不会进入共享全文库。</p>
    </section>
  );
}
