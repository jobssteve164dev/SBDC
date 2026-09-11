"use client";

import { useState } from "react";

import type { Locale } from "../i18n";

export function Postcard({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const source = `/postcards/sbdc-postcard-${en ? "en" : "zh"}.png`;
  const filename = `sbdc-postcard-${en ? "en" : "zh"}.png`;
  const [status, setStatus] = useState("");

  async function share() {
    setStatus(en ? "Opening share options…" : "正在打开分享选项…");
    try {
      const data = { title: "SBDC · Source-Based Deep Check", text: en ? "Evidence before conclusions. Review research concerns at their source." : "证据先于结论，让每一项科研疑点回到原文与依据。", url: en ? "https://sbdc.szlk.uk/en/about" : "https://sbdc.szlk.uk/about" };
      if (navigator.share) {
        const image = await fetch(source);
        const file = new File([await image.blob()], filename, { type: "image/png" });
        const postcardData = { title: data.title, text: data.text, files: [file] };
        await navigator.share(navigator.canShare?.(postcardData) ? postcardData : data);
        setStatus(en ? "Shared" : "已完成分享");
      } else {
        await navigator.clipboard.writeText(data.url);
        setStatus(en ? "Link copied" : "链接已复制");
      }
    } catch (error) {
      setStatus(error instanceof DOMException && error.name === "AbortError" ? (en ? "Sharing cancelled" : "已取消分享") : (en ? "Could not share. Save the postcard instead." : "未能直接分享，请保存明信片后发送。"));
    }
  }

  return <section className="postcard-section" aria-labelledby="postcard-title">
    <div className="postcard-copy"><p className="eyebrow">{en ? "Share SBDC" : "分享 SBDC"}</p><h2 id="postcard-title">{en ? "Send a reviewable idea further" : "让可复核的科研监督走得更远"}</h2><p>{en ? "Save the postcard or share this page with someone who cares about evidence-led research integrity review." : "保存这张明信片，或把页面分享给同样关心科研诚信与证据复核的人。"}</p></div>
    <figure className="postcard"><img src={source} width="1200" height="630" alt={en ? "SBDC sharing postcard: Evidence before conclusions" : "SBDC 分享明信片：证据先于结论"} /></figure>
    <div className="postcard-actions"><a className="primary-link" href={source} download={filename}>{en ? "Save postcard" : "保存明信片"}</a><button className="secondary-button" type="button" onClick={share}>{en ? "Share postcard" : "分享明信片"}</button><span role="status" aria-live="polite">{status}</span></div>
  </section>;
}
