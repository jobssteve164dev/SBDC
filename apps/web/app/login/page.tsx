import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getAuthConfig, safeNextPath, SESSION_COOKIE, verifySessionToken } from "../../lib/auth";
import { pageTitle } from "../brand";

export const metadata: Metadata = {
  title: pageTitle("审查者登录"),
};

type LoginPageProps = {
  searchParams: Promise<{ error?: string; next?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const query = await searchParams;
  const next = safeNextPath(query.next ?? "/workbench");
  const config = getAuthConfig();
  const cookieStore = await cookies();
  if (config && await verifySessionToken(cookieStore.get(SESSION_COOKIE)?.value, config)) redirect(next);

  const error = query.error === "configuration"
    ? "登录暂时不可用，请联系管理员。"
    : query.error === "rate_limit"
      ? "尝试次数过多，请稍后再试。"
    : query.error === "credentials"
      ? "账号或密码不正确，请重新输入。"
      : null;

  return (
    <main className="login-shell" id="main-content">
      <section className="login-intro" aria-labelledby="login-title">
        <p className="eyebrow">审查者入口</p>
        <h1 id="login-title">进入论文证据工作台</h1>
        <p>登录后可上传待检论文、查看解析依据，并回到原文位置复核。</p>
      </section>
      <section className="login-card" aria-label="登录">
        <form action="/auth/login" method="post">
          <input type="hidden" name="next" value={next} />
          <div className="field-group">
            <label htmlFor="username">账号</label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              spellCheck={false}
              required
              maxLength={256}
            />
          </div>
          <div className="field-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
              aria-describedby={error ? "login-error" : undefined}
            />
          </div>
          {error && <p className="form-error login-error" id="login-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit">登录工作台 <span aria-hidden="true">→</span></button>
        </form>
        <p className="login-boundary">仅限获授权的审查者使用。</p>
      </section>
    </main>
  );
}
