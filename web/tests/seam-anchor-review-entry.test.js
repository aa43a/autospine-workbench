import assert from "node:assert/strict";
import test from "node:test";

import { seamAnchorReviewPaths } from "../modules/seam-anchor-review-address.js";
import {
  createSeamAnchorReviewApi, seamReviewEntryPath,
} from "../modules/seam-anchor-review-api.js";
import { normalizeSeamCandidateEnvelope } from "../modules/seam-anchor-review-candidate.js";
import {
  normalizeSeamReviewEntry, packageIdFromSearch, requireSeamEntryCandidate,
} from "../modules/seam-anchor-review-entry.js";
import { createSeamReviewEntryFlow } from "../modules/seam-anchor-review-entry-flow.js";
import { createSeamReviewState } from "../modules/seam-anchor-review-state.js";
import {
  ADDRESS, RELATIONSHIPS, SHA, blockedCandidateEnvelope, candidateEnvelope,
  jsonResponse, seamEntryPayload,
} from "./seam-anchor-review-fixtures.js";

function normalizeCandidate(payload) {
  const paths = seamAnchorReviewPaths(ADDRESS);
  return normalizeSeamCandidateEnvelope(
    payload, ADDRESS, (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("loads a path-free Seam entry only from an exact package ID", async () => {
  const calls = [];
  const api = createSeamAnchorReviewApi(async (...args) => {
    calls.push(args);
    return jsonResponse(200, seamEntryPayload());
  });
  assert.deepEqual(await api.loadEntry(SHA.package), seamEntryPayload());
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], seamReviewEntryPath(SHA.package));
  assert.equal(calls[0][1].method, undefined);
  assert.throws(() => api.loadEntry("A".repeat(64)), /小写十六进制/);
  assert.equal(calls.length, 1);
});

test("package query is exact, singular, and fail-closed", () => {
  assert.equal(packageIdFromSearch(""), null);
  assert.equal(packageIdFromSearch(`?package_id=${SHA.package}`), SHA.package);
  assert.throws(() => packageIdFromSearch("?package_id=bad"), /64 位/);
  assert.throws(
    () => packageIdFromSearch(`?package_id=${"A".repeat(64)}`),
    /小写十六进制/,
  );
  assert.throws(
    () => packageIdFromSearch(
      `?package_id=${SHA.package}&package_id=${"4".repeat(64)}`,
    ),
    /只能出现一次/,
  );
});

test("strict Seam entry contract distinguishes review-ready and blockers", () => {
  const ready = normalizeSeamReviewEntry(seamEntryPayload(), SHA.package);
  assert.equal(ready.status, "manual_review_required");
  assert.deepEqual(ready.address, ADDRESS);
  assert.deepEqual(ready.blockingRelationships, []);

  const blocked = normalizeSeamReviewEntry(seamEntryPayload(true), SHA.package);
  assert.equal(blocked.status, "blocked_unobservable");
  assert.deepEqual(
    blocked.blockingRelationships.map((row) => row.relationshipId),
    RELATIONSHIPS.slice(2),
  );
  assert.equal(blocked.summary.unobservableCount, 4);
});

test("Seam entry rejects path-bearing, mismatched, or ambiguous authority", () => {
  const cases = [
    (payload) => { payload.path = "workspace/private.json"; },
    (payload) => { payload.package_id = "4".repeat(64); },
    (payload) => { payload.address.project_id = "another.project"; },
    (payload) => { payload.summary.relationship_count = 5; },
    (payload) => { payload.status = "manual_review_required"; },
    (payload) => { payload.blocking_relationships[0].reason_codes[0] = "C:\\private"; },
    (payload) => { payload.blocking_relationships.reverse(); },
  ];
  for (const mutate of cases) {
    const payload = seamEntryPayload(true);
    mutate(payload);
    assert.throws(() => normalizeSeamReviewEntry(payload, SHA.package));
  }
  const unexpectedBlocker = seamEntryPayload();
  unexpectedBlocker.blocking_relationships.push({
    relationship_id: RELATIONSHIPS[2], reason_codes: ["NO_SUPPORTED_CANDIDATE_PAIR"],
  });
  assert.throws(() => normalizeSeamReviewEntry(unexpectedBlocker, SHA.package));
});

test("entry authority must match the loaded candidate without making decisions", () => {
  const ready = normalizeSeamReviewEntry(seamEntryPayload(), SHA.package);
  assert.equal(requireSeamEntryCandidate(ready, normalizeCandidate(candidateEnvelope())), ready);

  const blocked = normalizeSeamReviewEntry(seamEntryPayload(true), SHA.package);
  const envelope = normalizeCandidate(blockedCandidateEnvelope());
  assert.equal(requireSeamEntryCandidate(blocked, envelope), blocked);
  const state = { ...createSeamReviewState(), candidate: envelope.candidate };
  assert.deepEqual(state.decisions, {});

  const wrongCandidate = { ...envelope, candidateSha256: "4".repeat(64) };
  assert.throws(() => requireSeamEntryCandidate(blocked, wrongCandidate), /身份不一致/);
  const changedEvidence = blockedCandidateEnvelope();
  changedEvidence.candidate.relationships[2].reason_codes = [
    "NO_SUPPORTED_CANDIDATE_PAIR", "PARENT_ROLE_MISSING",
  ];
  assert.throws(
    () => requireSeamEntryCandidate(blocked, normalizeCandidate(changedEvidence)),
    /blocker/,
  );
});

test("rapid package switching ignores stale entries and bad IDs load nothing", async () => {
  const packageA = SHA.package;
  const packageB = "4".repeat(64);
  const requests = new Map([[packageA, deferred()], [packageB, deferred()]]);
  const events = [];
  const flow = createSeamReviewEntryFlow({
    api: { loadEntry: (packageId) => requests.get(packageId).promise },
    elements: {},
    busy: { begin: () => Symbol("busy"), finish: () => {} },
    onReset: () => events.push("reset"),
    onSubmitAddress: () => events.push("submit"),
    view: {
      clearAddress: () => events.push("clear"),
      fillAddress: (_, entry) => events.push(`fill:${entry.packageId}`),
      candidateLoading: (_, entry) => events.push(`candidate:${entry.packageId}`),
      error: (_, error) => events.push(`error:${error.message}`),
      idle: () => events.push("idle"),
      loading: (_, packageId) => events.push(`loading:${packageId}`),
      manual: () => events.push("manual"),
      ready: () => events.push("ready"),
    },
  });
  const first = flow.loadSearch(`?package_id=${packageA}`);
  const second = flow.loadSearch(`?package_id=${packageB}`);
  requests.get(packageB).resolve(seamEntryPayload(true, packageB));
  await second;
  requests.get(packageA).resolve(seamEntryPayload(false, packageA));
  await first;
  assert.equal(flow.currentEntry().packageId, packageB);
  assert.deepEqual(events.filter((row) => row.startsWith("fill:")), [`fill:${packageB}`]);
  assert.equal(events.filter((row) => row === "submit").length, 1);

  await flow.loadSearch("?package_id=BAD");
  assert.equal(flow.currentEntry(), null);
  assert.equal(events.at(-1).startsWith("error:"), true);
});
