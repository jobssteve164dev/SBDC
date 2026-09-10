export default function Home() {
  return (
    <main id="main-content">
      <section className="marketing-hero">
        <div>
          <p className="eyebrow">Research Integrity Evidence Review Platform</p>
          <h1>科研诚信证据<br />核查平台</h1>
          <p className="hero-lead">让每一项疑点，都能回到原文与依据。</p>
          <p className="hero-copy">面向科研审查者与公众监督者，将论文结构、参考文献和核查线索整理成可定位、可追溯、可由人复核的证据基础。</p>
          <div className="hero-actions">
            <a className="primary-link" href="/submit">提交待核查论文 <span aria-hidden="true">→</span></a>
            <a className="text-link" href="/login">审查者登录</a>
          </div>
        </div>
        <aside className="evidence-preview" aria-label="当前检查范围">
          <p className="preview-kicker">Evidence first · 证据先行</p>
          <blockquote>不是给出一个武断分数，<br />而是保留一条复核路径。</blockquote>
          <div className="evidence-line"><span>论文结构</span><strong>题名 · 章节 · 页码</strong></div>
          <div className="evidence-line"><span>参考文献</span><strong>条目 · 标识符 · 位置</strong></div>
          <p className="preview-boundary">文本、统计与图片证据检查仍在后续建设中；当前结果不包含这些结论。</p>
        </aside>
      </section>

      <section className="value-section" aria-labelledby="value-title">
        <p className="eyebrow">平台价值</p>
        <h2 id="value-title">证据先于结论，边界同样清楚。</h2>
        <div className="value-grid">
          <article><span>01</span><h3>定位，而非猜测</h3><p>解析论文题名、章节与页码，让每一条线索都能回到原文。</p></article>
          <article><span>02</span><h3>呈现依据与缺口</h3><p>整理参考文献条目、标识符和位置，也如实说明无法取得或无法解析的材料。</p></article>
          <article><span>03</span><h3>把判断留给人</h3><p>平台整理证据和待复核事项，不自动认定造假、抄袭或主观故意。</p></article>
        </div>
      </section>

      <section className="process-section" aria-labelledby="process-title">
        <div><p className="eyebrow">公众科研监督</p><h2 id="process-title">发现疑点，可以把论文交给我们。</h2></div>
        <div className="process-copy">
          <p>无需注册账号。留下联系邮箱，提交你有权提供的 PDF 和具体核查理由；你可以自行决定是否公开这条投稿。</p>
          <ol><li><strong>提交材料</strong><span>论文 PDF、联系邮箱与核查理由</span></li><li><strong>自主公开</strong><span>公开时也不会展示邮箱和论文文件</span></li><li><strong>人工复核</strong><span>审查者独立决定是否公示审查结果</span></li></ol>
          <div className="section-actions"><a className="secondary-button" href="/submit">开始投稿</a><a className="text-link" href="/review-notices">查看审查公示</a></div>
        </div>
      </section>
    </main>
  );
}
