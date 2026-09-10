import { createServer } from "node:http";

const port = Number(process.env.SBDC_TEST_BACKEND_PORT ?? 3108);
createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  if (request.method === "GET" && request.url === "/submissions") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{
      id: "11111111-1111-1111-1111-111111111111",
      title: "公众投稿论文",
      authors: "示例作者",
      reason: "希望核查论文结论与引用来源是否一致。",
      status: "received",
      submitter_email: "submitter@example.org",
      is_public: true,
      review_outcome: null,
      review_summary: null,
      review_published: false,
      review_published_at: null,
      created_at: "2026-09-10T00:00:00Z",
    }]));
    return;
  }
  if (request.method === "GET" && request.url === "/public/submissions/published") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{ id: "22222222-2222-2222-2222-222222222222", title: "公开投稿论文", authors: "示例作者", reason: "请求核查引用依据。", created_at: "2026-09-10T00:00:00Z" }]));
    return;
  }
  if (request.method === "GET" && request.url === "/public/review-notices") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{ id: "33333333-3333-3333-3333-333333333333", title: "审查公示论文", authors: "示例作者", review_outcome: "insufficient_evidence", review_summary: "现有证据不足以支持进一步结论。", review_published_at: "2026-09-10T00:00:00Z" }]));
    return;
  }
  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ detail: "not found" }));
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`backend stub ready on ${port}\n`);
});
