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
    next: "/",
  });
  return fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    body,
    redirect: "manual",
  });
}

test("未登录访问工作台会进入登录页", async () => {
  const response = await fetch(`${baseUrl}/`, { redirect: "manual" });
  assert.equal(response.status, 307);
  assert.equal(new URL(response.headers.get("location"), baseUrl).pathname, "/login");
});

test("鉴权配置有效时健康检查通过", async () => {
  const response = await fetch(`${baseUrl}/health`, { redirect: "manual" });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
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
  assert.equal(response.headers.get("location"), "/");
  const cookie = cookieFrom(response);

  const workspace = await fetch(`${baseUrl}/`, { headers: { cookie }, redirect: "manual" });
  assert.equal(workspace.status, 200);
  assert.match(await workspace.text(), /上传待检论文/);

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

test("站外返回地址会被收敛到工作台首页", async () => {
  const body = new URLSearchParams({ username, password, next: "//attacker.example/path" });
  const response = await fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    body,
    redirect: "manual",
  });
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "/");
});

test("被篡改的会话不能访问工作台", async () => {
  const response = await login();
  const cookie = cookieFrom(response);
  const tampered = `${cookie.slice(0, -1)}${cookie.endsWith("a") ? "b" : "a"}`;

  const workspace = await fetch(`${baseUrl}/`, { headers: { cookie: tampered }, redirect: "manual" });
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
