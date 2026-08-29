import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMotionPolicyEvidenceModel,
} from "../modules/motion-policy-evidence-model.js";

function footSample(frame, {
  correction = [frame, -frame / 10], state = "candidate",
  support = "dual_support", contacts = ["contact-000", "contact-001"],
  residual = Math.abs(frame) / 20,
} = {}) {
  const constrained = correction !== null;
  const magnitude = constrained ? Math.hypot(...correction) : null;
  return {
    source_frame_index: frame,
    tick: frame * 10,
    support_state: support,
    state,
    active_contact_ids: [...contacts],
    observations: constrained ? [{
      contact_id: contacts[0] || "contact-000",
      limb: "leg.left",
      current_endpoint_px: [100 + frame, 200],
      desired_correction_px: [...correction],
      residual_after_candidate_px: [residual, 0],
      residual_magnitude_px: residual,
      residual_reference_ratio: residual / 100,
    }] : [],
    correction_candidate_px: correction,
    correction_magnitude_px: magnitude,
    correction_reference_ratio: magnitude == null ? null : magnitude / 100,
    maximum_residual_px: constrained ? residual : null,
  };
}

function footCandidate(sample) {
  return {
    candidateId: `foot-${String(sample.source_frame_index).padStart(3, "0")}`,
    kind: "foot_lock",
    tick: sample.tick,
    sourceFrameIndex: sample.source_frame_index,
    footState: sample.state,
    sample,
  };
}

function depthPair(pairId, eventFrames, frameCount = 12) {
  const samples = Array.from({ length: frameCount }, (_, frame) => ({
    source_frame_index: frame,
    tick: frame * 10,
    score_delta_first_minus_second: Math.sin(frame / 2),
  }));
  const events = eventFrames.map((frame) => ({
    source_frame_index: frame,
    tick: frame * 10,
    from_front_slot: `${pairId}-a`,
    to_front_slot: `${pairId}-b`,
    evidence_window: {
      start_source_frame_index: Math.max(0, frame - 1),
      end_source_frame_index: Math.min(frameCount - 1, frame + 1),
      start_tick: Math.max(0, frame - 1) * 10,
      end_tick: Math.min(frameCount - 1, frame + 1) * 10,
      sample_count: frame === 0 || frame === frameCount - 1 ? 2 : 3,
    },
  }));
  return { pair_id: pairId, samples, events };
}

function depthCandidates(pair) {
  return pair.events.map((event, eventIndex) => ({
    candidateId: `depth-${pair.pair_id}-${eventIndex}`,
    kind: "depth_order",
    tick: event.tick,
    sourceFrameIndex: event.source_frame_index,
    pairId: pair.pair_id,
    eventIndex,
    event,
  }));
}

function inventory(samples, pairs = [depthPair("pair-a", [], Math.max(2, samples.length))]) {
  return {
    snapshotKey: "project|clip|sealed",
    projectId: "project",
    clipId: "clip",
    evidence: {
      foot: {
        policy: {
          correction_limit: { maximum: 0.25 },
          residual_limit: { maximum: 8 },
        },
        reference: { value_px: 400 },
        samples,
      },
      depth: {
        hysteresis: { enter_threshold: 0.05, exit_threshold: 0.02, minimum_hold_frames: 2 },
        pairs,
      },
    },
    candidates: [
      ...samples.filter((row) => row.state !== "unconstrained").map(footCandidate),
      ...pairs.flatMap(depthCandidates),
    ],
  };
}

test("sorts frame evidence, preserves observations, and never jumps across a null gap", () => {
  const first = footSample(0, { correction: [-1, 0] });
  const gap = footSample(1, {
    correction: null, state: "unconstrained", support: "none", contacts: [],
  });
  const last = footSample(2, { correction: [1, 0] });
  const source = inventory([last, gap, first]);
  const model = buildMotionPolicyEvidenceModel(source);

  assert.deepEqual(model.samples.map((row) => row.sourceFrameIndex), [0, 1, 2]);
  assert.equal(model.contactSegments.length, 3);
  assert.equal(model.samples[2].jumpPx, null);
  assert.equal(model.attentionWindows.flatMap((row) => row.reasons).includes("zero:correctionX"), false);
  assert.equal(model.samples[0].observations[0].current_endpoint_px[0], 100);
  first.observations[0].current_endpoint_px[0] = 999;
  assert.equal(model.samples[0].observations[0].current_endpoint_px[0], 100);
  assert.equal(model.candidateIds.length, 2);
  assert.equal("decisions" in model, false);
  for (const segment of model.reviewSegments) {
    assert.equal("action" in segment, false);
    assert.equal("decision" in segment, false);
  }
});

test("derives dynamic boundary, rejection, p95, extrema, zero, and jump attention", () => {
  const values = [-4, -3, -2, -1, -0.5, 0.5, 1, 2, 3, 4, 20, 5, 4, 3, 2, 1, 0.5, -1, -2, -3];
  const samples = values.map((x, frame) => footSample(frame, {
    correction: [x, frame < 8 ? -1 : 1],
    state: frame === 12 ? "rejected_limit" : "candidate",
    residual: frame === 14 ? 7 : frame / 20,
  }));
  const model = buildMotionPolicyEvidenceModel(inventory(samples));
  const reasons = new Set(model.attentionWindows.flatMap((row) => row.reasons));

  for (const reason of [
    "boundary", "rejected_limit", "p95:correctionX", "extreme:correctionX:max",
    "zero:correctionX", "zero:correctionY", "jump:p95",
  ]) assert.equal(reasons.has(reason), true, reason);
  const peak = model.attentionWindows.find((row) => row.startFrame <= 10 && row.endFrame >= 10);
  assert.ok(peak.startFrame <= 9 && peak.endFrame >= 11);
  assert.equal(model.metrics.correctionX.maximum, 20);
  assert.equal(model.metrics.maximumResidualPx.maximum, 7);
  assert.deepEqual(model.contractLimits, {
    correctionReferenceRatio: 0.25,
    maximumResidualPx: 8,
    referencePx: 400,
    depthEnterThreshold: 0.05,
    depthExitThreshold: 0.02,
    depthMinimumHoldFrames: 2,
  });
});

test("partitions every exact candidate once and keeps ordinary batches at 24 items", () => {
  const samples = Array.from({ length: 70 }, (_, frame) => footSample(frame, {
    correction: [Math.sin(frame / 8) * 6, Math.cos(frame / 10)],
    residual: Math.abs(Math.sin(frame / 9)),
  }));
  const left = depthPair("pair-left", [5], 70);
  const right = depthPair("pair-right", [8, 60], 70);
  const source = inventory(samples, [left, right]);
  source.candidates.reverse();
  const model = buildMotionPolicyEvidenceModel(source);
  const flattened = model.reviewSegments.flatMap((row) => row.candidateIds);

  assert.equal(model.snapshotKey, source.snapshotKey);
  assert.equal(model.projectId, "project");
  assert.equal(model.clipId, "clip");
  assert.equal(flattened.length, source.candidates.length);
  assert.equal(new Set(flattened).size, source.candidates.length);
  assert.deepEqual(new Set(flattened), new Set(source.candidates.map((row) => row.candidateId)));
  assert.ok(model.reviewSegments.filter((row) => row.kind === "foot_lock" && !row.attention)
    .every((row) => row.candidateIds.length <= 24));
  const depth = model.reviewSegments.filter((row) => row.kind === "depth_order");
  assert.deepEqual(depth.map((row) => row.pairId).sort(), ["pair-left", "pair-right"]);
  assert.deepEqual(depth.find((row) => row.pairId === "pair-right").candidateIds,
    ["depth-pair-right-0", "depth-pair-right-1"]);
  assert.equal(model.candidatesById.get("depth-pair-left-0").pairId, "pair-left");
  for (const segment of model.reviewSegments) {
    for (const field of [
      "segmentId", "kind", "startFrame", "endFrame", "startTick", "endTick",
      "candidateIds", "attention", "reasons", "metrics",
    ]) assert.ok(field in segment, `${segment.segmentId}.${field}`);
  }
});

test("models the real 119 Foot / 0 Depth-event shape without creating decisions", () => {
  const samples = Array.from({ length: 120 }, (_, frame) => frame === 119
    ? footSample(frame, { correction: null, state: "unconstrained", support: "none", contacts: [] })
    : footSample(frame, {
      correction: [Math.sin(frame / 15) * 15, -Math.sin(frame / 10) * 2],
      residual: Math.abs(Math.sin(frame / 13) * 2),
    }));
  const pair = depthPair("hand-left-vs-face", [], 120);
  const source = inventory(samples, [pair]);
  const model = buildMotionPolicyEvidenceModel(source);

  assert.equal(model.samples.length, 120);
  assert.equal(model.candidateIds.length, 119);
  assert.deepEqual(model.contactSegments.map((row) => row.sampleCount), [119, 1]);
  assert.equal(model.contactSegments[0].supportState, "dual_support");
  assert.equal(model.contactSegments[1].state, "unconstrained");
  assert.equal(model.samples.at(-1).candidateId, null);
  assert.ok(model.attentionWindows.some((row) => row.startFrame <= 118 && row.endFrame === 119));
  const depth = model.reviewSegments.find((row) => row.kind === "depth_order");
  assert.deepEqual(depth.candidateIds, []);
  assert.deepEqual(depth.reasons, ["depth_pair_no_events"]);
  assert.equal(depth.attention, false);
  assert.equal(new Set(model.candidateIds).size, 119);
  assert.ok(model.reviewSegments.filter((row) => row.kind === "foot_lock" && !row.attention)
    .every((row) => row.candidateIds.length <= 24));
  assert.equal(model.candidateIds.some((id) => id.includes("decision")), false);
});

test("fails closed when exact candidates are missing or duplicated", () => {
  const source = inventory([footSample(0), footSample(1)]);
  source.candidates.pop();
  assert.throws(() => buildMotionPolicyEvidenceModel(source), /exact candidate/);
  const duplicate = inventory([footSample(0), footSample(1)]);
  duplicate.candidates.push(duplicate.candidates[0]);
  assert.throws(() => buildMotionPolicyEvidenceModel(duplicate), /无效或重复/);
});
