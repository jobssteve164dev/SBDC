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
      created_at: "2026-09-10T00:00:00Z",
    }]));
    return;
  }
  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ detail: "not found" }));
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`backend stub ready on ${port}\n`);
});
