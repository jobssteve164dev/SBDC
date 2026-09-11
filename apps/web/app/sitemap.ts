import type { MetadataRoute } from "next";

import { pathFor, SITE_ORIGIN } from "./i18n";

const publicPaths = ["/", "/about", "/submit", "/public-submissions", "/review-notices"];
const legalSlugs = ["terms", "privacy", "cookies", "refund", "data-rights", "do-not-sell", "ai-disclaimer", "product-supplement"];

export default function sitemap(): MetadataRoute.Sitemap {
  return [...publicPaths, ...legalSlugs.map((slug) => `/legal/${slug}`)].flatMap((path) => (["zh-CN", "en"] as const).map((locale) => ({
    url: `${SITE_ORIGIN}${pathFor(locale, path)}`,
    lastModified: new Date("2026-09-11T00:00:00Z"),
    changeFrequency: path.startsWith("/legal/") ? "monthly" as const : "weekly" as const,
    priority: path === "/" ? 1 : path === "/about" ? 0.9 : 0.7,
    alternates: { languages: { "zh-CN": `${SITE_ORIGIN}${pathFor("zh-CN", path)}`, en: `${SITE_ORIGIN}${pathFor("en", path)}` } },
  })));
}
