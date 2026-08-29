"use strict";

import { TARGET_BONES } from "./idle-behavior-review-contract.js";
import { IDLE_REVIEW_INTENT } from "./idle-behavior-review-api.js";

export const CONTROL_LIMITS = Object.freeze({
  cycles: { min: 1, max: 64, step: 1 },
  lowerAmplitude: { min: 0, max: 10, step: "any" },
  headAmplitude: { min: 0, max: 10, step: "any" },
  phaseDelay: { min: 0, max: 0.333333333333, step: "any" },
});

export function bodySwayFeature(entry) {
  return entry?.candidate?.features?.find((row) => row.feature_id === "body_sway") ?? null;
}

export function controlsFromSuggestion(suggestion) {
  return controlsFromParameters(suggestion?.payload);
}

export function controlsFromParameters(payload) {
  const amplitudes = valuesByBone(payload?.per_bone_amplitude_deg);
  const phases = valuesByBone(payload?.per_bone_phase_fraction);
  return normalizeControls({
    cycles: payload?.cycles ?? 2,
    lowerAmplitude: amplitudes.get("spine-chest") ?? 0.8,
    headAmplitude: amplitudes.get("neck-head") ?? 0.2,
    phaseDelay: phaseStep(phases),
  });
}

export function initialBodySwayParameters(entry) {
  const head = entry?.history?.items?.at(-1);
  return head?.action === "adjust" ? head.parameters : entry?.suggestion?.payload ?? null;
}

export function normalizeControls(value) {
  return {
    cycles: boundedInteger(value.cycles, CONTROL_LIMITS.cycles),
    lowerAmplitude: boundedNumber(value.lowerAmplitude, CONTROL_LIMITS.lowerAmplitude),
    headAmplitude: boundedNumber(value.headAmplitude, CONTROL_LIMITS.headAmplitude),
    phaseDelay: boundedNumber(value.phaseDelay, CONTROL_LIMITS.phaseDelay),
  };
}

export function parametersFromControls(value, sourceParameters = null) {
  const controls = normalizeControls(value);
  if (sourceParameters !== null
      && controlsEqual(controls, controlsFromParameters(sourceParameters))) {
    return exactCopy(sourceParameters);
  }
  const source = sourceParameters === null ? null : sourceProfile(sourceParameters);
  const amplitudes = source
    ? adjustedAmplitudes(controls, source)
    : [
      quantize(controls.lowerAmplitude * 0.75), controls.lowerAmplitude,
      quantize(controls.headAmplitude * 0.65), controls.headAmplitude,
    ];
  const phases = source && controls.phaseDelay === source.phaseDelay
    ? [...source.phases]
    : TARGET_BONES.map((_, index) => quantize(controls.phaseDelay * index));
  return {
    cycles: controls.cycles,
    per_bone_amplitude_deg: TARGET_BONES.map((bone_id, index) => ({
      bone_id, value: amplitudes[index],
    })),
    per_bone_phase_fraction: TARGET_BONES.map((bone_id, index) => ({
      bone_id, value: phases[index],
    })),
  };
}

export function baselineFromHistory(history) {
  if (history === null) throw new Error("复核历史尚未加载，不能提交");
  return {
    baseRevision: history.current_revision,
    previousDecisionSha256: history.head_decision_sha256,
  };
}

export function buildIdleReviewSubmission(
  entry, action, controls, sourceParameters = initialBodySwayParameters(entry),
) {
  const feature = bodySwayFeature(entry);
  if (feature?.availability !== "candidate") throw new Error("当前项目没有身体摆动候选");
  if (!["adjust", "reject", "unobservable"].includes(action)) {
    throw new Error("P10 人工动作无效");
  }
  const baseline = baselineFromHistory(entry.history);
  const parameters = action === "adjust"
    ? parametersFromControls(controls, sourceParameters) : null;
  if (action === "adjust"
      && !parameters.per_bone_amplitude_deg.some((row) => row.value > 0)) {
    throw new Error("身体摆动强度不能全部为 0；可以选择不使用身体摆动");
  }
  return {
    format: "autospine-idle-behavior-review-submission",
    format_version: 1,
    intent: IDLE_REVIEW_INTENT,
    explicit_confirmation: true,
    package_id: entry.package.package_id,
    candidate_sha256: entry.candidate_sha256,
    base_revision: baseline.baseRevision,
    previous_decision_sha256: baseline.previousDecisionSha256,
    action,
    reason_code: ({
      adjust: entry.suggestion.reason_code,
      reject: "human-declined-body-sway-v1",
      unobservable: "human-marked-unobservable-v1",
    })[action],
    parameters,
  };
}

export function sampleBodySwayPose(preview, parameters, progress) {
  if (!preview || !parameters) return null;
  const phaseByBone = valuesByBone(parameters.per_bone_phase_fraction);
  const amplitudeByBone = valuesByBone(parameters.per_bone_amplitude_deg);
  let start = { ...preview.anchor_px };
  let accumulatedDelta = 0;
  return preview.bones.map((bone) => {
    const phase = phaseByBone.get(bone.bone_id) ?? 0;
    const amplitude = amplitudeByBone.get(bone.bone_id) ?? 0;
    const delta = Math.sin(2 * Math.PI * (parameters.cycles * progress + phase)) * amplitude;
    accumulatedDelta += delta;
    const rotation = bone.setup_world_rotation_deg + accumulatedDelta;
    const radians = rotation * Math.PI / 180;
    const end = {
      x: start.x + bone.length_px * Math.cos(radians),
      y: start.y + bone.length_px * Math.sin(radians),
    };
    const row = { bone_id: bone.bone_id, start, end, rotation, delta };
    start = end;
    return row;
  });
}

export function setupPose(preview) {
  if (!preview) return null;
  return preview.bones.map((bone) => ({
    bone_id: bone.bone_id,
    start: { ...bone.setup_start_px }, end: { ...bone.setup_end_px },
  }));
}

export function formatProgress(progress, preview) {
  const seconds = preview
    ? progress * preview.duration_ticks / preview.ticks_per_second : 0;
  return `${seconds.toFixed(2)} s`;
}

function valuesByBone(rows) {
  return new Map(Array.isArray(rows) ? rows.map((row) => [row.bone_id, Number(row.value)]) : []);
}

function phaseStep(values) {
  if (!values.size) return 0.04;
  const first = values.get(TARGET_BONES[0]) ?? 0;
  const second = values.get(TARGET_BONES[1]) ?? first;
  return clamp(second - first, 0, CONTROL_LIMITS.phaseDelay.max);
}

function sourceProfile(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("身体摆动来源参数无效");
  }
  const amplitudes = exactPerBoneValues(value.per_bone_amplitude_deg, 10, false);
  const phases = exactPerBoneValues(value.per_bone_phase_fraction, 1, true);
  const controls = controlsFromParameters(value);
  return { amplitudes, phases, phaseDelay: controls.phaseDelay };
}

function exactPerBoneValues(rows, maximum, exclusiveMaximum) {
  if (!Array.isArray(rows) || rows.length !== TARGET_BONES.length
      || rows.some((row, index) => row?.bone_id !== TARGET_BONES[index])) {
    throw new Error("身体摆动来源骨骼顺序无效");
  }
  return rows.map((row) => {
    const number = Number(row.value);
    if (!Number.isFinite(number) || number < 0
        || (exclusiveMaximum ? number >= maximum : number > maximum)) {
      throw new Error("身体摆动来源数值无效");
    }
    return number;
  });
}

function adjustedAmplitudes(controls, source) {
  const lowerDelta = quantize(controls.lowerAmplitude - source.amplitudes[1]);
  const headDelta = quantize(controls.headAmplitude - source.amplitudes[3]);
  return [
    controls.lowerAmplitude === 0 ? 0
      : lowerDelta === 0 ? source.amplitudes[0]
      : quantize(clamp(source.amplitudes[0] + lowerDelta, 0, 10)),
    controls.lowerAmplitude,
    controls.headAmplitude === 0 ? 0
      : headDelta === 0 ? source.amplitudes[2]
      : quantize(clamp(source.amplitudes[2] + headDelta, 0, 10)),
    controls.headAmplitude,
  ];
}

function boundedInteger(value, limits) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < limits.min || number > limits.max) {
    throw new Error("摆动次数超出可编辑范围");
  }
  return number;
}

function boundedNumber(value, limits) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < limits.min || number > limits.max) {
    throw new Error("身体摆动参数超出可编辑范围");
  }
  return number;
}

function quantize(value) {
  if (!Number.isFinite(value)) throw new Error("身体摆动参数必须为有限数值");
  return value;
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function controlsEqual(left, right) {
  return left.cycles === right.cycles
    && left.lowerAmplitude === right.lowerAmplitude
    && left.headAmplitude === right.headAmplitude
    && left.phaseDelay === right.phaseDelay;
}

function exactCopy(value) {
  return JSON.parse(JSON.stringify(value));
}
