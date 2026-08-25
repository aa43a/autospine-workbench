import assert from "node:assert/strict";
import test from "node:test";

import {
  acceptedCandidatePoint,
  applyCandidateDecision,
  buildJointDecision,
  createCandidateReviewState,
  decisionMatchesArtifact,
  decisionMatchesSelection,
  reduceCandidateReview,
  selectCandidateId,
  syncedReasonValue,
} from "../modules/candidate-review-state.js";

const SHA = "a".repeat(64);
const candidate = (id, x) => ({
  candidate_id: id,
  xy: [x, 20],
  method: `method-${id}`,
  score_kind: "heuristic",
  heuristic_score: 0.7,
  source_layer_ids: [],
  evidence: [{ kind: "audit_source", source_ref: "fixture", note: "test" }],
  qa_flags: [],
});
const artifact = {
  format: "autospine-joint-candidates",
  format_version: 1,
  project_id: "fixture",
  joints: {
    elbow: { observability: "visible", candidates: [candidate("first", 10), candidate("second", 30)] },
  },
};

test("reducer keeps artifact, joint, and candidate selection deterministic", () => {
  let state = createCandidateReviewState();
  state = reduceCandidateReview(state, { type: "project-loading", projectId: "fixture" });
  state = reduceCandidateReview(state, {
    type: "index-loaded",
    payload: {
      kind: "joint-candidates",
      project_id: "fixture",
      items: [{
        artifact_sha256: SHA,
        provider: "fixture",
        provider_version: "1",
        joint_count: 1,
        candidate_count: 2,
        qa_status: "manual_required",
        qa_flags: [],
        method_counts: { fixture: 2 },
      }],
    },
  });
  assert.equal(state.artifactSha, SHA);
  state = reduceCandidateReview(state, { type: "joint-selected", jointId: "elbow", preferredId: "second" });
  state = reduceCandidateReview(state, { type: "artifact-loaded", payload: artifact, preferredId: "second" });
  assert.equal(state.status, "ready");
  assert.equal(state.candidateId, "second");

  state = reduceCandidateReview(state, { type: "candidate-selected", candidateId: "first" });
  assert.equal(state.candidateId, "first");
  state = reduceCandidateReview(state, { type: "candidate-selected", candidateId: "missing" });
  assert.equal(state.candidateId, "first");
  assert.equal(selectCandidateId({ artifact, jointId: "unknown", preferredId: "first" }), null);
});

test("accept payload pins evidence but never submits binder-derived final_xy", () => {
  const decision = buildJointDecision({
    action: "accept",
    artifactSha: SHA,
    candidateId: "first",
    point: [99, 88],
    reason: "looks correct",
  });
  assert.deepEqual(decision, {
    action: "accept",
    candidate_artifact_sha256: SHA,
    candidate_id: "first",
    reason: "looks correct",
  });
  assert.equal("final_xy" in decision, false);
  assert.equal("analysis" in decision, false);
});

test("accepted candidate point is a transient preview, not request data", () => {
  const decision = buildJointDecision({
    action: "accept", artifactSha: SHA, candidateId: "second", point: [99, 88],
  });
  assert.deepEqual(acceptedCandidatePoint(artifact, "elbow", decision), [30, 20]);
  assert.equal("final_xy" in decision, false);
  assert.equal(acceptedCandidatePoint(artifact, "other", decision), null);
});

test("a pinned decision never appears active on a different artifact", () => {
  const decision = buildJointDecision({
    action: "accept", artifactSha: SHA, candidateId: "first",
  });
  assert.equal(decisionMatchesArtifact(decision, SHA), true);
  assert.equal(decisionMatchesArtifact(decision, "b".repeat(64)), false);
  assert.equal(decisionMatchesArtifact(null, SHA), false);
});

test("candidate decisions require exact artifact and candidate identity", () => {
  const decision = buildJointDecision({
    action: "accept", artifactSha: SHA, candidateId: "first",
  });
  assert.equal(decisionMatchesSelection(decision, SHA, "first"), true);
  assert.equal(decisionMatchesSelection(decision, SHA, "second"), false);
  assert.equal(decisionMatchesSelection(decision, "b".repeat(64), "first"), false);
  const unobservable = buildJointDecision({
    action: "unobservable", artifactSha: SHA, reason: "occluded",
  });
  assert.equal(decisionMatchesSelection(unobservable, SHA, null), true);
  assert.equal(decisionMatchesSelection(unobservable, "b".repeat(64), null), false);
});

test("unobservable review clears the selected candidate", () => {
  let state = { ...createCandidateReviewState(), projectId: "fixture", artifact, jointId: "elbow" };
  state = reduceCandidateReview(state, {
    type: "joint-selected", jointId: "elbow", preferredId: "second",
  });
  assert.equal(state.candidateId, "second");
  state = reduceCandidateReview(state, {
    type: "joint-selected", jointId: "elbow", clearCandidate: true,
  });
  assert.equal(state.candidateId, null);
  state = reduceCandidateReview(state, { type: "candidate-selected", candidateId: "first" });
  assert.equal(state.candidateId, "first");
});

test("reason synchronization clears stale decisions but preserves user edits", () => {
  assert.equal(syncedReasonValue({
    currentValue: "old reason",
    lastSyncedReason: "old reason",
    nextReason: "",
    jointChanged: false,
    decisionChanged: true,
  }), "");
  assert.equal(syncedReasonValue({
    currentValue: "unsaved note",
    lastSyncedReason: "old reason",
    nextReason: "",
    jointChanged: false,
    decisionChanged: true,
  }), "unsaved note");
  assert.equal(syncedReasonValue({
    currentValue: "unsaved note",
    lastSyncedReason: "",
    nextReason: "other joint reason",
    jointChanged: true,
    decisionChanged: true,
  }), "other joint reason");
});

test("adjust, reject, and unobservable payloads match the write contract", () => {
  assert.deepEqual(buildJointDecision({
    action: "adjust", artifactSha: SHA, candidateId: "first", point: [12.34, 56.78], reason: "move to contact",
  }), {
    action: "adjust",
    candidate_artifact_sha256: SHA,
    candidate_id: "first",
    final_xy: [12.3, 56.8],
    reason: "move to contact",
  });
  const rejected = buildJointDecision({
    action: "reject", artifactSha: SHA, candidateId: "second", reason: "wrong limb",
  });
  assert.equal(rejected.candidate_id, "second");
  assert.equal("final_xy" in rejected, false);
  assert.deepEqual(buildJointDecision({
    action: "unobservable", artifactSha: SHA, candidateId: "ignored", reason: "fully occluded",
  }), {
    action: "unobservable",
    candidate_artifact_sha256: SHA,
    reason: "fully occluded",
  });
});

test("required reasons and candidate selection fail before draft mutation", () => {
  assert.throws(
    () => buildJointDecision({ action: "adjust", artifactSha: SHA, candidateId: "first", point: [1, 2] }),
    /需要填写理由/,
  );
  assert.throws(
    () => buildJointDecision({ action: "accept", artifactSha: SHA }),
    /选择一个候选点/,
  );
});

test("candidate decision replaces a mutually exclusive manual joint override", () => {
  const state = {
    jointOverrides: { elbow: { x: 1, y: 2 }, wrist: { x: 3, y: 4 } },
    jointDecisions: {},
  };
  const decision = buildJointDecision({ action: "accept", artifactSha: SHA, candidateId: "first" });
  applyCandidateDecision(state, "elbow", decision);
  assert.equal("elbow" in state.jointOverrides, false);
  assert.deepEqual(state.jointOverrides.wrist, { x: 3, y: 4 });
  assert.deepEqual(state.jointDecisions.elbow, decision);
});

test("corrupt detail payload becomes an explicit reducer error", () => {
  let state = { ...createCandidateReviewState(), projectId: "fixture", jointId: "elbow" };
  assert.throws(
    () => reduceCandidateReview(state, { type: "artifact-loaded", payload: { project_id: "fixture" } }),
    /结构损坏/,
  );
  state = reduceCandidateReview(state, { type: "failed", error: new Error("backend failed") });
  assert.equal(state.status, "error");
  assert.equal(state.error.message, "backend failed");
});
