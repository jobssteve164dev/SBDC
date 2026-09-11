"use client";

import { usePathname } from "next/navigation";

export function LanguageLink() {
  const pathname = usePathname();
  const en = pathname === "/en" || pathname.startsWith("/en/");
  const alternateLanguagePath = en
    ? pathname.slice(3) || "/"
    : `/en${pathname === "/" ? "" : pathname}`;

  return (
    <a className="language-link" href={alternateLanguagePath} hrefLang={en ? "zh-CN" : "en"}>
      {en ? "中文" : "EN"}
    </a>
  );
}
