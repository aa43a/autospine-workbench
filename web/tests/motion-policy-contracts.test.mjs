import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  approveDepthPolicy, validateDepthPolicyInput, validatePolicyCandidateBinding,
} from "../modules/motion-policy-contracts.js";
import { validateInventory } from "../modules/motion-policy-candidate-preflight.js";
import {
  deriveCandidateId, deriveCandidateInventorySha,
} from "../modules/motion-policy-hash.js";
import { gateIssue } from "../modules/motion-policy-policy-step.js";
import {
  fixtureUrl, POLICY_SHA,
} from "./motion-policy-review-fixtures.mjs";

test("candidate IDs match Python domain-length-prefix SHA-256 goldens", async () => {
  // Goldens were emitted by autospine_workbench.motion_policy_candidate_inventory._candidate_id.
  assert.equal(await deriveCandidateId("foot_lock", {
    report_sha256: "0d747347d7c4558239e2d9ea25eded676497d441e4f29c2433a57941cc296ccc",
    source_frame_index: 0,
    tick: 0,
  }, webcrypto), "foot-5c574212e5cb1b18db417e57a8bc381285c5cfdca75ecc83fc51982c6efdab6d");
  assert.equal(await deriveCandidateId("depth_order", {
    report_sha256: "3".repeat(64),
    pair_id: "hand-left-vs-face",
    event_index: 2,
    source_frame_index: 77,
    tick: 2566667,
    from_front_slot: "layer-011-face",
    to_front_slot: "layer-007-handwear-l",
  }, webcrypto), "depth-b07a8ede019178037a9c9bc162d5f88c8a82985d8b387488d5d07a4a0df13b70");
});

test("candidate inventory digest is order-independent and binds exact IDs", async () => {
  const ids = [`depth-${"2".repeat(64)}`, `foot-${"1".repeat(64)}`];
  const first = await deriveCandidateInventorySha(ids, webcrypto);
  const second = await deriveCandidateInventorySha([...ids].reverse(), webcrypto);
  assert.equal(first, "bc5886cb0e49487b2fae31f4305b391630299d2602d77463bee0606f11049982");
  assert.equal(first, second);
  assert.notEqual(
    first,
    await deriveCandidateInventorySha([ids[0], `foot-${"3".repeat(64)}`], webcrypto),
  );
  const derived = {
    candidates: ids.map((candidateId, index) => ({
      candidateId, kind: index === 0 ? "depth_order" : "foot_lock",
    })),
    unconstrainedTicks: [],
  };
  await assert.doesNotReject(() => validateInventory({
    total_count: 2, foot_count: 1, depth_count: 1, unconstrained_count: 0,
    candidate_ids_sha256: first,
  }, derived, webcrypto));
  await assert.rejects(() => validateInventory({
    total_count: 2, foot_count: 1, depth_count: 1, unconstrained_count: 0,
    candidate_ids_sha256: "0".repeat(64),
  }, derived, webcrypto), /候选 ID 清单摘要/);
});

test("real wave-left proposal requires human projection and loses proposal-only fields", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  assert.deepEqual(validateDepthPolicyInput(proposal), {
    document: proposal, proposal: true, approved: false,
  });
  const approved = approveDepthPolicy(proposal);
  assert.deepEqual(Object.keys(approved), [
    "format", "format_version", "policy_id", "project_id", "clip_id",
    "source", "review", "hysteresis", "pairs",
  ]);
  assert.equal(approved.format, "autospine-depth-pair-policy");
  assert.deepEqual(approved.review, { status: "approved", method: "human" });
  assert.equal("proposal" in approved, false);
  assert.equal(approved.pairs[0].setup_front_slot, "layer-011-face");
  assert.doesNotThrow(() => validateDepthPolicyInput(approved));

  const missing = structuredClone(proposal);
  delete missing.source.p8.p7_run_sha256;
  assert.throws(() => validateDepthPolicyInput(missing), /fields|字段/);
  const extra = structuredClone(proposal);
  extra.source.p5.latest = "f".repeat(64);
  assert.throws(() => validateDepthPolicyInput(extra), /fields|字段/);
});

test("approved policy SHA, source, hysteresis and pair inventory bind exactly", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const policySha = POLICY_SHA;
  const depth = {
    project_id: approved.project_id,
    clip_id: approved.clip_id,
    source: { ...structuredClone(approved.source), depth_pair_policy_sha256: policySha },
    hysteresis: structuredClone(approved.hysteresis),
    pairs: approved.pairs.map((pair) => ({ ...structuredClone(pair), samples: [], events: [] })),
  };
  assert.equal(gateIssue(approved, policySha, policySha), "");
  assert.doesNotThrow(() => validatePolicyCandidateBinding(approved, depth, policySha));
  assert.match(gateIssue(approved, policySha, "0".repeat(64)), /Python/);
  assert.throws(() => validatePolicyCandidateBinding(approved, depth, "0".repeat(64)), /policy SHA/);

  const staleHysteresis = structuredClone(depth);
  staleHysteresis.hysteresis.minimum_hold_frames += 1;
  assert.throws(() => validatePolicyCandidateBinding(approved, staleHysteresis, policySha), /hysteresis/);
  const stalePair = structuredClone(depth);
  stalePair.pairs[0].slots[0].depth_role = "humanoid.head";
  assert.throws(() => validatePolicyCandidateBinding(approved, stalePair, policySha), /pair\[0\]/);
});
