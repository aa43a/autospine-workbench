import assert from "node:assert/strict";
import test from "node:test";

import { readCandidateFile } from "../modules/motion-policy-candidate-files.js";
import {
  createLoadGuard, sameIdentitySnapshot,
} from "../modules/motion-policy-load-guard.js";
import {
  fakeElement, fileFrom, waitFor,
} from "./motion-policy-review-fixtures.mjs";

test("late candidate file read cannot replace a newer selection", async () => {
  const guard = createLoadGuard();
  const fileInput = fakeElement();
  const shaInput = fakeElement();
  const statusElement = fakeElement();
  let releaseFirst;
  const first = {
    size: 64,
    text: () => new Promise((resolve) => { releaseFirst = resolve; }),
  };
  const secondText = '{"format":"autospine-foot-lock-candidates"}';
  const second = fileFrom(secondText);
  fileInput.files = [first];
  const pendingFirst = readCandidateFile({
    kind: "foot", fileInput, shaInput, guard, statusElement,
  });
  await waitFor(() => typeof releaseFirst === "function");
  fileInput.files = [second];
  const current = await readCandidateFile({
    kind: "foot", fileInput, shaInput, guard, statusElement,
  });
  releaseFirst('{"format":"autospine-foot-lock-candidates","stale":true}');
  assert.equal(await pendingFirst, null);
  assert.equal(current.rawText, secondText);
  assert.equal("stale" in current.document, false);
});

test("generation and identity guards reject stale async results", () => {
  const guard = createLoadGuard();
  const first = guard.begin();
  const second = guard.begin();
  assert.equal(guard.isCurrent(first), false);
  assert.equal(guard.isCurrent(second), true);
  guard.invalidate();
  assert.equal(guard.isCurrent(second), false);

  const identity = {
    policy: {}, foot: {}, depth: {}, policyJson: "p", footJson: "f", depthJson: "d",
    policySha: "1", footSha: "2", depthSha: "3",
  };
  assert.equal(sameIdentitySnapshot(identity, { ...identity }), true);
  assert.equal(sameIdentitySnapshot(identity, { ...identity, depthSha: "changed" }), false);
  assert.equal(sameIdentitySnapshot(identity, { ...identity, policy: {} }), false);
});
