import { PRODUCT_NAME } from "./brand";
import { Locale, pathFor } from "./i18n";

const legalLinksZh = [
  ["服务条款", "terms"], ["隐私政策", "privacy"], ["Cookie 政策", "cookies"],
  ["退款与取消", "refund"], ["数据权利", "data-rights"], ["不出售或共享", "do-not-sell"],
  ["AI 使用说明", "ai-disclaimer"], ["产品法律补充", "product-supplement"],
] as const;
const legalLinksEn = [
  ["Terms of Service", "terms"], ["Privacy Policy", "privacy"], ["Cookie Policy", "cookies"],
  ["Refunds & cancellation", "refund"], ["Data rights", "data-rights"], ["Do not sell or share", "do-not-sell"],
  ["AI use notice", "ai-disclaimer"], ["Product legal supplement", "product-supplement"],
] as const;

export function SiteFooter({ locale }: { locale: Locale }) {
  const en = locale === "en";
  const legalLinks = en ? legalLinksEn : legalLinksZh;
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-company">
          <a className="footer-brand" href="https://szlk.ai" rel="noreferrer">SZLK LTD ↗</a>
          <p>{en ? "UK company 16843016" : "英国注册公司 16843016"}</p>
          <p>128 City Road, London, EC1V 2NX, United Kingdom</p>
        </div>
        <nav aria-label={en ? "Legal information" : "法律信息"}>{legalLinks.map(([label, slug]) => <a key={slug} href={pathFor(locale, `/legal/${slug}`)}>{label}</a>)}</nav>
        <p className="footer-note">{en ? `${PRODUCT_NAME} organizes traceable evidence for research integrity review. It does not replace institutional investigation, peer review or legal advice.` : `${PRODUCT_NAME} 为科研诚信审查整理可回到原文复核的证据，不替代机构调查、同行评议或法律判断。`}</p>
      </div>
    </footer>
  );
}
