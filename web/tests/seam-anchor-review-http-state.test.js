import assert from "node:assert/strict";
import test from "node:test";

import {
  REVIEW_INTENT, SeamAnchorReviewApiError, createSeamAnchorReviewApi,
} from "../modules/seam-anchor-review-api.js";
import {
  currentSeamHeadBaseline, normalizeSeamReviewHistory,
} from "../modules/seam-anchor-review-history.js";
import {
  createBusyGroup, markSeamSubmissionConflict,
} from "../modules/seam-anchor-review-state.js";
import {
  ADDRESS, SHA, jsonResponse, normalizedState,
} from "./seam-anchor-review-fixtures.js";

test("POST uses explicit intent and 409 never retries", async () => {
  const calls = [];
  const api = createSeamAnchorReviewApi(async (...args) => {
    calls.push(args);
    return jsonResponse(409, { error: "stale_revision", message: "stale" });
  });
  await assert.rejects(
    () => api.submit(ADDRESS, SHA.candidate, { base_revision: 0 }),
    (error) => error instanceof SeamAnchorReviewApiError && error.status === 409,
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers["X-Autospine-Intent"], REVIEW_INTENT);
  const draft = {
    ...normalizedState(), history: { rows: [] },
    baseline: { revision: 0, decisionSha256: null }, reviewerId: "artist-01",
  };
  const stale = markSeamSubmissionConflict(draft);
  assert.equal(stale.candidate, draft.candidate);
  assert.equal(stale.reviewerId, "artist-01");
  assert.equal(stale.baseline, null);
  assert.equal(stale.stale, true);
});

test("history is continuous and baseline selection stays explicit", () => {
  const history = normalizeSeamReviewHistory({
    candidate_sha256: SHA.candidate, current_revision: 1,
    head_decision_sha256: SHA.decision,
    items: [{
      revision: 1, decision_sha256: SHA.decision,
      status: "reviewed_anchor_set_ready_for_compile",
    }],
  }, SHA.candidate);
  assert.deepEqual(currentSeamHeadBaseline(history), {
    revision: 1, decisionSha256: SHA.decision,
  });
  assert.throws(() => normalizeSeamReviewHistory({
    candidate_sha256: SHA.candidate, current_revision: 2,
    head_decision_sha256: SHA.decision, items: [],
  }, SHA.candidate), /head/);
});

test("busy group does not let stale work unlock a newer request", () => {
  const snapshots = [];
  const group = createBusyGroup(
    ["history", "mutation"], (value) => snapshots.push(value),
  );
  const old = group.begin("history");
  const current = group.begin("history");
  group.finish("history", old);
  assert.equal(snapshots.at(-1).history, true);
  group.finish("history", current);
  assert.equal(snapshots.at(-1).history, false);
});
