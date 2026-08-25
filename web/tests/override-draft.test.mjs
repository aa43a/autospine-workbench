import assert from "node:assert/strict";
import test from "node:test";

import {
  applyOverrideDraft,
  captureOverrideDraft,
  overrideDraftFromServer,
} from "../modules/override-draft.js";


const cloneMap = (value) => value && typeof value === "object"
  ? JSON.parse(JSON.stringify(value))
  : {};
const normalizers = {
  normalizeOverrideMap: cloneMap,
  normalizeLayerOverrideMap: cloneMap,
};

test("candidate decisions survive capture, server normalization, and apply", () => {
  const decision = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.left.pose.fixture",
    final_xy: [10, 20],
  };
  const state = {
    jointOverrides: {},
    jointDecisions: { "elbow.left": decision },
    layerOverrides: {},
    notes: "reviewed",
  };
  const captured = captureOverrideDraft(state);
  assert.deepEqual(captured.joint_decisions["elbow.left"], decision);

  const serverDraft = overrideDraftFromServer({}, captured, normalizers);
  const next = {};
  applyOverrideDraft(next, serverDraft, normalizers);
  assert.deepEqual(next.jointDecisions["elbow.left"], decision);
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
