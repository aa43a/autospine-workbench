import assert from "node:assert/strict";
import test from "node:test";

import {
  createSeamAnchorReviewApi, seamReviewPublicationPath,
} from "../modules/seam-anchor-review-api.js";
import {
  SEAM_PUBLICATION_INTENT, buildSeamPublicationRequest,
  normalizeSeamPublicationReceipt, normalizeSeamReviewDecisionReceipt,
} from "../modules/seam-anchor-review-publication.js";
import {
  SeamReviewSubmitControllerError, createSeamReviewSubmitController,
} from "../modules/seam-anchor-review-submit-controller.js";
import {
  verifiedCommittedRevision,
} from "../modules/seam-anchor-review-submit-flow.js";

const PACKAGE = "3".repeat(64);
const CANDIDATE = "d".repeat(64);
const DECISION = "2".repeat(64);
const REVIEWED_SET = "4".repeat(64);
const BUNDLE = "5".repeat(64);

const READY_REASONS = [
  "dynamic_seam_safety_unproven",
  "reviewed_seam_anchor_set_missing",
  "runtime_equivalence_unproven",
  "visual_seam_quality_unproven",
];
const BLOCKED_REASONS = [
  "dynamic_seam_safety_unproven",
  "reviewed_seam_anchor_selection_blocked",
  "reviewed_seam_anchor_set_missing",
  "runtime_equivalence_unproven",
  "visual_seam_quality_unproven",
];

function decisionReceipt(blocked = false) {
  return {
    candidate_sha256: CANDIDATE,
    decision_sha256: DECISION,
    revision: 1,
    status: blocked
      ? "reviewed_anchor_set_blocked"
      : "reviewed_anchor_set_ready_for_compile",
    release_gate: {
      status: "blocked",
      reason_codes: blocked ? BLOCKED_REASONS : READY_REASONS,
    },
    summary: blocked ? {
      relationship_count: 6, accept_count: 2, adjust_count: 0,
      reject_count: 0, unobservable_count: 4, anchor_pair_count: 4,
    } : {
      relationship_count: 6, accept_count: 6, adjust_count: 0,
      reject_count: 0, unobservable_count: 0, anchor_pair_count: 12,
    },
    reused: false,
  };
}

function publicationReceipt(overrides = {}) {
  return {
    format: "autospine-reviewed-seam-anchor-set-receipt",
    format_version: 1,
    status: "passed",
    package_id: PACKAGE,
    source: {
      project_id: "sample.project",
      candidate_sha256: CANDIDATE,
      review_revision: 1,
      decision_sha256: DECISION,
    },
    address: {
      project_id: "sample.project",
      reviewed_set_sha256: REVIEWED_SET,
      bundle_sha256: BUNDLE,
    },
    verification: {
      status: "passed",
      replayed_from_exact_upstreams: true,
      head_observation: {
        method: "double_snapshot", scope: "compile_time", revision: 1,
        head_decision_sha256: DECISION, permanent_authority_claimed: false,
      },
    },
    release_gate: {
      status: "blocked",
      reason_codes: [
        "dynamic_seam_safety_unproven",
        "runtime_equivalence_unproven",
        "visual_seam_quality_unproven",
      ],
    },
    summary: { relationship_count: 6, anchor_pair_count: 12 },
    ...overrides,
  };
}

function jsonResponse(status, payload) {
  return {
    status, ok: status >= 200 && status < 300,
    headers: { get: () => "application/json" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

function submitInput(packageId = PACKAGE) {
  return {
    address: { projectId: "sample.project" },
    candidateSha256: CANDIDATE,
    payload: { exact: "P10.5b payload" },
    packageId,
  };
}


test("P10.5c API posts one exact intent-bound request and returns a path-free receipt", async () => {
  const request = buildSeamPublicationRequest(PACKAGE, decisionReceipt());
  const calls = [];
  const api = createSeamAnchorReviewApi(async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, publicationReceipt());
  });

  const result = await api.publish(PACKAGE, request);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, seamReviewPublicationPath(PACKAGE));
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(
    calls[0].options.headers["X-Autospine-Intent"], SEAM_PUBLICATION_INTENT,
  );
  assert.deepEqual(JSON.parse(calls[0].options.body), request);
  assert.equal(result.address.reviewedSetSha256, REVIEWED_SET);
  assert.equal(result.verification.replayedFromExactUpstreams, true);
  assert.doesNotMatch(JSON.stringify(result), /path|\\|E:\//);
});

test("strict normalizers reject extra paths and every stale identity boundary", () => {
  const request = buildSeamPublicationRequest(PACKAGE, decisionReceipt());
  const badDecision = decisionReceipt();
  badDecision.output_path = "E:/private/decision.json";
  assert.throws(() => normalizeSeamReviewDecisionReceipt(badDecision), /字段无效/);

  const cases = [
    (row) => { row.path = "E:/private/result.json"; },
    (row) => { row.package_id = "6".repeat(64); },
    (row) => { row.source.candidate_sha256 = "7".repeat(64); },
    (row) => { row.address.project_id = "other.project"; },
    (row) => { row.verification.head_observation.revision = 2; },
    (row) => { row.verification.head_observation.permanent_authority_claimed = true; },
    (row) => { row.release_gate.reason_codes.pop(); },
    (row) => { row.summary.anchor_pair_count = 49; },
  ];
  for (const mutate of cases) {
    const payload = publicationReceipt();
    mutate(payload);
    assert.throws(() => normalizeSeamPublicationReceipt(payload, request));
  }
});

test("controller submits P10.5b once, publishes ready P10.5c, and keeps exact identities", async () => {
  const calls = [];
  const changes = [];
  let validated = 0;
  const api = {
    submit: async (...args) => { calls.push(["decision", ...args]); return decisionReceipt(); },
    publish: async (packageId, request) => {
      calls.push(["publication", packageId, request]);
      return normalizeSeamPublicationReceipt(publicationReceipt(), request);
    },
  };
  const controller = createSeamReviewSubmitController({
    api, onChange: (state) => changes.push(state.phase),
    validateDecision: (raw, normalized) => {
      validated += 1;
      assert.equal(raw.revision, 1);
      assert.equal(normalized.summary.relationshipCount, 6);
    },
  });

  const result = await controller.submit(submitInput());

  assert.equal(calls.filter(([kind]) => kind === "decision").length, 1);
  assert.equal(calls.filter(([kind]) => kind === "publication").length, 1);
  assert.equal(validated, 1);
  assert.deepEqual(calls[1][2], buildSeamPublicationRequest(PACKAGE, decisionReceipt()));
  assert.equal(result.phase, "complete");
  assert.equal(result.decisionCommitted, true);
  assert.equal(verifiedCommittedRevision(result), 1);
  assert.equal(result.retryPublication, false);
  assert.equal(result.publication.address.bundleSha256, BUNDLE);
  assert.deepEqual(changes, [
    "submitting_decision", "submitting_decision", "submitting_decision",
    "publishing", "complete",
  ]);

  assert.equal(await controller.submit(submitInput()), result);
  assert.equal(calls.filter(([kind]) => kind === "decision").length, 1);
});

test("a failed P10.5c keeps publication-only retry and never resubmits P10.5b", async () => {
  let decisionCalls = 0;
  let publicationCalls = 0;
  const api = {
    submit: async () => { decisionCalls += 1; return decisionReceipt(); },
    publish: async (_packageId, request) => {
      publicationCalls += 1;
      if (publicationCalls === 1) throw new Error("E:/private must not leak");
      return normalizeSeamPublicationReceipt(publicationReceipt(), request);
    },
  };
  const controller = createSeamReviewSubmitController({ api });

  await assert.rejects(
    controller.submit(submitInput()),
    (error) => error instanceof SeamReviewSubmitControllerError
      && error.code === "publication_failed"
      && !error.message.includes("private"),
  );
  assert.equal(controller.snapshot().phase, "publication_retry_required");
  assert.equal(controller.snapshot().retryPublication, true);
  assert.deepEqual(controller.snapshot().failure, {
    stage: "publication", code: "publication_failed",
  });

  const result = await controller.submit(submitInput());
  assert.equal(result.phase, "complete");
  assert.equal(decisionCalls, 1);
  assert.equal(publicationCalls, 2);
});

test("blocked decisions and missing packages stop before P10.5c", async () => {
  for (const [rawDecision, packageId, expectedPhase] of [
    [decisionReceipt(true), PACKAGE, "decision_blocked"],
    [decisionReceipt(false), null, "decision_ready_without_package"],
  ]) {
    let publications = 0;
    const controller = createSeamReviewSubmitController({
      api: {
        submit: async () => rawDecision,
        publish: async () => { publications += 1; throw new Error("must not publish"); },
      },
    });
    const result = await controller.submit(submitInput(packageId));
    assert.equal(result.phase, expectedPhase);
    assert.equal(result.decisionCommitted, true);
    assert.equal(publications, 0);
  }
});

test("invalid or uncertain decision receipts fail closed without a second decision POST", async () => {
  let calls = 0;
  const malformed = decisionReceipt();
  malformed.internal_path = "E:/private/head.json";
  const controller = createSeamReviewSubmitController({
    api: {
      submit: async () => { calls += 1; return malformed; },
      publish: async () => { throw new Error("must not publish"); },
    },
  });
  await assert.rejects(
    controller.submit(submitInput()),
    (error) => error.code === "decision_receipt_invalid",
  );
  assert.equal(controller.snapshot().decisionCommitted, true);
  assert.equal(verifiedCommittedRevision(controller.snapshot()), null);
  assert.equal(controller.snapshot().failure.code, "decision_receipt_invalid");
  assert.equal(await controller.submit(submitInput()), controller.snapshot());
  assert.equal(calls, 1);

  const invalidPackageController = createSeamReviewSubmitController({
    api: {
      submit: async () => { calls += 1; return decisionReceipt(); },
      publish: async () => publicationReceipt(),
    },
  });
  await assert.rejects(
    invalidPackageController.submit(submitInput("A".repeat(64))),
    /小写十六进制/,
  );
  assert.equal(calls, 1);
});
