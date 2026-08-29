import assert from "node:assert/strict";
import test from "node:test";

import {
  applyBatchPreview, createBatchPreview,
} from "../modules/motion-policy-batch-model.js";
import {
  buildReviewInput, createReviewState, setDecision, setDecisionBatch,
  undoDecisionBatch,
} from "../modules/motion-policy-review-state.js";

const IDS = {
  blocked: `foot-${"1".repeat(64)}`,
  foot: `foot-${"2".repeat(64)}`,
  depth: `depth-${"3".repeat(64)}`,
};

function createModel() {
  return createReviewState({
    snapshotKey: "policy:foot:depth:inventory",
    projectId: "sample",
    clipId: "wave",
    loop: false,
    unconstrainedTicks: [],
    candidates: [
      {
        candidateId: IDS.blocked,
        kind: "foot_lock",
        tick: 10,
        footState: "rejected_limit",
      },
      {
        candidateId: IDS.foot,
        kind: "foot_lock",
        tick: 20,
        footState: "candidate",
      },
      {
        candidateId: IDS.depth,
        kind: "depth_order",
        tick: 30,
        slots: ["slot-a", "slot-b"],
      },
    ],
  });
}

test("preview freezes exact candidate IDs and reports overwrites", () => {
  const model = createModel();
  const depth = model.inventory.candidates[2];
  setDecision(model, depth, {
    action: "reject", reason_code: "manual-before-preview", payload: null,
  });
  const selected = [IDS.foot, IDS.depth];
  const preview = createBatchPreview(model, selected, {
    action: "unobservable", reason_code: "segment-hidden",
  });
  selected.splice(0, selected.length, IDS.blocked);
  assert.equal(Object.isFrozen(preview), true);
  assert.equal(Object.isFrozen(preview.candidateIds), true);
  assert.deepEqual(preview.candidateIds, [IDS.depth, IDS.foot]);
  assert.equal(preview.snapshotKey, model.snapshotKey);
  assert.equal(preview.overwriteCount, 1);
  assert.equal(preview.action, "unobservable");
});

test("batch validation is atomic and never invents a decision", () => {
  const model = createModel();
  assert.throws(() => setDecisionBatch(model, [IDS.foot], {
    action: "adjust", reason_code: "bulk-adjust", payload: null,
  }), /只允许/);
  assert.throws(() => setDecisionBatch(model, [IDS.foot], {
    action: "reject", reason_code: "", payload: null,
  }), /reason_code/);
  assert.throws(() => setDecisionBatch(model, [IDS.foot], {
    action: "reject", reason_code: "bulk-reject", payload: { automatic: true },
  }), /payload/);
  assert.throws(() => setDecisionBatch(model, [IDS.foot, IDS.blocked], {
    action: "accept", reason_code: "bulk-accept", payload: null,
  }), /禁止 accept/);
  assert.equal(model.decisions.size, 0);
  assert.equal(model.batchHistory.length, 0);
  assert.equal(model.nextBatchId, 1);
});

test("apply rejects stale snapshots, missing IDs and changed decisions", () => {
  const model = createModel();
  const preview = createBatchPreview(model, [IDS.foot], {
    action: "accept", reason_code: "segment-accept",
  });
  model.snapshotKey = "new-snapshot";
  assert.throws(() => applyBatchPreview(model, preview), /snapshot/);
  assert.equal(model.decisions.size, 0);

  model.snapshotKey = preview.snapshotKey;
  model.inventory.candidates = model.inventory.candidates.filter(
    (candidate) => candidate.candidateId !== IDS.foot,
  );
  assert.throws(() => applyBatchPreview(model, preview), /未知 candidate ID/);
  assert.equal(model.decisions.size, 0);

  const fresh = createModel();
  const stale = createBatchPreview(fresh, [IDS.depth], {
    action: "reject", reason_code: "segment-reject",
  });
  setDecision(fresh, fresh.inventory.candidates[1], {
    action: "reject", reason_code: "manual-change", payload: null,
  });
  assert.throws(() => applyBatchPreview(fresh, stale), /逐项决定变化/);
  assert.equal(fresh.decisions.has(IDS.depth), false);
});

test("undo preserves later manual edits and restores untouched rows", () => {
  const model = createModel();
  setDecision(model, model.inventory.candidates[1], {
    action: "accept", reason_code: "manual-original", payload: null,
  });
  const preview = createBatchPreview(model, [IDS.foot, IDS.depth], {
    action: "reject", reason_code: "segment-reject",
  });
  const applied = applyBatchPreview(model, preview);
  assert.equal(applied.overwriteCount, 1);
  assert.equal(model.batchHistory.length, 1);
  assert.equal(model.decisionSources.get(IDS.foot).batchId, applied.batchId);

  setDecision(model, model.inventory.candidates[2], {
    action: "unobservable", reason_code: "manual-after-batch", payload: null,
  });
  const undone = undoDecisionBatch(model, applied.batchId);
  assert.deepEqual(undone, {
    batchId: applied.batchId, restoredCount: 1, skippedCount: 1,
  });
  assert.deepEqual(model.decisions.get(IDS.foot), {
    action: "accept", reason_code: "manual-original", payload: null,
  });
  assert.equal(model.decisionSources.get(IDS.foot).kind, "manual");
  assert.deepEqual(model.decisions.get(IDS.depth), {
    action: "unobservable", reason_code: "manual-after-batch", payload: null,
  });
  assert.equal(model.decisionSources.get(IDS.depth).kind, "manual");
});

test("batch drafts still export only four fields with one row per candidate", () => {
  const model = createModel();
  applyBatchPreview(model, createBatchPreview(
    model,
    [IDS.blocked, IDS.foot, IDS.depth],
    { action: "reject", reason_code: "segment-review" },
  ));
  model.revision = 1;
  model.loopResetApproved = false;
  model.humanConfirmed = true;
  const output = buildReviewInput(model);
  assert.deepEqual(Object.keys(output), [
    "review", "decisions", "root_release_keys", "draw_order_loop_reset",
  ]);
  assert.deepEqual(
    output.decisions.map((row) => row.candidate_id),
    [IDS.depth, IDS.blocked, IDS.foot],
  );
  assert.equal(output.decisions.every((row) => (
    row.action === "reject" && row.reason_code === "segment-review" && row.payload === null
  )), true);
  assert.equal("batchHistory" in output, false);
  assert.equal("snapshotKey" in output, false);
});
