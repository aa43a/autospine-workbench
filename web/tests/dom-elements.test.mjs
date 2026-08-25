import assert from "node:assert/strict";
import test from "node:test";

import {
  collectRequiredElements,
  REQUIRED_ELEMENT_IDS,
} from "../modules/dom-elements.js";


test("DOM collection returns every required element exactly once", () => {
  const nodes = new Map(REQUIRED_ELEMENT_IDS.map((id) => [id, { id }]));
  const elements = collectRequiredElements({
    getElementById: (id) => nodes.get(id) || null,
  });

  assert.deepEqual(Object.keys(elements), REQUIRED_ELEMENT_IDS);
  assert.equal(elements.candidateGroup.id, "candidateGroup");
  assert.equal(elements.candidateRetryBtn.id, "candidateRetryBtn");
});

test("DOM collection fails at startup when markup and code drift", () => {
  assert.throws(
    () => collectRequiredElements({ getElementById: () => null }),
    /Missing required DOM element: projectSelect/,
  );
});
