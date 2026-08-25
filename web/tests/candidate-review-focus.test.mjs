import assert from "node:assert/strict";
import test from "node:test";

import {
  captureCandidateFocus,
  scheduleCandidateFocus,
} from "../modules/candidate-review-focus.js";

function focusFixture(kind, candidateId) {
  const selector = kind === "canvas" ? ".candidate-marker" : ".candidate-choice";
  const node = {
    dataset: { candidateId },
    matches: (value) => value === selector,
    focusCount: 0,
    focus() { this.focusCount += 1; },
  };
  const activeScope = {
    contains: (value) => value === node,
    querySelectorAll: (value) => value === selector ? [node] : [],
  };
  const inactiveScope = { contains: () => false, querySelectorAll: () => [] };
  return {
    node,
    elements: kind === "canvas"
      ? { candidateGroup: activeScope, candidateList: inactiveScope }
      : { candidateGroup: inactiveScope, candidateList: activeScope },
  };
}

test("candidate marker focus survives a destructive overlay render", () => {
  const fixture = focusFixture("canvas", "candidate-2");
  const snapshot = captureCandidateFocus(fixture.elements, fixture.node);
  scheduleCandidateFocus(fixture.elements, snapshot, (callback) => callback());
  assert.deepEqual(snapshot, { kind: "canvas", candidateId: "candidate-2" });
  assert.equal(fixture.node.focusCount, 1);
});

test("candidate list focus restores only the exact candidate identity", () => {
  const fixture = focusFixture("list", "candidate-1");
  scheduleCandidateFocus(
    fixture.elements,
    { kind: "list", candidateId: "other" },
    (callback) => callback(),
  );
  assert.equal(fixture.node.focusCount, 0);
});
