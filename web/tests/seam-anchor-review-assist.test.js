import assert from "node:assert/strict";
import test from "node:test";

import { createSeamAssistController } from "../modules/seam-anchor-review-assist-controller.js";
import {
  acceptBatchEligibleSeamAssist, prefillSeamAssist,
} from "../modules/seam-anchor-review-assist.js";
import { normalizedState } from "./seam-anchor-review-fixtures.js";

test("prefill selects deterministic options without inventing approval", () => {
  const state = prefillSeamAssist(normalizedState());
  for (const relationship of state.candidate.relationships) {
    const choice = state.decisions[relationship.relationship_id];
    assert.equal(choice.optionId, relationship.options[0].option_id);
    assert.equal(choice.action, null);
  }
});

test("batch assist changes only local draft and can be undone", () => {
  let state = normalizedState();
  let rendered = 0;
  let canUndo = false;
  const controller = createSeamAssistController({
    getState: () => state,
    setState: (next) => { state = next; },
    onRender: () => { rendered += 1; },
    onStatus: () => {},
    onUndoAvailability: (value) => { canUndo = value; },
  });
  controller.apply({ automatic: true });
  assert.equal(Object.values(state.decisions).every((row) => row.action === "accept"), true);
  assert.equal(canUndo, true);
  assert.equal(controller.undo(), true);
  assert.deepEqual(state.decisions, {});
  assert.equal(canUndo, false);
  assert.equal(rendered, 2);
});

test("authored changes invalidate undo so automation cannot erase later work", () => {
  let state = acceptBatchEligibleSeamAssist(normalizedState());
  let canUndo = true;
  const controller = createSeamAssistController({
    getState: () => state,
    setState: (next) => { state = next; }, onRender: () => {}, onStatus: () => {},
    onUndoAvailability: (value) => { canUndo = value; },
  });
  controller.apply();
  controller.authoredChange();
  assert.equal(canUndo, false);
  assert.equal(controller.undo(), false);
});
