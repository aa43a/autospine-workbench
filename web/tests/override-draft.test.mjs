import assert from "node:assert/strict";
import test from "node:test";

import {
  applyOverrideDraft,
  captureOverrideDraft,
  clientJointDecisions,
  overrideDraftFromServer,
  resolvedDecisionPoint,
} from "../modules/override-draft.js";
import { createDraftPatch } from "../modules/draft-transactions.js";


const cloneMap = (value) => value && typeof value === "object"
  ? JSON.parse(JSON.stringify(value))
  : {};
const normalizers = {
  normalizeOverrideMap: cloneMap,
  normalizeLayerOverrideMap: cloneMap,
};

test("candidate decisions survive capture without binder-derived accept fields", () => {
  const decision = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.left.pose.fixture",
    final_xy: [10, 20],
    analysis: { provider: "fixture" },
  };
  const state = {
    jointOverrides: {},
    jointDecisions: { "elbow.left": decision },
    layerOverrides: {},
    notes: "reviewed",
  };
  const captured = captureOverrideDraft(state);
  const clientDecision = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.left.pose.fixture",
  };
  assert.deepEqual(captured.joint_decisions["elbow.left"], clientDecision);

  const serverDraft = overrideDraftFromServer({}, captured, normalizers);
  const next = {};
  applyOverrideDraft(next, serverDraft, normalizers);
  assert.deepEqual(next.jointDecisions["elbow.left"], clientDecision);
  assert.equal(next.notes, "reviewed");
});

test("capture is isolated from later live mutations", () => {
  const state = {
    jointOverrides: {},
    jointDecisions: { root: { action: "unobservable", reason: "hidden" } },
    layerOverrides: {},
    notes: "",
  };
  const captured = captureOverrideDraft(state);
  state.jointDecisions.root.reason = "changed";
  assert.equal(captured.joint_decisions.root.reason, "hidden");
});

test("capture preserves manual adjust coordinates while stripping provenance", () => {
  const state = {
    jointOverrides: {},
    jointDecisions: { elbow: { action: "adjust", final_xy: [12, 24], reason: "contact", analysis: { provider: "x" } } },
    layerOverrides: {},
    notes: "",
  };
  assert.deepEqual(captureOverrideDraft(state).joint_decisions.elbow, {
    action: "adjust", final_xy: [12, 24], reason: "contact",
  });
});

test("server normalization never creates provenance-removal patch operations", () => {
  const serverDecision = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.left.pose.fixture",
    final_xy: [12, 24],
    analysis: { provider: "fixture" },
  };
  const persisted = overrideDraftFromServer(
    { joint_decisions: { "elbow.left": serverDecision } },
    {},
    normalizers,
  );
  const live = {
    ...persisted,
    joint_decisions: clientJointDecisions({ "elbow.left": serverDecision }),
  };
  assert.deepEqual(createDraftPatch(persisted, live), []);
});

test("split decisions never replay binder-derived fields to the save payload", () => {
  const stored = {
    action: "accept",
    split_artifact_sha256: "b".repeat(64),
    binding_status: "current",
    review_target_sha256: "c".repeat(64),
    analysis: { provider: "split-binder" },
  };
  const client = {
    action: "accept",
    split_artifact_sha256: "b".repeat(64),
  };
  const state = {
    jointOverrides: {}, jointDecisions: {}, layerOverrides: {}, notes: "",
    splitDecisions: { sleeves: stored },
  };
  assert.deepEqual(captureOverrideDraft(state).split_decisions, { sleeves: client });

  const draft = overrideDraftFromServer(
    { split_decisions: { sleeves: stored } },
    {},
    normalizers,
  );
  const next = {};
  applyOverrideDraft(next, draft, normalizers);
  assert.deepEqual(next.splitDecisions, { sleeves: client });
  assert.equal("binding_status" in next.splitDecisions.sleeves, false);
  assert.equal("analysis" in next.splitDecisions.sleeves, false);
});

test("resolved accept point is used only for the exact client decision identity", () => {
  const client = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.left.pose.fixture",
  };
  const resolved = { ...client, final_xy: [12, "24"], analysis: { provider: "x" } };
  assert.deepEqual(resolvedDecisionPoint(client, resolved), [12, 24]);
  assert.equal(
    resolvedDecisionPoint({ ...client, candidate_id: "other" }, resolved),
    null,
  );
  assert.equal(
    resolvedDecisionPoint(client, { ...resolved, final_xy: [Number.NaN, 24] }),
    null,
  );
});
