import assert from "node:assert/strict";
import test from "node:test";

import {
  createMotionPolicyAdoptionApi,
  MOTION_POLICY_ADOPTION_INTENT,
  normalizeAdoptionReceipt,
} from "../modules/motion-policy-adoption-api.js";

const PACKAGE = "a".repeat(64);
const INSTANCE = "b".repeat(64);
const BUNDLE = "c".repeat(64);

function reviewInput() {
  return {
    review: { status: "approved", method: "human", revision: 1 },
    decisions: [],
    root_release_keys: [],
    draw_order_loop_reset: { mode: "explicit", approved: false },
  };
}

function receipt(overrides = {}) {
  return {
    format: "autospine-motion-policy-adoption-receipt",
    format_version: 1,
    status: "passed",
    package_id: PACKAGE,
    project_id: "sample-a",
    motion_id: "kimodo-wave",
    clip_id: "wave-left",
    reused: false,
    address: {
      project_id: "sample-a",
      motion_instance_v2_sha256: INSTANCE,
      bundle_sha256: BUNDLE,
    },
    verification: { status: "passed", replayed_from_exact_upstreams: true },
    ...overrides,
  };
}

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

test("adoption API sends one explicit human intent to the exact package endpoint", async () => {
  const calls = [];
  const api = createMotionPolicyAdoptionApi(async (url, options) => {
    calls.push({ url, options });
    return response(receipt());
  });

  const result = await api.adopt(PACKAGE, reviewInput(), {
    expected: { projectId: "sample-a", motionId: "kimodo-wave", clipId: "wave-left" },
  });

  assert.equal(result.packageId, PACKAGE);
  assert.equal(result.address.motionInstanceV2Sha256, INSTANCE);
  assert.equal(result.address.bundleSha256, BUNDLE);
  assert.equal(result.reused, false);
  assert.equal(calls[0].url, `/api/motion-policy/review-packages/${PACKAGE}/adoptions`);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal("signal" in calls[0].options, false);
  assert.equal(calls[0].options.headers["X-AutoSpine-Intent"], MOTION_POLICY_ADOPTION_INTENT);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    format: "autospine-motion-policy-adoption-request",
    format_version: 1,
    intent: MOTION_POLICY_ADOPTION_INTENT,
    package_id: PACKAGE,
    review_input: reviewInput(),
  });
});

test("receipt adapter exposes only path-free identities and supports a report envelope", () => {
  const result = normalizeAdoptionReceipt({
    ok: true,
    status: "passed",
    input_paths: ["E:/private/review.json"],
    report: receipt({ reused: true, output_path: "E:/private/build" }),
  }, PACKAGE);

  assert.deepEqual(result, {
    packageId: PACKAGE,
    projectId: "sample-a",
    motionId: "kimodo-wave",
    clipId: "wave-left",
    reused: true,
    address: {
      projectId: "sample-a",
      motionInstanceV2Sha256: INSTANCE,
      bundleSha256: BUNDLE,
    },
  });
  assert.doesNotMatch(JSON.stringify(result), /private|output_path|input_paths/);
});

test("adoption API rejects stale receipts, non-human drafts, and public server errors", async () => {
  for (const invalid of [
    receipt({ format: "future-receipt" }),
    receipt({ format_version: 2 }),
  ]) {
    assert.throws(
      () => normalizeAdoptionReceipt(invalid, PACKAGE),
      /回执版本无效/,
    );
  }
  for (const verification of [
    { status: "passed" },
    { status: "passed", replayed_from_exact_upstreams: false },
    { status: "published", replayed_from_exact_upstreams: true },
  ]) {
    assert.throws(
      () => normalizeAdoptionReceipt(receipt({ verification }), PACKAGE),
      /精确复验通过/,
    );
  }
  assert.throws(
    () => normalizeAdoptionReceipt(receipt({ status: "failed" }), PACKAGE),
    /精确复验通过/,
  );
  assert.throws(
    () => normalizeAdoptionReceipt({ ok: false, status: "passed", report: receipt() }, PACKAGE),
    /envelope 未通过/,
  );
  assert.throws(
    () => normalizeAdoptionReceipt(receipt(), PACKAGE, {
      projectId: "sample-b", motionId: "kimodo-wave", clipId: "wave-left",
    }),
    /当前项目或动作不一致/,
  );
  assert.throws(
    () => normalizeAdoptionReceipt(receipt({
      address: {
        project_id: "sample-b",
        motion_instance_v2_sha256: INSTANCE,
        bundle_sha256: BUNDLE,
      },
    }), PACKAGE),
    /地址与当前项目不一致/,
  );

  await assert.rejects(
    createMotionPolicyAdoptionApi(async () => response(receipt({ package_id: "d".repeat(64) })))
      .adopt(PACKAGE, reviewInput()),
    /当前自动复核包不一致/,
  );

  const automatic = reviewInput();
  automatic.review.method = "automatic";
  let calls = 0;
  await assert.rejects(
    createMotionPolicyAdoptionApi(async () => { calls += 1; return response(receipt()); })
      .adopt(PACKAGE, automatic),
    /人工采用/,
  );
  assert.equal(calls, 0);

  const draftBackup = {
    format: "autospine-motion-policy-review-draft-backup",
    format_version: 1,
    project_id: "sample-a",
    clip_id: "wave-left",
    adoptable: false,
    draft: { ...reviewInput(), review: { status: "draft", method: "unconfirmed", revision: 1 } },
  };
  await assert.rejects(
    createMotionPolicyAdoptionApi(async () => { calls += 1; return response(receipt()); })
      .adopt(PACKAGE, draftBackup),
    /复核输入字段无效/,
  );
  assert.equal(calls, 0);

  await assert.rejects(
    createMotionPolicyAdoptionApi(async () => response(
      { error: "conflict", message: "复核包已变化，请重新加载" },
      { ok: false, status: 409 },
    )).adopt(PACKAGE, reviewInput()),
    /复核包已变化/,
  );
});
