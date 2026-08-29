import assert from "node:assert/strict";
import test from "node:test";

import {
  buildIdleReviewSubmission, controlsFromParameters, controlsFromSuggestion,
  initialBodySwayParameters, parametersFromControls, sampleBodySwayPose,
} from "../modules/idle-behavior-review-model.js";
import {
  BONES, entryDocument, previewDocument, suggestionDocument,
} from "./idle-behavior-review-fixtures.mjs";

test("four simple controls map deterministically to the exact four-bone contract", () => {
  const parameters = parametersFromControls({
    cycles: 3, lowerAmplitude: 2, headAmplitude: 1, phaseDelay: 0.08,
  });
  assert.equal(parameters.cycles, 3);
  assert.deepEqual(parameters.per_bone_amplitude_deg, [
    { bone_id: BONES[0], value: 1.5 },
    { bone_id: BONES[1], value: 2 },
    { bone_id: BONES[2], value: 0.65 },
    { bone_id: BONES[3], value: 1 },
  ]);
  assert.deepEqual(parameters.per_bone_phase_fraction.map((row) => row.value),
    [0, 0.08, 0.16, 0.24]);
});

test("backend suggestion initializes the simple controls without granting authority", () => {
  assert.deepEqual(controlsFromSuggestion(suggestionDocument()), {
    cycles: 2, lowerAmplitude: 0.7, headAmplitude: 0.2, phaseDelay: 0.04,
  });
});

test("unchanged simple controls preserve the exact four-bone server suggestion", () => {
  const source = {
    cycles: 9,
    per_bone_amplitude_deg: BONES.map((bone_id, index) => ({
      bone_id, value: [0.812345678901, 1.234567890123, 0.456789012345, 0.987654321987][index],
    })),
    per_bone_phase_fraction: BONES.map((bone_id, index) => ({
      bone_id, value: index * 0.25,
    })),
  };
  const controls = controlsFromParameters(source);
  const result = parametersFromControls(controls, source);
  assert.deepEqual(controls, {
    cycles: 9, lowerAmplitude: 1.234567890123,
    headAmplitude: 0.987654321987, phaseDelay: 0.25,
  });
  assert.deepEqual(result, source);
  assert.notEqual(result, source);
  assert.notEqual(result.per_bone_amplitude_deg, source.per_bone_amplitude_deg);
  result.per_bone_amplitude_deg[0].value = 4;
  assert.equal(source.per_bone_amplitude_deg[0].value, 0.812345678901);
});

test("edited controls cover the complete shared review profile", () => {
  const parameters = parametersFromControls({
    cycles: 64, lowerAmplitude: 10, headAmplitude: 10,
    phaseDelay: 0.333333333333,
  });
  assert.equal(parameters.cycles, 64);
  assert.ok(parameters.per_bone_amplitude_deg.every((row) => row.value <= 10));
  assert.ok(parameters.per_bone_phase_fraction.every((row) => row.value < 1));
  assert.throws(() => parametersFromControls({
    cycles: 65, lowerAmplitude: 1, headAmplitude: 1, phaseDelay: 0,
  }), /摆动次数超出/);
});

test("arbitrary valid source phases remain loadable even when the simple delay projection saturates", () => {
  const source = suggestionDocument().payload;
  source.cycles = 64;
  source.per_bone_phase_fraction = BONES.map((bone_id, index) => ({
    bone_id, value: [0, 0.999999999999, 0.125678901234, 0.876543210987][index],
  }));
  const controls = controlsFromParameters(source);
  assert.equal(controls.phaseDelay, 0.333333333333);
  assert.deepEqual(parametersFromControls(controls, source), source);
});

test("submission carries explicit confirmation and CAS baseline only after user action", () => {
  const entry = entryDocument();
  const request = buildIdleReviewSubmission(entry, "adjust", {
    cycles: 2, lowerAmplitude: 0.7, headAmplitude: 0.2, phaseDelay: 0.04,
  });
  assert.deepEqual(Object.keys(request).sort(), [
    "action", "base_revision", "candidate_sha256", "explicit_confirmation",
    "format", "format_version", "intent", "package_id", "parameters",
    "previous_decision_sha256", "reason_code",
  ]);
  assert.equal(request.explicit_confirmation, true);
  assert.equal(request.base_revision, 0);
  assert.equal(request.previous_decision_sha256, null);
  assert.equal(request.parameters.cycles, 2);

  const rejected = buildIdleReviewSubmission(entry, "reject", null);
  assert.equal(rejected.parameters, null);
  assert.equal(rejected.reason_code, "human-declined-body-sway-v1");

  const unobservable = buildIdleReviewSubmission(entry, "unobservable", null);
  assert.equal(unobservable.parameters, null);
  assert.equal(unobservable.reason_code, "human-marked-unobservable-v1");
});

test("current adjusted head becomes the refresh baseline instead of the draft", () => {
  const reviewed = {
    ...suggestionDocument().payload,
    cycles: 9,
    per_bone_amplitude_deg: BONES.map((bone_id, index) => ({
      bone_id, value: [1.123456789012, 1.012345678901, 0.612345678901, 0.412345678901][index],
    })),
    per_bone_phase_fraction: BONES.map((bone_id, index) => ({
      bone_id, value: index * 0.25,
    })),
  };
  const entry = entryDocument({
    history: {
      current_revision: 1, revision_count: 1,
      head_decision_sha256: "9".repeat(64),
      items: [{
        revision: 1, decision_sha256: "9".repeat(64), action: "adjust",
        probe_status: "pending_probe", parameters: reviewed,
      }],
    },
  });
  assert.deepEqual(initialBodySwayParameters(entry), reviewed);
  const request = buildIdleReviewSubmission(
    entry, "adjust", controlsFromParameters(reviewed), reviewed,
  );
  assert.deepEqual(request.parameters, reviewed);
  assert.notEqual(request.parameters, reviewed);
  assert.equal(request.base_revision, 1);
});

test("zero-amplitude and missing-history submissions fail closed", () => {
  const controls = { cycles: 2, lowerAmplitude: 0, headAmplitude: 0, phaseDelay: 0 };
  assert.throws(() => buildIdleReviewSubmission(entryDocument(), "adjust", controls), /不能全部为 0/);
  assert.throws(() => buildIdleReviewSubmission(
    entryDocument({ history: null }), "adjust",
    { ...controls, lowerAmplitude: 1 },
  ), /历史尚未加载/);
});

test("schematic sampler preserves the setup chain at the zero phase endpoint", () => {
  const preview = previewDocument();
  const parameters = parametersFromControls({
    cycles: 1, lowerAmplitude: 2, headAmplitude: 1, phaseDelay: 0,
  });
  const setup = sampleBodySwayPose(preview, parameters, 0);
  assert.equal(setup.length, 4);
  assert.deepEqual(setup[0].start, preview.anchor_px);
  assert.ok(Math.abs(setup[0].end.x - 500) < 1e-9);
  assert.ok(Math.abs(setup[0].end.y - 600) < 1e-9);
  assert.deepEqual(setup[1].start, setup[0].end);
  const moved = sampleBodySwayPose(preview, parameters, 0.25);
  assert.notDeepEqual(moved.at(-1).end, setup.at(-1).end);
});
