import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyDraftApi } from "../modules/motion-policy-draft-api.js";

const DRAFT = "a".repeat(64);
const PACKAGE = "b".repeat(64);

function summary() {
  return {
    format: "autospine-motion-policy-review-draft-detail",
    format_version: 1,
    draft_id: DRAFT,
    project_id: "sample",
    motion_namespace: "wave-r6-draft",
    clip_id: "wave-left",
    manifest_sha256: "1".repeat(64),
    proposal_sha256: "2".repeat(64),
    foot_candidates_sha256: "3".repeat(64),
    promotion_motion_id: "wave-r6-pabcdef",
    pair_count: 1,
    authoring_alignment: "current",
  };
}

function detail() {
  return {
    ...summary(),
    semantic_summary: {
      pair_count: 1,
      pairs: [{
        pair_id: "hand-vs-face",
        setup_front_slot: "face",
        slots: [
          { slot_id: "handwear-l", depth_role: "humanoid.arm.upper.left" },
          { slot_id: "face", depth_role: "humanoid.head" },
        ],
      }],
    },
  };
}

function response(value) { return { ok: true, status: 200, json: async () => value }; }

test("draft API keeps GET discovery separate from one explicit adoption POST", async () => {
  const calls = [];
  const api = createMotionPolicyDraftApi(async (url, options) => {
    calls.push({ url, options });
    if (options.method === "POST") {
      return response({
        format: "autospine-depth-policy-draft-adoption-receipt",
        format_version: 1,
        status: "passed",
        draft_id: DRAFT,
        project_id: "sample",
        motion_id: "wave-r6-pabcdef",
        clip_id: "wave-left",
        reused: false,
        policy_sha256: "4".repeat(64),
        depth_candidates_sha256: "5".repeat(64),
        package_id: PACKAGE,
      });
    }
    if (url === `/api/motion-policy/review-drafts/${DRAFT}`) return response(detail());
    return response({
      format: "autospine-motion-policy-draft-list",
      format_version: 1,
      count: 1,
      skipped_count: 0,
      recommended_draft_id: DRAFT,
      drafts: [summary()],
    });
  });

  const listing = await api.list();
  const loaded = await api.detail(DRAFT);
  const receipt = await api.adopt(loaded);
  assert.equal(listing.recommended_draft_id, DRAFT);
  assert.equal(receipt.package_id, PACKAGE);
  assert.deepEqual(calls.map((call) => call.options.method), ["GET", "GET", "POST"]);
  const request = JSON.parse(calls[2].options.body);
  assert.deepEqual(Object.keys(request).sort(), [
    "draft_id", "explicit_confirmation", "format", "format_version",
    "intent", "manifest_sha256", "proposal_sha256",
  ]);
  assert.equal(request.explicit_confirmation, true);
  assert.equal(calls[2].options.headers["X-Autospine-Intent"], "depth-policy-draft-adoption-v1");
  assert.doesNotMatch(calls[2].options.body, /path|source|policy_json/i);
});

test("draft API rejects a malformed semantic projection before adoption", async () => {
  const invalid = detail();
  invalid.semantic_summary.pairs[0].setup_front_slot = "missing";
  const api = createMotionPolicyDraftApi(async () => response(invalid));
  await assert.rejects(api.detail(DRAFT), /前景图层/);
});

test("draft list sends one canonical project scope", async () => {
  const urls = [];
  const api = createMotionPolicyDraftApi(async (url) => {
    urls.push(url);
    return response({
      format: "autospine-motion-policy-draft-list",
      format_version: 1,
      count: 1,
      skipped_count: 0,
      recommended_draft_id: DRAFT,
      drafts: [summary()],
    });
  });
  await api.list("sample");
  assert.deepEqual(urls, ["/api/motion-policy/review-drafts?project_id=sample"]);
  await assert.rejects(api.list("../sample"), /project_id/);
  assert.equal(urls.length, 1);
});

test("draft detail sends the same canonical project scope", async () => {
  const urls = [];
  const api = createMotionPolicyDraftApi(async (url) => {
    urls.push(url);
    return response(detail());
  });
  await api.detail(DRAFT, "sample");
  assert.deepEqual(urls, [
    `/api/motion-policy/review-drafts/${DRAFT}?project_id=sample`,
  ]);
  await assert.rejects(api.detail(DRAFT, "../sample"), /project_id/);
  assert.equal(urls.length, 1);
});

test("draft list accepts empty or historical-only inventories without a recommendation", async () => {
  const empty = {
    format: "autospine-motion-policy-draft-list",
    format_version: 1,
    count: 0,
    skipped_count: 0,
    recommended_draft_id: null,
    drafts: [],
  };
  const emptyList = await createMotionPolicyDraftApi(
    async () => response(empty),
  ).list();
  assert.equal(emptyList.recommended_draft_id, null);

  const historical = summary();
  historical.authoring_alignment = "historical";
  const historicalList = await createMotionPolicyDraftApi(async () => response({
    ...empty, count: 1, drafts: [historical],
  })).list();
  assert.equal(historicalList.drafts[0].authoring_alignment, "historical");
});

test("one confirmation cannot authorize a multi-pair draft", async () => {
  const invalid = detail();
  invalid.pair_count = 2;
  invalid.semantic_summary.pair_count = 2;
  invalid.semantic_summary.pairs.push(structuredClone(invalid.semantic_summary.pairs[0]));
  const api = createMotionPolicyDraftApi(async () => response(invalid));
  await assert.rejects(api.detail(DRAFT), /草案摘要合同无效/);
});
