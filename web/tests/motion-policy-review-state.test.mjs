import assert from "node:assert/strict";
import test from "node:test";

import {
  buildReviewInput, createReviewState, reviewProgress, setDecision, setRelease,
  validateDecision,
} from "../modules/motion-policy-review-state.js";

test("review state preserves human gates and exports only the four CLI input fields", () => {
  const blocked = {
    candidateId: `foot-${"1".repeat(64)}`, kind: "foot_lock", tick: 10,
    footState: "rejected_limit",
  };
  const depth = {
    candidateId: `depth-${"2".repeat(64)}`, kind: "depth_order", tick: 20,
    slots: ["slot-a", "slot-b"],
  };
  const state = createReviewState({
    candidates: [depth, blocked], unconstrainedTicks: [30], loop: false,
    projectId: "sample", clipId: "wave",
  });
  assert.match(setDecision(state, blocked, {
    action: "accept", reason_code: "manual", payload: null,
  }), /禁止 accept/);
  assert.match(validateDecision(blocked, {
    action: "adjust", reason_code: "manual-adjust", payload: { x: "", y: " " },
  }), /有限/);
  assert.match(validateDecision(blocked, {
    action: "adjust", reason_code: "manual-adjust", payload: { x: null, y: false },
  }), /有限/);
  assert.equal(setDecision(state, blocked, {
    action: "adjust", reason_code: "manual-adjust", payload: { x: 1.25, y: -2 },
  }), "");
  assert.equal(setDecision(state, depth, {
    action: "adjust", reason_code: "manual-front", payload: { frontSlot: "slot-b" },
  }), "");
  assert.throws(() => setRelease(state, 20, {}), /unconstrained/);
  setRelease(state, 30, {
    x: "", y: " ", interpolation: "stepped", reasonCode: "release-zero",
  });
  assert.match(
    reviewProgress(state).errors.find((row) => row.candidateId === "release-30").message,
    /有限/,
  );
  setRelease(state, 30, {
    x: 0, y: 0, interpolation: "stepped", reasonCode: "release-zero",
  });
  state.revision = 1;
  state.loopResetApproved = true;
  assert.match(reviewProgress(state).errors.at(-1).message, /非 loop/);
  state.loopResetApproved = false;
  assert.equal(reviewProgress(state).ready, true);
  state.humanConfirmed = true;
  const result = buildReviewInput(state);
  assert.deepEqual(Object.keys(result), [
    "review", "decisions", "root_release_keys", "draw_order_loop_reset",
  ]);
  assert.deepEqual(
    result.decisions.map((row) => row.candidate_id),
    [depth.candidateId, blocked.candidateId],
  );
  assert.deepEqual(result.decisions[0].payload, { final_front_slot: "slot-b" });
  assert.deepEqual(result.decisions[1].payload, { final_correction_xy_px: [1.25, -2] });
  assert.deepEqual(result.root_release_keys[0], {
    tick: 30,
    correction_xy_px: [0, 0],
    incoming_interpolation: "stepped",
    reason_code: "release-zero",
  });
});
