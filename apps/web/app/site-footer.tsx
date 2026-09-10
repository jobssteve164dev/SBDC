const legalLinks = [
  ["服务条款", "terms"], ["隐私政策", "privacy"], ["Cookie 政策", "cookies"],
  ["退款与取消", "refund"], ["数据权利", "data-rights"], ["不出售或共享", "do-not-sell"],
  ["AI 使用说明", "ai-disclaimer"], ["产品法律补充", "product-supplement"],
] as const;

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-company">
          <a className="footer-brand" href="https://szlk.ai" rel="noreferrer">SZLK LTD ↗</a>
          <p>英国注册公司 16843016</p>
          <p>128 City Road, London, EC1V 2NX, United Kingdom</p>
        </div>
        <nav aria-label="法律信息">{legalLinks.map(([label, slug]) => <a key={slug} href={`/legal/${slug}`}>{label}</a>)}</nav>
        <p className="footer-note">科研诚信证据核查平台提供可回到原文复核的证据整理工具，不替代机构调查、同行评议或法律判断。</p>
      </div>
    </footer>
  );
}
