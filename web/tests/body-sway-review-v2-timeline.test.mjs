import assert from "node:assert/strict";
import test from "node:test";

import { buildReviewSubmission, createReviewState } from "../modules/body-sway-review-state.js";
import {
  buildReviewTimelineGroups, createDefaultApproveDraft, groupDraftState,
  markVisitedRange, timelineCoverage, timelineExceptions,
} from "../modules/body-sway-review-v2-timeline-model.js";

const SHA = (character) => character.repeat(64);

function runtimeCases(pairCount = 21) {
  const rows = [row("setup", null, 0, 0, "1")];
  for (let index = 0; index < pairCount; index += 1) {
    const tick = index * 1000;
    rows.push(
      row(`base-${index}`, "p10.base", tick, index / 10, "2"),
      row(`sway-${index}`, "p10.body-sway", tick, index / 10, "3"),
    );
  }
  return rows;
}

function row(caseId, animation, tick, timeSeconds, digest) {
  return {
    case_id: caseId, animation, tick, time_seconds: timeSeconds,
    evidence_sha256: SHA(digest),
    image: { png_sha256: SHA("4"), size_bytes: 10, width: 64, height: 64 },
  };
}

test("43 immutable cases become setup plus 21 strict A/B timeline positions", () => {
  const cases = runtimeCases();
  const groups = buildReviewTimelineGroups(cases);
  assert.equal(cases.length, 43);
  assert.equal(groups.length, 22);
  assert.deepEqual(groups[0].cases.map((item) => item.animation), [null]);
  assert.deepEqual(groups[1].cases.map((item) => item.animation), [
    "p10.base", "p10.body-sway",
  ]);
});

test("pairing fails closed for wrong order, missing pair, duplicate, or tick mismatch", () => {
  const wrongOrder = runtimeCases(1);
  [wrongOrder[1], wrongOrder[2]] = [wrongOrder[2], wrongOrder[1]];
  assert.throws(() => buildReviewTimelineGroups(wrongOrder), /严格配对/);
  assert.throws(() => buildReviewTimelineGroups(runtimeCases(1).slice(0, 2)), /成对排列/);
  const duplicate = runtimeCases(1);
  duplicate[2] = { ...duplicate[2], case_id: duplicate[1].case_id };
  assert.throws(() => buildReviewTimelineGroups(duplicate), /重复/);
  const mismatch = runtimeCases(1);
  mismatch[2] = { ...mismatch[2], tick: 99 };
  assert.throws(() => buildReviewTimelineGroups(mismatch), /严格配对/);
  const reordered = runtimeCases(2);
  reordered.splice(1, 4, ...reordered.slice(3, 5), ...reordered.slice(1, 3));
  assert.throws(() => buildReviewTimelineGroups(reordered), /严格递增/);
});

test("default approve is a complete local draft and full scrub records coverage", () => {
  const cases = runtimeCases();
  const groups = buildReviewTimelineGroups(cases);
  const draft = createDefaultApproveDraft(cases);
  assert.equal(Object.keys(draft).length, 43);
  assert.ok(Object.values(draft).every((choice) => choice.action === "approve"));
  assert.throws(() => createDefaultApproveDraft([cases[0], cases[0]]), /重复/);
  const visited = markVisitedRange(new Set([groups[0].id]), groups, 0, 21);
  assert.deepEqual(timelineCoverage(groups, visited), {
    visitedCount: 22, groupCount: 22, complete: true,
  });
});

test("only rejected or unobservable cases appear as exceptions", () => {
  const cases = runtimeCases(1);
  const groups = buildReviewTimelineGroups(cases);
  const decisions = createDefaultApproveDraft(cases);
  decisions["base-0"] = { action: "reject", notes: "轮廓破裂" };
  decisions["sway-0"] = { action: "unobservable", notes: "" };
  const exceptions = timelineExceptions(groups, decisions);
  assert.equal(exceptions.length, 2);
  assert.equal(exceptions[1].incomplete, true);
  assert.equal(groupDraftState(groups[1], decisions), "incomplete");
});

test("submission still contains all 43 cases in immutable candidate order", () => {
  const cases = runtimeCases();
  const state = {
    ...createReviewState(),
    candidate: { cases, release_gate: { reason_codes: [] } },
    candidateSha256: SHA("a"),
    decisions: createDefaultApproveDraft(cases),
    baseline: { revision: 0, decisionSha256: null },
    reviewerId: "operator-1",
  };
  const payload = buildReviewSubmission(state);
  assert.equal(payload.decisions.length, 43);
  assert.deepEqual(
    payload.decisions.map((item) => item.case_id),
    cases.map((item) => item.case_id),
  );
  assert.deepEqual(
    payload.decisions.map((item) => item.evidence_sha256),
    cases.map((item) => item.evidence_sha256),
  );
});
