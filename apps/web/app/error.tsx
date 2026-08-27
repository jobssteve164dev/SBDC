"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="loading-screen">
      <p>页面暂时无法显示。</p>
      <button className="secondary-button" onClick={reset}>重新加载</button>
    </main>
  );
}
