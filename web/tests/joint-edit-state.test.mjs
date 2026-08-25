import assert from "node:assert/strict";
import test from "node:test";

import {
  applyManualJoint,
  clearJointEdits,
  resolveEffectiveJoint,
} from "../modules/joint-edit-state.js";


function stateFixture() {
  return {
    jointOverrides: {},
    jointDecisions: {},
    resolvedJointDecisions: {},
  };
}

test("resolved server point applies only to its matching accept decision", () => {
  const state = stateFixture();
  const decision = {
    action: "accept",
    candidate_artifact_sha256: "a".repeat(64),
    candidate_id: "elbow.pose.1",
  };
  state.jointDecisions.elbow = decision;
  state.resolvedJointDecisions.elbow = { ...decision, final_xy: [12, 24] };
  assert.deepEqual(
    resolveEffectiveJoint({ id: "elbow", x: 1, y: 2 }, state),
    {
      id: "elbow", x: 12, y: 24, reviewAction: "accept", isManual: false,
    },
  );
  state.jointDecisions.elbow.candidate_id = "elbow.pose.2";
  const changed = resolveEffectiveJoint(
    { id: "elbow", x: 1, y: 2 },
    state,
    [30, 40],
  );
  assert.deepEqual([changed.x, changed.y], [30, 40]);
});

test("manual edit supersedes and clears a review decision", () => {
  const state = stateFixture();
  state.jointDecisions.elbow = { action: "reject" };
  applyManualJoint(state, "elbow", 12.34, 56.78);
  assert.deepEqual(state.jointOverrides.elbow, { x: 12.3, y: 56.8 });
  assert.equal(state.jointDecisions.elbow, undefined);
  const joint = resolveEffectiveJoint({ id: "elbow", x: 1, y: 2 }, state);
  assert.deepEqual([joint.x, joint.y, joint.isManual], [12.3, 56.8, true]);
});

test("reset clears client edits without mutating resolved server metadata", () => {
  const state = stateFixture();
  state.jointOverrides.elbow = { x: 12, y: 24 };
  state.jointDecisions.elbow = { action: "adjust", final_xy: [12, 24] };
  state.resolvedJointDecisions.elbow = { action: "accept", final_xy: [9, 18] };
  clearJointEdits(state, "elbow");
  assert.equal(state.jointOverrides.elbow, undefined);
  assert.equal(state.jointDecisions.elbow, undefined);
  assert.deepEqual(state.resolvedJointDecisions.elbow.final_xy, [9, 18]);
});
