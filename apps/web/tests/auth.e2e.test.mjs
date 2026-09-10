import assert from "node:assert/strict";
import test from "node:test";

const baseUrl = process.env.SBDC_TEST_BASE_URL ?? "http://127.0.0.1:3000";
const username = process.env.SBDC_ADMIN_USERNAME ?? "reviewer";
const password = process.env.SBDC_ADMIN_PASSWORD ?? "test-password";

function cookieFrom(response) {
  const value = response.headers.get("set-cookie");
  assert.ok(value, "response must set a session cookie");
  return value.split(";", 1)[0];
}

async function login(overrides = {}) {
  const body = new URLSearchParams({
    username: overrides.username ?? username,
    password: overrides.password ?? password,
    next: "/workbench",
  });
  return fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    body,
    redirect: "manual",
  });
}

test("主域名根路径直接展示公众营销页", async () => {
  const response = await fetch(`${baseUrl}/`, { redirect: "manual" });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /科研诚信证据核查平台/);
  assert.match(html, /SBDC · Source-Based Deep Check/);
  assert.match(html, /<title>SBDC · Source-Based Deep Check<\/title>/);
  assert.match(html, /<h1>SBDC<\/h1>/);
  assert.doesNotMatch(html, /Research Integrity Evidence Review Platform/);
  assert.match(html, /SBDC(?:<!-- -->)? 是面向科研诚信审查的证据核查平台/);
  assert.match(html, /href="\/submit"/);
  assert.match(html, /href="\/login"/);
});

test("投稿无需注册登录并允许选择是否公开", async () => {
  const response = await fetch(`${baseUrl}/submit`);
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /联系邮箱/);
  assert.match(html, /公开这条投稿/);
  assert.doesNotMatch(html, /创建投稿账号|登录投稿账号|注册并继续/);
});

test("公开投稿与审查公示拥有独立公开页面", async () => {
  const submissions = await fetch(`${baseUrl}/public-submissions`);
  assert.equal(submissions.status, 200);
  const submissionsHtml = await submissions.text();
  assert.match(submissionsHtml, /公开投稿论文/);
  assert.match(submissionsHtml, /<title>公开投稿 · SBDC<\/title>/);
  const notices = await fetch(`${baseUrl}/review-notices`);
  assert.equal(notices.status, 200);
  const noticesHtml = await notices.text();
  assert.match(noticesHtml, /现有证据不足/);
  assert.match(noticesHtml, /<title>审查公示 · SBDC<\/title>/);

  const submissionForm = await fetch(`${baseUrl}/submit`);
  assert.match(await submissionForm.text(), /<title>提交待核查论文 · SBDC<\/title>/);

  const loginPage = await fetch(`${baseUrl}/login`);
  assert.match(await loginPage.text(), /<title>审查者登录 · SBDC<\/title>/);
});

test("未登录访问工作台会进入带原路径的登录页", async () => {
  const response = await fetch(`${baseUrl}/workbench`, { redirect: "manual" });
  assert.equal(response.status, 307);
  const location = new URL(response.headers.get("location"), baseUrl);
  assert.equal(location.pathname, "/login");
  assert.equal(location.searchParams.get("next"), "/workbench");
});

test("公众页展示完整法务入口与公司主体信息", async () => {
  const response = await fetch(`${baseUrl}/`, { redirect: "manual" });
  const html = await response.text();
  for (const path of ["terms", "privacy", "cookies", "refund", "data-rights", "do-not-sell", "ai-disclaimer", "product-supplement"]) {
    assert.match(html, new RegExp(`href="/legal/${path}"`));
  }
  assert.match(html, /SZLK LTD/);
  assert.match(html, /16843016/);
  assert.match(html, /https:\/\/szlk\.ai/);
});

test("鉴权配置有效时健康检查通过", async () => {
  const response = await fetch(`${baseUrl}/health`, { redirect: "manual" });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok", service: "web", api: "ok" });
});

test("未登录访问后端代理会被拒绝", async () => {
  const response = await fetch(`${baseUrl}/backend/health`, { redirect: "manual" });
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { detail: "请先登录" });
});

test("错误凭据不会建立会话", async () => {
  const response = await login({ password: `${password}-wrong` });
  assert.equal(response.status, 303);
  const locationHeader = response.headers.get("location");
  assert.match(locationHeader, /^\/login\?/);
  const location = new URL(locationHeader, baseUrl);
  assert.equal(location.pathname, "/login");
  assert.equal(location.searchParams.get("error"), "credentials");
  assert.equal(response.headers.get("set-cookie"), null);
});

test("正确凭据建立会话并允许进入工作台", async () => {
  const response = await login();
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "/workbench");
  const cookie = cookieFrom(response);

  const workspace = await fetch(`${baseUrl}/workbench`, { headers: { cookie }, redirect: "manual" });
  assert.equal(workspace.status, 200);
  const workspaceHtml = await workspace.text();
  assert.match(workspaceHtml, /<title>审查工作台 · SBDC<\/title>/);
  assert.match(workspaceHtml, /上传待检论文/);
  assert.match(workspaceHtml, /公众投稿论文/);
  assert.match(workspaceHtml, /发布到审查公示/);
  assert.match(workspaceHtml, /href="\/backend\/submissions\/11111111-1111-1111-1111-111111111111\/content"/);

  const backend = await fetch(`${baseUrl}/backend/health`, {
    headers: { cookie },
    redirect: "manual",
  });
  assert.equal(backend.status, 200);
  assert.deepEqual(await backend.json(), { status: "ok" });
  assert.match(response.headers.get("set-cookie"), /HttpOnly/i);
  assert.match(response.headers.get("set-cookie"), /Secure/i);
  assert.match(response.headers.get("set-cookie"), /SameSite=Strict/i);
});

test("站外返回地址会被收敛到工作台路径", async () => {
  const body = new URLSearchParams({ username, password, next: "//attacker.example/path" });
  const response = await fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    body,
    redirect: "manual",
  });
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "/workbench");
});

test("被篡改的会话不能访问工作台", async () => {
  const response = await login();
  const cookie = cookieFrom(response);
  const tampered = `${cookie.slice(0, -1)}${cookie.endsWith("a") ? "b" : "a"}`;

  const workspace = await fetch(`${baseUrl}/workbench`, { headers: { cookie: tampered }, redirect: "manual" });
  assert.equal(workspace.status, 307);
  assert.equal(new URL(workspace.headers.get("location"), baseUrl).pathname, "/login");
});

test("退出会清除会话并返回登录页", async () => {
  const response = await login();
  const cookie = cookieFrom(response);
  const logout = await fetch(`${baseUrl}/auth/logout`, {
    method: "POST",
    headers: { cookie },
    redirect: "manual",
  });

  assert.equal(logout.status, 303);
  assert.equal(logout.headers.get("location"), "/login");
  assert.match(logout.headers.get("set-cookie"), /Max-Age=0/i);
});

test("连续错误登录会被暂时限制", async () => {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const response = await fetch(`${baseUrl}/auth/login`, {
      method: "POST",
      headers: { "cf-connecting-ip": "203.0.113.77" },
      body: new URLSearchParams({ username, password: "definitely-wrong", next: "/" }),
      redirect: "manual",
    });
    assert.equal(response.status, 303);
  }
  const blocked = await fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    headers: { "cf-connecting-ip": "203.0.113.77" },
    body: new URLSearchParams({ username, password: "definitely-wrong", next: "/" }),
    redirect: "manual",
  });
  const location = new URL(blocked.headers.get("location"), baseUrl);
  assert.equal(location.searchParams.get("error"), "rate_limit");

  const otherClientAuthorized = await fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    headers: { "cf-connecting-ip": "192.0.2.80" },
    body: new URLSearchParams({ username, password, next: "/" }),
    redirect: "manual",
  });
  assert.equal(otherClientAuthorized.headers.get("location"), "/");
  assert.ok(otherClientAuthorized.headers.get("set-cookie"));
});
