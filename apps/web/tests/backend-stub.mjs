import { createServer } from "node:http";

const port = Number(process.env.SBDC_TEST_BACKEND_PORT ?? 3108);
const internalSecret = process.env.SBDC_INTERNAL_API_SECRET ?? "0123456789abcdef0123456789abcdef";
createServer((request, response) => {
  const taskId = "11111111-1111-1111-1111-111111111111";
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  if (request.method === "GET" && request.url === "/submissions") {
    if (request.headers["x-sbdc-internal-secret"] !== internalSecret) {
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ detail: "unauthorized" }));
      return;
    }
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
      terms_version: "2026-09-11.v1",
      terms_locale: "zh-CN",
      terms_notice_sha256: "0".repeat(64),
      terms_accepted_at: "2026-09-10T00:00:00Z",
      created_at: "2026-09-10T00:00:00Z",
    }]));
    return;
  }
  if (request.method === "GET" && request.url === `/tasks/${taskId}`) {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({
      id: taskId, status: "review_ready", stage_message: "深度检查完成，请逐项复核证据", error_message: null,
      coverage_summary: { references_total: 52, references_parsed: 52, references_failed: 0, body_sections: 4, located_sections: 4 },
      source_asset: { id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", sha256: "a".repeat(64), size_bytes: 2048, page_count: 7 },
      report_asset: null,
      document: { title: "Room Temperature Triggered Single Photon Emission", authors: ["Ling Chen"], abstract: "Room-temperature single photon emission study.", parser_version: "0.9.0", sections: [{ ordinal: 1, heading: "Results", page: 2, bbox: [1, 1, 2, 2], paragraphs: [{ text: "Experimental results.", page: 2, bbox: [1, 1, 2, 2] }] }] },
      references: [],
    }));
    return;
  }
  if (request.method === "GET" && request.url === `/tasks/${taskId}/evidence`) {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", code: "cross_condition_subject_mismatch", status: "needs_review",
      severity: "high", confidence: 0.99, subject_location: { page: 4, bbox: [1, 1, 2, 2] },
      source_location: { page: 1, bbox: [1, 1, 2, 2] },
      subject_excerpt: "The data recorded at 4.6 K and RT were not obtained from the same QD.",
      explanation: "低温与室温结果来自不同发射体，现有记录不能证明同一发射体随温度升高仍保持相同性能。",
      limitations: ["该发现不评价测量数据真实性。"], decision: null,
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
