import assert from "node:assert/strict";
import test from "node:test";

import {
  applySplitDecision,
  buildSplitDecision,
  clientSplitDecisions,
  escapeHtml,
  isSplitReviewLayer,
  isCurrentSplitArtifact,
  removeSplitDecision,
  shouldShowSplitReviewBody,
  splitArtifactsForLayer,
  splitDecisionStatus,
  splitPartImageUrl,
} from "../modules/split-review-state.js";

const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);
const SHA_C = "c".repeat(64);
const SHA_D = "d".repeat(64);
const SNAPSHOT = "1".repeat(64);

test("artifact index is layer-scoped, current-snapshot first, and stably sorted", () => {
  const payload = { items: [
    { layer_id: "other", artifact_sha256: "e".repeat(64), resolved_snapshot_sha256: SNAPSHOT },
    { layer_id: "arm", artifact_sha256: SHA_D, resolved_snapshot_sha256: "2".repeat(64), published_at: "2026-08-25T12:00:00Z" },
    { layer_id: "arm", artifact_sha256: SHA_B, resolved_snapshot_sha256: SNAPSHOT, published_at: "2026-08-24T12:00:00Z" },
    { layer_id: "arm", artifact_sha256: SHA_C, resolved_snapshot_sha256: SNAPSHOT, published_at: "2026-08-25T12:00:00Z" },
    { layer_id: "arm", artifact_sha256: SHA_A, resolved_snapshot_sha256: "3".repeat(64), published_at: "2026-08-20T12:00:00Z" },
    { layer_id: "arm", artifact_sha256: "not-a-digest", resolved_snapshot_sha256: SNAPSHOT },
  ] };

  const items = splitArtifactsForLayer(payload, "arm", SNAPSHOT, SHA_A);
  assert.deepEqual(items.map((item) => item.artifact_sha256), [SHA_C, SHA_B, SHA_A, SHA_D]);
  assert.equal(items.every((item) => !("_index" in item)), true);
  assert.deepEqual(splitArtifactsForLayer(payload, "missing", SNAPSHOT), []);
});

test("equal-date artifacts use digest ordering instead of engine sort accidents", () => {
  const items = splitArtifactsForLayer({ items: [
    { layer_id: "arm", artifact_sha256: SHA_A, published_at: "invalid" },
    { layer_id: "arm", artifact_sha256: SHA_C, published_at: "invalid" },
    { layer_id: "arm", artifact_sha256: SHA_B, published_at: "invalid" },
  ] }, "arm");
  assert.deepEqual(items.map((item) => item.artifact_sha256), [SHA_C, SHA_B, SHA_A]);
});

test("stored decisions are reduced to the three writable client fields", () => {
  const stripped = clientSplitDecisions({
    arm: {
      action: "reject",
      split_artifact_sha256: SHA_A,
      reason: "wrong ownership",
      binding_status: "stale",
      analysis: { provider: "binder" },
      review_target_sha256: SHA_B,
      layer_manifest_sha256: SHA_C,
    },
    invalid: null,
    constructor: { action: "accept", split_artifact_sha256: SHA_D },
  });
  assert.deepEqual(stripped, {
    arm: {
      action: "reject",
      split_artifact_sha256: SHA_A,
      reason: "wrong ownership",
    },
  });
});

test("accept, reject, and remove mutate only the selected layer decision", () => {
  const accepted = buildSplitDecision("accept", SHA_A, "ignored for accept");
  const rejected = buildSplitDecision("reject", SHA_B, "  crosses the torso  ");
  assert.deepEqual(accepted, { action: "accept", split_artifact_sha256: SHA_A });
  assert.deepEqual(rejected, {
    action: "reject",
    split_artifact_sha256: SHA_B,
    reason: "crosses the torso",
  });
  assert.throws(() => buildSplitDecision("reject", SHA_B, "  "), /必须填写理由/);
  assert.throws(() => buildSplitDecision("accept", "bad"), /artifact/);

  const state = { splitDecisions: { leg: accepted } };
  applySplitDecision(state, "arm", rejected);
  assert.deepEqual(state.splitDecisions, { leg: accepted, arm: rejected });
  assert.equal(removeSplitDecision(state, "arm"), true);
  assert.equal(removeSplitDecision(state, "arm"), false);
  assert.deepEqual(state.splitDecisions, { leg: accepted });
  assert.throws(() => applySplitDecision(state, "__proto__", accepted), /图层标识/);
});

test("decision status distinguishes current, stale, rejected, and artifact mismatch", () => {
  const accepted = { action: "accept", split_artifact_sha256: SHA_A };
  assert.deepEqual(splitDecisionStatus(null, null, SHA_A), {
    kind: "none", label: "尚未审查",
  });
  assert.deepEqual(splitDecisionStatus(accepted, { ...accepted, binding_status: "current" }, SHA_A), {
    kind: "accepted-current", label: "已接受 · 当前有效",
  });
  assert.deepEqual(splitDecisionStatus(accepted, { ...accepted, binding_status: "stale" }, SHA_B), {
    kind: "stale", label: "已失效 · 绑定 aaaaaaaa",
  });
  assert.deepEqual(splitDecisionStatus(
    { action: "reject", split_artifact_sha256: SHA_B, reason: "bad split" },
    { action: "reject", split_artifact_sha256: SHA_B, reason: "bad split", binding_status: "current" },
    SHA_B,
  ), { kind: "rejected", label: "已拒绝" });
  assert.deepEqual(splitDecisionStatus(
    { action: "reject", split_artifact_sha256: SHA_B, reason: "new reason" },
    { action: "reject", split_artifact_sha256: SHA_B, reason: "old reason", binding_status: "current" },
    SHA_B,
  ), { kind: "rejected", label: "待保存拒绝" });
});

test("split review gate requires authored left-right parts", () => {
  assert.equal(isSplitReviewLayer({
    disposition: "split_left_right",
    split_spec: { parts: { left: {}, right: {} } },
  }), true);
  assert.equal(isSplitReviewLayer({ disposition: "split", split_spec: { parts: {} } }), false);
  assert.equal(isSplitReviewLayer({
    disposition: "split_left_right", split_spec: { parts: { left: {} } },
  }), false);
  assert.equal(isSplitReviewLayer({ disposition: "split_left_right" }), false);
});

test("an existing decision keeps remove controls available without an artifact", () => {
  assert.equal(shouldShowSplitReviewBody(null, null), false);
  assert.equal(shouldShowSplitReviewBody(null, {
    action: "accept", split_artifact_sha256: SHA_A,
  }), true);
  assert.equal(shouldShowSplitReviewBody({ review_target: {} }, null), true);
  assert.equal(shouldShowSplitReviewBody(null, null, true), true);
});

test("only an artifact bound to the authoritative resolved SHA is actionable", () => {
  assert.equal(isCurrentSplitArtifact({ resolved_snapshot_sha256: SNAPSHOT }, SNAPSHOT), true);
  assert.equal(isCurrentSplitArtifact({ resolved_snapshot_sha256: SHA_A }, SNAPSHOT), false);
  assert.equal(isCurrentSplitArtifact({ resolved_snapshot_sha256: SNAPSHOT }, ""), false);
  assert.equal(isCurrentSplitArtifact(null, SNAPSHOT), false);
});

test("untrusted labels escape predictably and image URLs stay path-safe", () => {
  assert.equal(
    escapeHtml(`<img src=x onerror="alert('x')"> &`),
    "&lt;img src=x onerror=&quot;alert(&#39;x&#39;)&quot;&gt; &amp;",
  );
  assert.equal(
    splitPartImageUrl("/api/projects/", "sample/一 号", SHA_A, "left"),
    `/api/projects/sample%2F%E4%B8%80%20%E5%8F%B7/split-previews/${SHA_A}/parts/left/image`,
  );
  assert.throws(() => splitPartImageUrl("/api/projects", "sample", "../x", "left"), /artifact/);
  assert.throws(() => splitPartImageUrl("/api/projects", "sample", SHA_A, "center"), /侧别/);
});
