"use client";

import { FormEvent, useEffect, useState } from "react";

type User = { id: string; email: string };
type Submission = { id: string; title: string; status: string; created_at: string };

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/backend/public${path}`, init);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail ?? "暂时无法完成，请稍后重试");
  return payload;
}

export function PublicSubmission() {
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<Submission[]>([]);
  const [mode, setMode] = useState<"login" | "register">("register");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadAccount() {
    try {
      const account = await request("/me") as User;
      setUser(account);
      setItems(await request("/submissions") as Submission[]);
    } catch { setUser(null); }
  }
  useEffect(() => { void loadAccount(); }, []);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const form = new FormData(event.currentTarget);
      const account = await request(`/auth/${mode}`, { method: "POST", body: form }) as User;
      setUser(account);
      setItems(await request("/submissions") as Submission[]);
    } catch (error) { setMessage(error instanceof Error ? error.message : "暂时无法登录"); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true); setMessage("");
    try {
      const item = await request("/submissions", { method: "POST", body: new FormData(form) }) as Submission;
      setItems((current) => [item, ...current]); form.reset();
      setMessage(`投稿已收到，凭证号：${item.id}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "暂时无法提交"); }
    finally { setBusy(false); }
  }

  async function logout() { await request("/auth/logout", { method: "POST" }); setUser(null); setItems([]); setMessage(""); }

  if (!user) return (
    <section className="public-form-card" aria-labelledby="account-title">
      <div className="form-tabs" role="tablist" aria-label="投稿账号">
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => setMode("register")}>注册</button>
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => setMode("login")}>登录</button>
      </div>
      <h2 id="account-title">{mode === "register" ? "创建投稿账号" : "登录投稿账号"}</h2>
      <p className="form-help">投稿账号仅用于提交论文和查看自己的收件状态，不能进入审查工作台。</p>
      <form onSubmit={authenticate}>
        <label>电子邮箱<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
        <label>密码<input name="password" type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={12} maxLength={1024} /></label>
        {message && <p className="form-message error" role="alert">{message}</p>}
        <button className="primary-button" disabled={busy}>{busy ? "请稍候…" : mode === "register" ? "注册并继续" : "登录并继续"}</button>
      </form>
    </section>
  );

  return (
    <section className="public-form-card" aria-labelledby="submission-title">
      <div className="account-row"><span>投稿账号：{user.email}</span><button type="button" onClick={logout}>退出</button></div>
      <h2 id="submission-title">提交待核查论文</h2>
      <form onSubmit={submit}>
        <label>论文题名<input name="title" required minLength={2} maxLength={500} /></label>
        <label>作者（选填）<input name="authors" maxLength={1000} /></label>
        <label>希望核查的原因<textarea name="reason" required minLength={10} maxLength={4000} rows={6} /></label>
        <label className="file-field">论文 PDF<input name="file" type="file" accept="application/pdf,.pdf" required /><small>最大 50 MB、500 页；不接受加密或损坏文件。</small></label>
        <label className="check-field"><input name="rights_confirmed" type="checkbox" value="true" required /><span>我确认有权提交此文件用于科研诚信审查，并已阅读隐私政策。</span></label>
        {message && <p className="form-message" role="status">{message}</p>}
        <button className="primary-button" disabled={busy}>{busy ? "正在提交…" : "确认投稿"}</button>
      </form>
      {items.length > 0 && <div className="own-submissions"><h3>我的投稿</h3>{items.map((item) => <p key={item.id}><strong>{item.title}</strong><span>已收件 · {new Date(item.created_at).toLocaleDateString("zh-CN")}</span></p>)}</div>}
    </section>
  );
}
