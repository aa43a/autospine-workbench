import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeSeamReviewAddress, seamAnchorReviewPaths,
} from "../modules/seam-anchor-review-address.js";
import {
  REVIEW_INTENT, SeamAnchorReviewApiError, createSeamAnchorReviewApi,
} from "../modules/seam-anchor-review-api.js";
import {
  normalizeSeamCandidateEnvelope, requireSeamLocator,
} from "../modules/seam-anchor-review-candidate.js";
import {
  currentSeamHeadBaseline, normalizeSeamReviewHistory,
} from "../modules/seam-anchor-review-history.js";
import {
  buildSeamReviewSubmission, createBusyGroup, deriveSeamReviewSummary,
  createSeamReviewState,
  expectedSeamSubmissionResult, hasLoadedSeamReviewAddress,
  markSeamSubmissionConflict,
  setAdjustedAnchorsText, setSeamAction, setSeamNotes, setSeamOption,
} from "../modules/seam-anchor-review-state.js";
import {
  ADDRESS, RELATIONSHIPS, SHA, assistFor, candidateEnvelope,
  decideAll, jsonResponse, normalizedState,
} from "./seam-anchor-review-fixtures.js";

function normalizeCandidate(payload) {
  const paths = seamAnchorReviewPaths(ADDRESS);
  return normalizeSeamCandidateEnvelope(
    payload, ADDRESS, (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
}

test("uses exact REST paths and never discovers an address", async () => {
  const calls = [];
  const api = createSeamAnchorReviewApi(async (...args) => {
    calls.push(args);
    return jsonResponse(200, candidateEnvelope());
  });
  assert.equal(calls.length, 0);
  await api.loadCandidate(ADDRESS);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], seamAnchorReviewPaths(ADDRESS).candidate());
  assert.match(calls[0][0], new RegExp(`/${SHA.manifest}/${SHA.rig}/${SHA.bundle}/candidate$`));
});

test("rejects uppercase, partial, and ambiguous addresses", () => {
  assert.throws(() => normalizeSeamReviewAddress({
    ...ADDRESS, p3RigSha256: "B".repeat(64),
  }), /小写十六进制/);
  assert.throws(() => normalizeSeamReviewAddress({
    ...ADDRESS, layerManifestSha256: "a".repeat(63),
  }), /64 位/);
  assert.throws(() => normalizeSeamReviewAddress({
    ...ADDRESS, projectId: "../escape",
  }), /安全标识符/);
});

test("same loaded exact address is detected without clearing its draft", () => {
  const state = normalizedState();
  state.addressKey = [
    ADDRESS.projectId, ADDRESS.layerManifestSha256,
    ADDRESS.p3RigSha256, ADDRESS.p3BundleSha256,
  ].join(":");
  state.reviewerId = "artist-01";
  assert.equal(hasLoadedSeamReviewAddress(state, ADDRESS), true);
  assert.equal(state.reviewerId, "artist-01");
  assert.equal(hasLoadedSeamReviewAddress(state, {
    ...ADDRESS, p3BundleSha256: "9".repeat(64),
  }), false);
});

test("candidate keeps fixed order and exact option-bound image evidence", () => {
  const payload = candidateEnvelope();
  const paths = seamAnchorReviewPaths(ADDRESS);
  const result = normalizeSeamCandidateEnvelope(
    payload, ADDRESS,
    (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
  assert.deepEqual(
    result.candidate.relationships.map((row) => row.relationship_id), RELATIONSHIPS,
  );
  assert.equal(result.attachmentImages.length, 12);
  const tampered = candidateEnvelope();
  tampered.attachment_images[0].path = "internal/source.png";
  assert.throws(() => normalizeSeamCandidateEnvelope(
    tampered, ADDRESS, () => tampered.attachment_images[0].url,
  ), /evidence/);
  const reordered = candidateEnvelope();
  reordered.attachment_images.reverse();
  assert.throws(() => normalizeSeamCandidateEnvelope(
    reordered, ADDRESS, () => reordered.attachment_images[0].url,
  ), /option/);
});

test("unavailable option keeps both images with an empty anchor preview", () => {
  const payload = candidateEnvelope();
  const relationship = payload.candidate.relationships[0];
  const option = relationship.options[0];
  option.status = "unavailable";
  option.reason_codes = ["GAP_LOCATOR_UNSUPPORTED_IN_V1"];
  option.anchors = [];
  relationship.status = "unobservable";
  relationship.reason_codes = ["GAP_LOCATOR_UNSUPPORTED_IN_V1"];
  payload.attachment_images
    .filter((row) => row.option_id === option.option_id)
    .forEach((row) => { row.anchor_points = []; });
  payload.review_assist = assistFor(payload.candidate);
  const paths = seamAnchorReviewPaths(ADDRESS);
  const normalized = normalizeSeamCandidateEnvelope(
    payload, ADDRESS, (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
  const images = normalized.attachmentImages.filter(
    (row) => row.option_id === option.option_id,
  );
  assert.deepEqual(images.map((row) => row.attachment_role), ["parent", "child"]);
  assert.equal(images.every((row) => row.anchor_points.length === 0), true);
});

test("option status and anchor cardinality remain fail closed", () => {
  for (const [status, clearAnchors] of [
    ["candidate", true], ["unavailable", false],
  ]) {
    const payload = candidateEnvelope();
    const relationship = payload.candidate.relationships[0];
    const option = relationship.options[0];
    option.status = status;
    if (clearAnchors) option.anchors = [];
    if (status === "unavailable") relationship.status = "unobservable";
    payload.review_assist = assistFor(payload.candidate);
    assert.throws(() => normalizeSeamCandidateEnvelope(
      payload, ADDRESS, () => payload.attachment_images[0].url,
    ), /anchor 数量/);
  }
});

test("submission contains only exhaustive human CAS fields and evidence identity", () => {
  let state = decideAll(normalizedState());
  state = {
    ...state, baseline: { revision: 0, decisionSha256: null },
    reviewerId: "artist-01", reviewNotes: "all six reviewed",
  };
  const payload = buildSeamReviewSubmission(state);
  assert.deepEqual(Object.keys(payload).sort(), [
    "base_revision", "candidate_sha256", "decisions",
    "previous_decision_sha256", "review",
  ]);
  assert.equal(payload.decisions.length, 6);
  assert.equal(payload.decisions[0].relationship_evidence_sha256, SHA.relationship);
  assert.equal(payload.decisions[0].option_evidence_sha256, SHA.option);
  assert.equal(JSON.stringify(payload).includes("attachment_images"), false);
  assert.equal(JSON.stringify(payload).includes("contact_evidence"), false);
  assert.equal(deriveSeamReviewSummary(state.candidate, state.decisions).counts.pending, 0);
  assert.deepEqual(expectedSeamSubmissionResult(state).summary, {
    relationship_count: 6, accept_count: 6, adjust_count: 0,
    reject_count: 0, unobservable_count: 0, anchor_pair_count: 12,
  });
});

test("adjust edits complete anchors without changing option evidence", () => {
  let state = normalizedState();
  const first = state.candidate.relationships[0];
  state = setSeamOption(state, first.relationship_id, first.options[0].option_id);
  state = setSeamAction(state, first.relationship_id, "adjust");
  const anchors = JSON.parse(state.decisions[first.relationship_id].anchorText);
  anchors[0].parent.local_xy_q4096[0] += 1024;
  state = setAdjustedAnchorsText(state, first.relationship_id, JSON.stringify(anchors));
  state = setSeamNotes(state, first.relationship_id, "manual locator correction");
  for (const relationship of state.candidate.relationships.slice(1)) {
    state = setSeamOption(state, relationship.relationship_id, relationship.options[0].option_id);
    state = setSeamAction(state, relationship.relationship_id, "accept");
  }
  state = {
    ...state, baseline: { revision: 0, decisionSha256: null }, reviewerId: "artist-01",
  };
  const row = buildSeamReviewSubmission(state).decisions[0];
  assert.equal(row.final_anchors[0].parent.local_xy_q4096[0], 5120);
  assert.equal(row.option_evidence_sha256, SHA.option);
  assert.equal(first.options[0].anchors[0].parent.local_xy_q4096[0], 4096);

  state = setAdjustedAnchorsText(state, first.relationship_id, "not JSON");
  assert.match(state.decisions[first.relationship_id].anchorError, /有效 JSON/);
  assert.throws(() => buildSeamReviewSubmission(state), /尚未完成/);
});

test("adjust rejects out-of-bounds, duplicate, and unordered locators", () => {
  let state = normalizedState();
  const first = state.candidate.relationships[0];
  state = setSeamOption(state, first.relationship_id, first.options[0].option_id);
  state = setSeamAction(state, first.relationship_id, "adjust");
  const original = JSON.parse(state.decisions[first.relationship_id].anchorText);
  const cases = [
    (rows) => { rows[0].parent.local_xy_q4096[0] = -1; },
    (rows) => { rows[1].parent = structuredClone(rows[0].parent); },
    (rows) => { rows.reverse(); rows.forEach((row, i) => {
      row.pair_id = `anchor.${String(i).padStart(3, "0")}`;
    }); },
    (rows) => { rows[0].child.local_xy_q4096[0] = 65 * 4096; },
  ];
  for (const mutate of cases) {
    const rows = structuredClone(original);
    mutate(rows);
    const next = setAdjustedAnchorsText(
      state, first.relationship_id, JSON.stringify(rows),
    );
    assert.ok(next.decisions[first.relationship_id].anchorError);
  }
});

test("mesh locator validation rejects noncanonical topology and weights", () => {
  const locator = {
    attachment_id: "mesh.arm", attachment_type: "mesh",
    locator_type: "mesh-barycentric-q65535", triangle_index: 0,
    vertex_indices: [0, 1, 2], weights_q65535: [21845, 21845, 21845],
  };
  assert.doesNotThrow(() => requireSeamLocator(locator, "mesh.arm", "mesh"));
  assert.throws(() => requireSeamLocator({
    ...locator, weights_q65535: [1, 1, 1],
  }, "mesh.arm", "mesh"), /mesh locator/);
  assert.throws(() => requireSeamLocator({
    ...locator, vertex_indices: [0, 0, 2],
  }, "mesh.arm", "mesh"), /mesh locator/);
});

test("review-required nonaccept keeps an option and requires notes", () => {
  let state = normalizedState();
  const first = state.candidate.relationships[0];
  assert.throws(() => setSeamAction(state, first.relationship_id, "reject"), /先选择/);
  state = setSeamOption(state, first.relationship_id, first.options[0].option_id);
  state = setSeamAction(state, first.relationship_id, "unobservable");
  assert.equal(state.decisions[first.relationship_id].optionId, first.options[0].option_id);
  assert.equal(
    deriveSeamReviewSummary(state.candidate, state.decisions).counts.pending, 6,
  );
});

test("candidate-unobservable relationship accepts only an explicit null-option decision", () => {
  const payload = candidateEnvelope();
  const relationship = payload.candidate.relationships.at(-1);
  const removedOptionId = relationship.options[0].option_id;
  relationship.status = "unobservable";
  relationship.reason_codes = ["NO_SUPPORTED_CANDIDATE_PAIR"];
  relationship.options = [];
  payload.attachment_images = payload.attachment_images.filter(
    (row) => row.option_id !== removedOptionId,
  );
  payload.review_assist = assistFor(payload.candidate);
  const paths = seamAnchorReviewPaths(ADDRESS);
  const normalized = normalizeSeamCandidateEnvelope(
    payload, ADDRESS, (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
  let state = {
    ...normalizedState(), candidate: normalized.candidate,
    attachmentImages: normalized.attachmentImages,
  };
  for (const row of state.candidate.relationships.slice(0, -1)) {
    state = setSeamOption(state, row.relationship_id, row.options[0].option_id);
    state = setSeamAction(state, row.relationship_id, "accept");
  }
  assert.throws(
    () => setSeamAction(state, relationship.relationship_id, "accept"), /只能标记/,
  );
  state = setSeamAction(state, relationship.relationship_id, "unobservable");
  state = setSeamNotes(state, relationship.relationship_id, "source seam not visible");
  state = {
    ...state, baseline: { revision: 0, decisionSha256: null }, reviewerId: "artist-01",
  };
  const submitted = buildSeamReviewSubmission(state).decisions.at(-1);
  assert.equal(submitted.option_id, null);
  assert.equal(submitted.option_evidence_sha256, null);
});

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
  const group = createBusyGroup(["history", "mutation"], (value) => snapshots.push(value));
  const old = group.begin("history");
  const current = group.begin("history");
  group.finish("history", old);
  assert.equal(snapshots.at(-1).history, true);
  group.finish("history", current);
  assert.equal(snapshots.at(-1).history, false);
});
