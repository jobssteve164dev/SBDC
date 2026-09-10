export default function Home() {
  return (
    <main id="main-content">
      <section className="marketing-hero">
        <div>
          <p className="eyebrow">科研诚信证据工作台</p>
          <h1>让论文审查，<br />从猜测回到证据。</h1>
          <p className="hero-copy">当前可上传论文 PDF，解析论文结构与参考文献，并把结果带回具体页码核对。系统如实呈现覆盖范围，把最终判断留给人。</p>
          <div className="hero-actions">
            <a className="primary-link" href="/submit">提交待核查论文 <span aria-hidden="true">→</span></a>
            <a className="text-link" href="/login">审查者登录</a>
          </div>
        </div>
        <aside className="evidence-preview" aria-label="当前检查范围">
          <p className="preview-kicker">当前可用范围</p>
          <blockquote>先看清论文与引用，<br />再进入证据复核。</blockquote>
          <div className="evidence-line"><span>论文结构</span><strong>题名 · 章节 · 页码</strong></div>
          <div className="evidence-line"><span>参考文献</span><strong>条目 · 标识符 · 位置</strong></div>
          <p className="preview-boundary">文本、统计与图片证据检查仍在后续建设中；当前结果不包含这些结论。</p>
        </aside>
      </section>

      <section className="value-section" aria-labelledby="value-title">
        <p className="eyebrow">为什么使用 SBDC</p>
        <h2 id="value-title">证据先于结论，边界同样清楚。</h2>
        <div className="value-grid">
          <article><span>01</span><h3>看清论文结构</h3><p>解析题名、章节与页码，让审查者先准确定位原文。</p></article>
          <article><span>02</span><h3>整理参考文献</h3><p>提取参考文献条目、标识符与所在位置，并如实显示解析缺失。</p></article>
          <article><span>03</span><h3>由审查者作出决定</h3><p>系统输出证据和待复核结论，不替代学术共同体作出事实与责任判断。</p></article>
        </div>
      </section>

      <section className="process-section" aria-labelledby="process-title">
        <div><p className="eyebrow">公众科研监督</p><h2 id="process-title">发现疑点，可以把论文交给我们。</h2></div>
        <div className="process-copy">
          <p>注册公众投稿账号后，提交你有权提供的 PDF 和核查理由。投稿账号与审查工作台严格分开，不会获得内部审查权限。</p>
          <ol><li><strong>提交论文</strong><span>说明希望核查的原因</span></li><li><strong>确认收件</strong><span>随时查看自己的投稿状态</span></li><li><strong>进入复核</strong><span>由获授权审查者评估和推进</span></li></ol>
          <a className="secondary-button" href="/submit">开始投稿</a>
        </div>
      </section>
    </main>
  );
}
