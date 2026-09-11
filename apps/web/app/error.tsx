"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="loading-screen">
      <p><span className="zh-copy">页面暂时无法显示。</span><span className="en-copy">This page is temporarily unavailable.</span></p>
      <button className="secondary-button" onClick={reset}><span className="zh-copy">重新加载</span><span className="en-copy">Reload</span></button>
    </main>
  );
}
