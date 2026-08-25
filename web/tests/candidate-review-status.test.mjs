import assert from "node:assert/strict";
import test from "node:test";

import { updateCandidateDecisionStatus } from "../modules/candidate-review-status.js";

test("decision live region is not rewritten when status is unchanged", () => {
  let kindWrites = 0;
  let textWrites = 0;
  let kind = "neutral";
  let text = "unchanged";
  const element = {
    dataset: {
      get kind() { return kind; },
      set kind(value) { kind = value; kindWrites += 1; },
    },
    get textContent() { return text; },
    set textContent(value) { text = value; textWrites += 1; },
  };

  updateCandidateDecisionStatus(element, "neutral", "unchanged");
  assert.deepEqual({ kindWrites, textWrites }, { kindWrites: 0, textWrites: 0 });
  updateCandidateDecisionStatus(element, "success", "accepted");
  assert.deepEqual({ kindWrites, textWrites }, { kindWrites: 1, textWrites: 1 });
});
