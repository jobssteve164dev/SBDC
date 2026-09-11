import type { MetadataRoute } from "next";

import { SITE_ORIGIN } from "./i18n";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/backend/", "/auth/", "/workbench", "/tasks/", "/en/workbench", "/en/tasks/"] }],
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
    host: SITE_ORIGIN,
  };
}
