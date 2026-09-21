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
      coverage_summary: {
        references_total: 52, references_parsed: 52, references_failed: 0,
        reference_full_texts_obtained: 12, reference_full_texts_compared: 10,
        reference_candidate_comparisons: 300, reference_candidate_budget: 50000,
        reference_candidate_budget_exhausted: 0,
        body_sections: 4, located_sections: 4,
        semantic_candidate_comparisons: 480, semantic_similarity_candidates: 3,
        semantic_candidate_budget: 50000, semantic_candidate_budget_exhausted: 0,
        citation_contexts_detected: 18, citation_contexts_with_full_text: 7,
        citation_support_matches: 5, citation_support_unresolved: 13,
        citation_candidate_comparisons: 50000, citation_candidate_budget: 50000,
        citation_candidate_budget_exhausted: 1,
        statistical_mentions_detected: 34, statistical_mentions_recomputed: 2,
        statistical_checks_consistent: 2, statistical_checks_inconsistent: 0,
        statistical_threshold_claims_examined: 8, statistical_threshold_claim_budget: 1000,
        statistical_average_claims_examined: 4, statistical_average_claim_budget: 500,
        statistical_value_list_comparisons: 12, statistical_value_list_comparison_budget: 5000,
        advanced_images_screened: 4, image_regions_compared: 260,
        embedded_images_skipped_resource_limit: 1, advanced_images_skipped_resource_limit: 1,
        image_tile_sampling_adjusted: 2,
        image_tiles_generated: 2500, image_task_tile_budget: 25000,
        image_task_decoded_pixels: 128000, image_task_decoded_pixel_budget: 40000000,
        image_resource_budget_exhausted: 0,
        image_region_comparison_budget: 50000, image_region_budget_exhausted: 0,
        image_region_reuse_candidates: 0,
      },
      source_asset: { id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", sha256: "a".repeat(64), size_bytes: 2048, page_count: 7 },
      report_asset: null,
      document: { title: "Room Temperature Triggered Single Photon Emission", authors: ["Ling Chen"], abstract: "Room-temperature single photon emission study.", parser_version: "0.9.0", sections: [{ ordinal: 1, heading: "Results", page: 2, bbox: [1, 1, 2, 2], paragraphs: [{ text: "Experimental results.", page: 2, bbox: [1, 1, 2, 2] }] }] },
      references: [{
        id: "dddddddd-dddd-dddd-dddd-dddddddddddd", ordinal: 1, raw_citation: "A cited source.",
        title: "A cited source", authors: ["Example Author"], year: "2024", venue: "Evidence Journal",
        doi: "10.1000/example", parse_status: "parsed", failure_reason: null, page: 7, bbox: [1, 1, 2, 2],
        metadata_status: "resolved", full_text_status: "not_open_access", full_text_asset_id: null, access_url: null,
      }],
    }));
    return;
  }
  if (request.method === "GET" && request.url === `/tasks/${taskId}/evidence`) {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify([{
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", code: "cross_condition_subject_mismatch", status: "needs_review",
      severity: "high", confidence: 0.99, subject_location: { document_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", page: 4, bbox: [1, 1, 2, 2] },
      source_location: { document_id: "cccccccc-cccc-cccc-cccc-cccccccccccc", page: 1, bbox: [1, 1, 2, 2] },
      subject_excerpt: "The data recorded at 4.6 K and RT were not obtained from the same QD.",
      source_excerpt: "Figure 3 reports the comparison baseline.",
      explanation: "低温与室温结果来自不同发射体，现有记录不能证明同一发射体随温度升高仍保持相同性能。",
      limitations: ["该发现不评价测量数据真实性。"], decision: null,
    }, {
      id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", code: "citation_direction_conflict_candidate", status: "needs_review",
      severity: "high", confidence: 0.9, subject_location: { document_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", page: 3, bbox: [1, 1, 2, 2] },
      source_location: { document_id: "cccccccc-cccc-cccc-cccc-cccccccccccc", page: 2, bbox: [1, 1, 2, 2] },
      subject_excerpt: "Treatment increased mortality [1].", source_excerpt: "Treatment decreased mortality.",
      explanation: "论断方向与来源片段相反，需要人工核对。", limitations: ["方向词只生成复核候选。"], decision: null,
    }, {
      id: "ffffffff-ffff-ffff-ffff-ffffffffffff", code: "statistical_average_inconsistency", status: "needs_review",
      severity: "medium", confidence: 0.9, subject_location: { document_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", page: 5, bbox: [1, 1, 2, 2] },
      source_location: null, subject_excerpt: "Values 1, 2, 3, 4; average 4.5.", source_excerpt: null,
      explanation: "报告平均值与所列数值不一致。", limitations: ["需核对预先规定的计算方法。"], decision: null,
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
