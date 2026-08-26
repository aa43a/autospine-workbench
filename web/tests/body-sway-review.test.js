import assert from "node:assert/strict";
import test from "node:test";

import {
  bodySwayReviewPaths, normalizeReviewAddress,
} from "../modules/body-sway-review-address.js";
import {
  BodySwayReviewApiError, REVIEW_INTENT, createBodySwayReviewApi,
} from "../modules/body-sway-review-api.js";
import {
  currentHeadBaseline, normalizeHistoryEnvelope,
} from "../modules/body-sway-review-history.js";
import {
  buildReviewSubmission, clearReviewForAddress, createBusyGate,
  createBusyGroup, createRequestSequence, createReviewState,
  markSubmissionConflict, normalizeCandidateEnvelope, setCaseDecision,
  setCaseNotes,
} from "../modules/body-sway-review-state.js";

const SHA = {
  preview: "a".repeat(64), bundle: "b".repeat(64), artifact: "c".repeat(64),
  candidate: "d".repeat(64), evidence: "e".repeat(64), png: "f".repeat(64),
  decision: "1".repeat(64),
};
const ADDRESS = normalizeReviewAddress({
  projectId: "sample.project", previewSha256: SHA.preview,
  bundleSha256: SHA.bundle, artifactSha256: SHA.artifact,
});

function candidateEnvelope() {
  const cases = ["setup", "combined-t001000000", "combined-t002000000"].map(
    (caseId, index) => ({
      case_id: caseId,
      animation: index ? "p10.body-sway" : null,
      tick: index * 1_000_000,
      time_seconds: index,
      evidence_sha256: SHA.evidence,
      image: {
        png_sha256: SHA.png, size_bytes: 4096 + index,
        width: 640, height: 640,
      },
    }),
  );
  return {
    candidate_sha256: SHA.candidate,
    candidate: {
      project_id: ADDRESS.projectId,
      status: "candidate_only",
      source: {
        temporary_preview_sha256: ADDRESS.previewSha256,
        runtime_capture_bundle_sha256: ADDRESS.bundleSha256,
        capture_artifact_set_sha256: ADDRESS.artifactSha256,
      },
      release_gate: {
        status: "blocked",
        reason_codes: ["manual_visual_review_required", "safe_range_unproven"],
      },
      cases,
    },
  };
}

function jsonResponse(status, payload) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: () => "application/json" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

test("does not discover or auto-select an address before explicit load", async () => {
  const calls = [];
  const api = createBodySwayReviewApi(async (...args) => {
    calls.push(args);
    return jsonResponse(200, candidateEnvelope());
  });
  assert.equal(calls.length, 0);
  await api.loadCandidate(ADDRESS);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], bodySwayReviewPaths(ADDRESS).candidate());
  assert.match(calls[0][0], new RegExp(`/${SHA.preview}/${SHA.bundle}/${SHA.artifact}/`));
});

test("rejects uppercase and partial SHA addresses", () => {
  assert.throws(() => normalizeReviewAddress({
    ...ADDRESS, previewSha256: "A".repeat(64),
  }), /小写十六进制/);
  assert.throws(() => normalizeReviewAddress({
    ...ADDRESS, bundleSha256: "b".repeat(63),
  }), /64 位/);
});

test("address changes clear evidence and ignore a late fetch response", async () => {
  let release;
  const delayed = new Promise((resolve) => { release = resolve; });
  const api = createBodySwayReviewApi(() => delayed);
  const requests = createRequestSequence();
  const token = requests.next();
  const pending = api.loadCandidate(ADDRESS);
  const dirty = {
    ...createReviewState(), candidate: { cases: [] }, history: { items: [] },
    baseline: { revision: 1 }, decisions: { setup: { action: "approve" } },
    reviewerId: "reviewer", reviewNotes: "draft",
  };
  const cleared = clearReviewForAddress(dirty);
  requests.invalidate();
  release(jsonResponse(200, candidateEnvelope()));
  const result = await pending;
  assert.equal(requests.isCurrent(token), false);
  assert.equal(result.candidate_sha256, SHA.candidate);
  assert.equal(cleared.candidate, null);
  assert.equal(cleared.history, null);
  assert.equal(cleared.baseline, null);
  assert.deepEqual(cleared.decisions, {});
  assert.equal(cleared.reviewerId, "");
});

test("candidate cases preserve service order", () => {
  const normalized = normalizeCandidateEnvelope(candidateEnvelope(), ADDRESS);
  assert.deepEqual(
    normalized.candidate.cases.map((row) => row.case_id),
    ["setup", "combined-t001000000", "combined-t002000000"],
  );
});

test("candidate rejects internal image paths at the public boundary", () => {
  const envelope = candidateEnvelope();
  envelope.candidate.cases[0].image.path = "captures/setup.png";
  assert.throws(
    () => normalizeCandidateEnvelope(envelope, ADDRESS),
    /case 元数据/,
  );
});

test("submission contains only the human CAS contract", () => {
  const normalized = normalizeCandidateEnvelope(candidateEnvelope(), ADDRESS);
  const decisions = Object.fromEntries(normalized.candidate.cases.map((row, index) => [
    row.case_id,
    { action: index ? "approve" : "reject", notes: index ? "" : "bad seam" },
  ]));
  const payload = buildReviewSubmission({
    ...createReviewState(), candidate: normalized.candidate,
    candidateSha256: normalized.candidateSha256,
    baseline: { revision: 2, decisionSha256: SHA.decision },
    reviewerId: "qa.operator", reviewNotes: "sampled only", decisions,
  });
  assert.deepEqual(Object.keys(payload).sort(), [
    "base_revision", "candidate_sha256", "decisions",
    "previous_decision_sha256", "review",
  ]);
  assert.deepEqual(Object.keys(payload.review).sort(), ["notes", "reviewer_id"]);
  assert.deepEqual(Object.keys(payload.decisions[0]).sort(), [
    "action", "case_id", "evidence_sha256", "notes",
  ]);
  assert.equal(JSON.stringify(payload).includes("source"), false);
  assert.equal(JSON.stringify(payload).includes("image"), false);
  assert.equal(JSON.stringify(payload).includes("status"), false);
});

test("PUT uses the exact intent header and one request", async () => {
  const calls = [];
  const api = createBodySwayReviewApi(async (...args) => {
    calls.push(args);
    return jsonResponse(200, { candidate_sha256: SHA.candidate });
  });
  const body = { base_revision: 0 };
  await api.submit(ADDRESS, SHA.candidate, body);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1].method, "PUT");
  assert.equal(calls[0][1].headers["X-Autospine-Intent"], REVIEW_INTENT);
  assert.equal(calls[0][1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0][1].body), body);
});

test("409 preserves the draft and never retries silently", async () => {
  let calls = 0;
  const api = createBodySwayReviewApi(async () => {
    calls += 1;
    return jsonResponse(409, { error: "stale_revision", message: "stale" });
  });
  const before = {
    ...createReviewState(),
    history: { currentRevision: 2, headDecisionSha256: SHA.decision, items: [] },
    selectedDecision: { review: { revision: 1 } },
    baseline: { revision: 2, decisionSha256: SHA.decision },
    decisions: { setup: { action: "reject", notes: "tear" } },
    reviewerId: "qa", reviewNotes: "keep me",
  };
  let after = before;
  await assert.rejects(
    () => api.submit(ADDRESS, SHA.candidate, { base_revision: 2 }),
    (error) => error instanceof BodySwayReviewApiError && error.status === 409,
  );
  after = markSubmissionConflict(after);
  after = {
    ...after,
    candidate: candidateEnvelope().candidate,
  };
  after = setCaseDecision(after, "setup", "reject", "still stale");
  after = setCaseNotes(after, "setup", "edited after conflict");
  assert.equal(calls, 1);
  assert.deepEqual(after.decisions.setup, {
    action: "reject", notes: "edited after conflict",
  });
  assert.equal(after.history, null);
  assert.equal(after.selectedDecision, null);
  assert.equal(after.baseline, null);
  assert.equal(after.reviewNotes, "keep me");
  assert.equal(after.stale, true);
});

test("busy gates release canceled work without unlocking a newer peer", () => {
  const changes = [];
  const gate = createBusyGate((busy) => changes.push(busy));
  const first = gate.begin();
  gate.finish(first);
  const older = gate.begin();
  const newer = gate.begin();
  gate.finish(older);
  assert.equal(changes.at(-1), true);
  gate.finish(newer);
  assert.deepEqual(changes, [true, false, true, true, false]);
});

test("busy group preserves a mutation lock when a history request ends", () => {
  const snapshots = [];
  const group = createBusyGroup(
    ["history", "mutation"], (value) => snapshots.push(value),
  );
  const history = group.gate("history");
  const mutation = group.gate("mutation");
  const historyToken = history.begin();
  const mutationToken = mutation.begin();
  history.finish(historyToken);
  assert.deepEqual(snapshots.at(-1), { history: false, mutation: true });
  mutation.finish(mutationToken);
  assert.deepEqual(snapshots.at(-1), { history: false, mutation: false });
});

test("history requires explicit revision and explicit head baseline actions", () => {
  const envelope = {
    candidate_sha256: SHA.candidate,
    current_revision: 1,
    head_decision_sha256: SHA.decision,
    items: [{ revision: 1, decision_sha256: SHA.decision,
      status: "sampled_visual_approved" }],
  };
  const history = normalizeHistoryEnvelope(envelope, SHA.candidate);
  const state = { ...createReviewState(), history };
  assert.equal(state.selectedDecision, null);
  assert.equal(state.baseline, null);
  assert.deepEqual(currentHeadBaseline(history), {
    revision: 1, decisionSha256: SHA.decision,
  });
});
