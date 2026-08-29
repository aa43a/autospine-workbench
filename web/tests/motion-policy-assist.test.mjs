import assert from "node:assert/strict";
import test from "node:test";

import {
  allSafeCandidateIds,
  ASSIST_PROFILE,
  ASSIST_REASON,
  assistedCoverage,
  isSafeAssistedCandidate,
  safeCandidateIdsForSampleRange,
} from "../modules/motion-policy-assist-model.js";
import { createMotionPolicyAssistController } from "../modules/motion-policy-assist-controller.js";
import {
  createReviewState,
  setDecision,
  setDecisionBatch,
  undoDecisionBatch,
} from "../modules/motion-policy-review-state.js";

function candidate(id, overrides = {}) {
  return { candidateId: id, kind: "foot_lock", footState: "candidate", ...overrides };
}

function sample(id, overrides = {}) {
  return {
    candidateId: id,
    correctionX: 2,
    correctionY: -1,
    correctionReferenceRatio: 0.2,
    maximumResidualPx: 4,
    observations: [{
      currentEndpointPx: [10, 20],
      desiredCorrectionPx: [2, -1],
      residualMagnitudePx: 1,
    }],
    ...overrides,
  };
}

function fixture() {
  const candidates = [candidate("foot-a"), candidate("foot-b"), candidate("foot-c")];
  const inventory = {
    candidates,
    unconstrainedTicks: [],
    loop: false,
    snapshotKey: "snapshot-a",
  };
  const model = {
    samples: [sample("foot-a"), sample("foot-b"), sample("foot-c")],
    candidatesById: new Map(candidates.map((row) => [row.candidateId, row])),
    contractLimits: { correctionReferenceRatio: 0.5, maximumResidualPx: 10 },
  };
  return { candidates, model, state: createReviewState(inventory) };
}

function assistedOptions(overrides = {}) {
  return {
    sourceKind: "assisted",
    profile: ASSIST_PROFILE,
    rule: ASSIST_REASON,
    trigger: "timeline",
    snapshotKey: "snapshot-a",
    ...overrides,
  };
}

test("safe assist accepts only observable Foot candidates inside the 80% safety margin", () => {
  const { candidates, model } = fixture();
  assert.equal(isSafeAssistedCandidate(candidates[0], model), true);

  model.samples[0] = sample("foot-a", {
    correctionReferenceRatio: 0.4,
    maximumResidualPx: 8,
  });
  assert.equal(isSafeAssistedCandidate(candidates[0], model), true, "boundary is inclusive");

  for (const unsafe of [
    candidate("foot-a", { kind: "depth_order" }),
    candidate("foot-a", { footState: "rejected_limit" }),
  ]) assert.equal(isSafeAssistedCandidate(unsafe, model), false);

  for (const override of [
    { correctionReferenceRatio: 0.400001 },
    { maximumResidualPx: 8.000001 },
    { correctionReferenceRatio: -0.01 },
    { maximumResidualPx: -0.01 },
    { correctionX: Number.NaN },
    { observations: [] },
    { observations: [{ currentEndpointPx: [10, Number.NaN], desiredCorrectionPx: [1, 2], residualMagnitudePx: 1 }] },
  ]) {
    model.samples[0] = sample("foot-a", override);
    assert.equal(isSafeAssistedCandidate(candidates[0], model), false);
  }
});

test("a timeline range adopts skipped frames once and never overwrites an existing decision", () => {
  const { candidates, model, state } = fixture();
  model.samples.splice(1, 0, { candidateId: null });
  model.samples.push(sample("foot-b"));
  setDecision(state, candidates[1], {
    action: "reject", reason_code: "manual-review", payload: null,
  });

  assert.deepEqual(
    safeCandidateIdsForSampleRange(model, state, model.samples.length - 1, 0),
    ["foot-a", "foot-c"],
  );
  assert.deepEqual(allSafeCandidateIds(model, state), ["foot-a", "foot-c"]);
  assert.deepEqual(assistedCoverage(model, state), {
    total: 3,
    safe: 3,
    adopted: 1,
    safePending: 2,
    exceptions: 0,
  });
});

test("assisted decisions record exact provenance and undo preserves a later manual edit", () => {
  const { candidates, state } = fixture();
  const applied = setDecisionBatch(state, ["foot-a", "foot-b"], {
    action: "accept", reason_code: ASSIST_REASON, payload: null,
  }, assistedOptions());

  assert.equal(applied.batchId, "assist-1");
  assert.deepEqual(state.decisionSources.get("foot-a"), {
    kind: "assisted",
    profile: ASSIST_PROFILE,
    rule: ASSIST_REASON,
    trigger: "timeline",
    snapshotKey: "snapshot-a",
    batchId: "assist-1",
  });
  assert.equal(state.batchHistory[0].sourceKind, "assisted");
  assert.deepEqual(state.batchHistory[0].provenance, {
    kind: "assisted",
    profile: ASSIST_PROFILE,
    rule: ASSIST_REASON,
    trigger: "timeline",
    snapshotKey: "snapshot-a",
  });

  setDecision(state, candidates[1], {
    action: "reject", reason_code: "manual-after-assist", payload: null,
  });
  const undone = undoDecisionBatch(state, applied.batchId);
  assert.deepEqual(undone, { batchId: "assist-1", restoredCount: 1, skippedCount: 1 });
  assert.equal(state.decisions.has("foot-a"), false);
  assert.equal(state.decisions.get("foot-b").action, "reject");
  assert.deepEqual(state.decisionSources.get("foot-b"), { kind: "manual" });
});

test("assisted decisions fail closed when profile, trigger, or snapshot provenance is invalid", () => {
  for (const options of [
    assistedOptions({ profile: "future-profile" }),
    assistedOptions({ trigger: "load" }),
    assistedOptions({ snapshotKey: "different-snapshot" }),
  ]) {
    const { state } = fixture();
    assert.throws(() => setDecisionBatch(state, ["foot-a"], {
      action: "accept", reason_code: ASSIST_REASON, payload: null,
    }, options), /自动辅助来源/);
    assert.equal(state.decisions.size, 0);
    assert.equal(state.batchHistory.length, 0);
  }
});

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.checked = false;
    this.disabled = false;
    this.dataset = {};
    this.attributes = {};
    this.textContent = "";
    this.value = 0;
    this.max = 1;
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
}

function controllerElements() {
  return Object.fromEntries([
    "autoApplyAllBtn", "autoUndoBtn", "approveOnScrub", "autoDownloadBtn",
    "autoDecisionStatus", "autoCoverageBar", "automationSummary",
  ].map((key) => [key, new FakeElement()]));
}

test("one timeline gesture creates one undoable assisted transaction", () => {
  const { model, state } = fixture();
  const ui = controllerElements();
  const changed = [];
  const located = [];
  const controller = createMotionPolicyAssistController(ui, {
    onChanged: (ids) => changed.push([...ids]),
    onLocate: (id) => located.push(id),
    onAdopt: () => {},
  });
  controller.load(state, model, { assistOnScrub: true });

  controller.applyRange(0, 2);
  assert.equal(state.batchHistory.length, 1);
  assert.deepEqual(state.batchHistory[0].candidateIds, ["foot-a", "foot-b", "foot-c"]);
  assert.deepEqual(changed, [["foot-a", "foot-b", "foot-c"]]);
  assert.equal(ui.autoUndoBtn.disabled, false);
  assert.match(ui.automationSummary.textContent, /3\/3/);

  ui.autoUndoBtn.dispatchEvent(new Event("click"));
  assert.equal(state.decisions.size, 0);
  assert.equal(state.batchHistory[0].undone, true);
  assert.equal(ui.autoUndoBtn.disabled, true);
  assert.deepEqual(changed.at(-1), []);
  assert.deepEqual(located, []);
});

test("turning timeline assistance off locates evidence without writing a decision", () => {
  const { model, state } = fixture();
  const ui = controllerElements();
  const located = [];
  const controller = createMotionPolicyAssistController(ui, {
    onChanged: () => {},
    onLocate: (id) => located.push(id),
    onAdopt: () => {},
  });
  controller.load(state, model, { assistOnScrub: false });
  controller.applyRange(0, 2);

  assert.deepEqual(located, ["foot-c"]);
  assert.equal(state.decisions.size, 0);
  assert.equal(state.batchHistory.length, 0);
});
