"use strict";

import {
  digestValue, exactCopy, exactFields, finiteNumber, integer, objectValue,
  safeId, sameJson,
} from "./body-sway-probe-contract-utils.js";
import {
  normalizeCanvasAdjustmentProbes, normalizeCanvasGain,
} from "./body-sway-canvas-adjustment-probe-contract.js";

export const CANVAS_ADJUSTMENT_FORMAT =
  "autospine-body-sway-canvas-adjustment-candidates";
export const CANVAS_ADJUSTMENT_VERSION = 1;

const BONES = ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"];
const TOP_FIELDS = [
  "format", "format_version", "project_id", "clip_id", "source", "timing",
  "reviewed_selection", "analyzer", "semantics", "diagnosis", "probes",
  "adjustment_candidates", "status", "release_gate", "summary",
];
const CANDIDATE_FIELDS = [
  "candidate_id", "kind", "status", "authority", "gain", "parameters",
  "probe_evidence_sha256", "requires_explicit_p10_1_revision", "claims",
];
const CLASSIFICATIONS = new Set([
  "reviewed_canvas_passed", "upstream_base_motion_canvas_overflow",
  "sampled_adjustment_candidate_available",
  "no_nonzero_sampled_adjustment_candidate",
]);
const SEMANTICS = Object.freeze({
  scope: "sampled-canvas-adjustment-candidate-only", authority: "none",
  human_decision_emitted: false, review_revision_written: false,
  temporary_preview_emitted: false, sampled_canvas_observation_claimed: true,
  discrete_gain_samples_are_safe_interval: false, safe_parameters_claimed: false,
  continuous_time_safety_claimed: false, visual_quality_claimed: false,
  runtime_equivalence_claimed: false,
  inter_attachment_seam_safety_claimed: false,
});
const CLAIMS = Object.freeze({
  sampled_canvas_passed: true, sampled_geometry_passed: true,
  safe_parameters: false, continuous_time: false, visual_quality: false,
  release_authority: false,
});
const RELEASE_REASONS = [
  "candidate_requires_explicit_p10_1_review", "continuous_time_safety_unproven",
  "manual_runtime_preview_required", "reviewed_seam_anchors_missing",
  "safe_parameters_unproven",
];
const DIAGNOSIS_REASONS = Object.freeze({
  reviewed_canvas_passed: ["reviewed_canvas_containment_passed"],
  upstream_base_motion_canvas_overflow: [
    "body_sway_zero_gain_did_not_remove_canvas_overflow",
    "upstream_base_motion_canvas_overflow",
  ],
  sampled_adjustment_candidate_available: [
    "lower_uniform_gain_sampled_canvas_and_geometry_passed",
    "requires_explicit_p10_1_revision",
  ],
  no_nonzero_sampled_adjustment_candidate: [
    "fixed_gain_grid_found_no_nonzero_sampled_pass",
  ],
});

export function normalizeCanvasAdjustmentEnvelope(value, context) {
  exactFields(value, ["candidate_sha256", "document"], "画布调整候选");
  const candidateSha256 = digestValue(value.candidate_sha256, "画布调整候选 SHA");
  const document = normalizeDocument(value.document, context);
  return {
    candidateSha256, document, classification: document.diagnosis.classification,
    probes: document.probes, proposal: document.adjustment_candidates[0] ?? null,
  };
}

function normalizeDocument(value, context) {
  exactFields(value, TOP_FIELDS, "画布调整候选文档");
  if (value.format !== CANVAS_ADJUSTMENT_FORMAT
      || value.format_version !== CANVAS_ADJUSTMENT_VERSION
      || value.status !== "candidate_only") throw new Error("画布调整候选合同无效");
  if (value.project_id !== context.packageRow.project_id
      || value.clip_id !== context.packageRow.clip_id) {
    throw new Error("画布调整候选与项目不一致");
  }
  const source = normalizeSource(value.source, context);
  const timing = normalizeTiming(value.timing, context.report?.timing);
  const selection = normalizeSelection(value.reviewed_selection);
  if (context.report && (!sameJson(selection, context.report.selection)
      || source.body_sway_probe_report_sha256 !== context.reportSha256)) {
    throw new Error("画布调整候选与 P10.2 报告不一致");
  }
  normalizeAnalyzer(value.analyzer);
  if (!sameJson(value.semantics, SEMANTICS)) throw new Error("画布调整候选语义无效");
  const probes = normalizeCanvasAdjustmentProbes(value.probes, timing);
  const diagnosis = normalizeDiagnosis(value.diagnosis, probes, context);
  const candidates = normalizeCandidates(value.adjustment_candidates, probes, selection);
  normalizeGate(value.release_gate);
  normalizeSummary(value.summary, diagnosis.classification, probes, candidates);
  return exactCopy({ ...value, source, timing, reviewed_selection: selection,
    diagnosis, probes, adjustment_candidates: candidates });
}

function normalizeSource(value, context) {
  exactFields(value, [
    "probe_inputs", "current_p10_1_head", "body_sway_probe_report_sha256",
  ], "画布调整来源");
  const inputs = objectValue(value.probe_inputs, "画布调整 probe inputs");
  for (const field of ["idle_behavior_candidates_sha256", "idle_behavior_decision_sha256"]) {
    digestValue(inputs[field], `画布调整 ${field}`);
  }
  const head = exactFields(value.current_p10_1_head,
    ["candidate_sha256", "decision_sha256", "revision"], "画布调整 P10.1 head");
  digestValue(head.candidate_sha256, "画布调整 candidate SHA");
  digestValue(head.decision_sha256, "画布调整 decision SHA");
  integer(head.revision, 1, "画布调整 revision");
  digestValue(value.body_sway_probe_report_sha256, "画布调整 report SHA");
  if (head.candidate_sha256 !== context.candidateSha
      || head.decision_sha256 !== context.sourceReview?.decision_sha256
      || head.revision !== context.sourceReview?.revision
      || inputs.idle_behavior_candidates_sha256 !== head.candidate_sha256
      || inputs.idle_behavior_decision_sha256 !== head.decision_sha256) {
    throw new Error("画布调整候选与 P10.1 current head 不一致");
  }
  if (context.report && !sameJson(inputs, context.report.source)) {
    throw new Error("画布调整 probe inputs 与 P10.2 报告不一致");
  }
  if (context.expectedProbeInputs && !sameJson(inputs, context.expectedProbeInputs)) {
    throw new Error("画布调整 probe inputs 与 P10.1 入口不一致");
  }
  return exactCopy(value);
}

function normalizeTiming(value, expected = null) {
  exactFields(value, ["ticks_per_second", "duration_ticks", "loop"], "画布调整时间基准");
  if (value.ticks_per_second !== 1_000_000
      || !Number.isInteger(value.duration_ticks) || value.duration_ticks < 1
      || typeof value.loop !== "boolean" || (expected && !sameJson(value, expected))) {
    throw new Error("画布调整时间基准无效");
  }
  return exactCopy(value);
}

function normalizeSelection(value) {
  exactFields(value, ["candidate_id", "feature_id", "action", "probe_status", "parameters"],
    "画布调整 reviewed selection");
  safeId(value.candidate_id, "画布调整 body-sway candidate");
  if (value.feature_id !== "body_sway" || value.action !== "adjust"
      || value.probe_status !== "pending_probe") throw new Error("画布调整选择无效");
  return { ...exactCopy(value), parameters: normalizeParameters(value.parameters) };
}

function normalizeAnalyzer(value) {
  exactFields(value, ["id", "version", "config"], "画布调整 analyzer");
  const config = exactFields(value.config, [
    "parameterization", "gain_denominator", "reviewed_gain_numerator",
    "search_order", "search_stop", "zero_gain_probe_required_after_reviewed_failure",
    "sample_schedule",
  ], "画布调整 analyzer config");
  const expected = {
    id: "body-sway-canvas-adjustment-analyzer", version: "1.0.0",
    config: { parameterization: "uniform-amplitude-gain", gain_denominator: 8,
      reviewed_gain_numerator: 8, search_order: [7, 6, 5, 4, 3, 2, 1],
      search_stop: "first-sampled-structural-pass",
      zero_gain_probe_required_after_reviewed_failure: true,
      sample_schedule: "exact-p10.2-probe-schedule" },
  };
  if (!sameJson(value, expected) || !Array.isArray(config.search_order)) {
    throw new Error("画布调整 analyzer profile 无效");
  }
}

function normalizeDiagnosis(value, probes, context) {
  exactFields(value, [
    "classification", "reason_codes", "reviewed_canvas_check",
    "zero_gain_canvas_status", "other_rejected_check_ids",
  ], "画布调整诊断");
  if (!CLASSIFICATIONS.has(value.classification)) throw new Error("画布调整诊断分类无效");
  const check = exactFields(value.reviewed_canvas_check,
    ["status", "sample_count", "failure_count", "evidence_sha256"], "原参数画布检查");
  digestValue(check.evidence_sha256, "原参数画布证据 SHA");
  const reviewed = probes.at(-1);
  if (reviewed.canvas_status !== check.status || reviewed.sample_count !== check.sample_count
      || reviewed.canvas_failure_tick_count !== check.failure_count) {
    throw new Error("画布调整诊断与 100% 档位不一致");
  }
  const zero = probes.find((row) => row.gain.numerator === 0);
  const gains = new Set(probes.map((row) => row.gain.numerator));
  const anyMiddlePass = probes.some((row) => row.gain.numerator > 0
    && row.gain.numerator < 8 && row.canvas_status === "passed"
    && row.sampled_geometry_status === "passed");
  const validClass = value.classification === "reviewed_canvas_passed"
    ? check.status === "passed" && !zero && probes.length === 1
    : value.classification === "upstream_base_motion_canvas_overflow"
      ? check.status === "rejected" && zero?.canvas_status === "rejected"
        && gains.size === 2 && gains.has(8)
      : value.classification === "no_nonzero_sampled_adjustment_candidate"
        ? check.status === "rejected" && zero?.canvas_status === "passed"
          && gains.size === 9 && !anyMiddlePass
        : check.status === "rejected" && zero?.canvas_status === "passed";
  const expectedOther = (context.result?.checks || []).filter((row) =>
    row.check_id !== "sampled_canvas_containment" && row.status === "rejected")
    .map((row) => row.check_id).sort();
  if (!validClass || value.zero_gain_canvas_status !== (zero?.canvas_status ?? "not_evaluated")
      || !sameJson(value.reason_codes, DIAGNOSIS_REASONS[value.classification])
      || (context.result && !sameJson(value.other_rejected_check_ids, expectedOther))) {
    throw new Error("画布调整诊断分类与离散实测不一致");
  }
  const resultCheck = context.result?.checks?.find(
    (row) => row.check_id === "sampled_canvas_containment");
  if (resultCheck && (resultCheck.status !== check.status
      || resultCheck.sample_count !== check.sample_count
      || resultCheck.failure_count !== check.failure_count
      || resultCheck.evidence_sha256 !== check.evidence_sha256)) {
    throw new Error("画布调整诊断与 P10.2 检查不一致");
  }
  return exactCopy(value);
}

function normalizeCandidates(value, probes, selection) {
  if (!Array.isArray(value) || value.length > 1) throw new Error("画布调整草稿数量无效");
  return value.map((raw) => {
    exactFields(raw, CANDIDATE_FIELDS, "画布调整草稿");
    const numerator = normalizeCanvasGain(raw.gain);
    const probe = probes.find((row) => row.gain.numerator === numerator);
    if (!/^body-sway-canvas-adjustment-[0-9a-f]{64}$/.test(raw.candidate_id)
        || raw.kind !== "uniform_amplitude_gain" || raw.status !== "unvalidated_draft"
        || raw.authority !== "none" || !probe || numerator === 0 || numerator === 8
        || probe.canvas_status !== "passed" || probe.sampled_geometry_status !== "passed"
        || raw.probe_evidence_sha256 !== probe.evidence_sha256
        || raw.requires_explicit_p10_1_revision !== true || !sameJson(raw.claims, CLAIMS)) {
      throw new Error("画布调整草稿越过了自动候选边界");
    }
    const parameters = normalizeParameters(raw.parameters);
    if (parameters.cycles !== selection.parameters.cycles
        || !sameJson(parameters.per_bone_phase_fraction,
          selection.parameters.per_bone_phase_fraction)) {
      throw new Error("画布调整草稿修改了幅度以外的参数");
    }
    const expectedAmplitudes = selection.parameters.per_bone_amplitude_deg.map((row) => ({
      bone_id: row.bone_id, value: row.value * numerator / 8,
    }));
    const gainSet = new Set(probes.map((row) => row.gain.numerator));
    const exactSearch = gainSet.size === 10 - numerator && gainSet.has(0)
      && Array.from({ length: 9 - numerator }, (_, index) => numerator + index)
        .every((gain) => gainSet.has(gain));
    if (!sameJson(parameters.per_bone_amplitude_deg, expectedAmplitudes)
        || !exactSearch || probes.some((row) => row.gain.numerator > numerator
          && row.canvas_status === "passed" && row.sampled_geometry_status === "passed")) {
      throw new Error("画布调整草稿不是最高通过的精确 gain 档位");
    }
    return { ...exactCopy(raw), parameters };
  });
}

function normalizeParameters(value) {
  exactFields(value, ["cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction"],
    "身体摆动草稿参数");
  integer(value.cycles, 1, "身体摆动次数", 64);
  const amplitudes = normalizePerBone(value.per_bone_amplitude_deg, 10, false);
  const phases = normalizePerBone(value.per_bone_phase_fraction, 1, true);
  if (!amplitudes.some((row) => row.value > 0)) throw new Error("身体摆动草稿幅度不能全为 0");
  return { cycles: value.cycles, per_bone_amplitude_deg: amplitudes,
    per_bone_phase_fraction: phases };
}

function normalizePerBone(value, maximum, exclusive) {
  if (!Array.isArray(value) || value.length !== BONES.length
      || value.some((row, index) => row?.bone_id !== BONES[index])) {
    throw new Error("身体摆动草稿骨骼顺序无效");
  }
  return value.map((row) => {
    exactFields(row, ["bone_id", "value"], "身体摆动逐骨参数");
    finiteNumber(row.value, "身体摆动逐骨数值");
    if (row.value < 0 || (exclusive ? row.value >= maximum : row.value > maximum)) {
      throw new Error("身体摆动逐骨数值越界");
    }
    return exactCopy(row);
  });
}

function normalizeGate(value) {
  exactFields(value, ["status", "reason_codes"], "画布调整发布门禁");
  if (value.status !== "blocked" || !sameJson(value.reason_codes, RELEASE_REASONS)) {
    throw new Error("画布调整发布门禁无效");
  }
}

function normalizeSummary(value, classification, probes, candidates) {
  exactFields(value, [
    "classification", "tested_gain_count", "adjustment_candidate_count",
    "reviewed_canvas_failure_tick_count", "zero_gain_canvas_failure_tick_count",
  ], "画布调整摘要");
  const zero = probes.find((row) => row.gain.numerator === 0);
  if (value.classification !== classification || value.tested_gain_count !== probes.length
      || value.adjustment_candidate_count !== candidates.length
      || value.reviewed_canvas_failure_tick_count !== probes.at(-1).canvas_failure_tick_count
      || value.zero_gain_canvas_failure_tick_count
        !== (zero ? zero.canvas_failure_tick_count : null)
      || (classification === "sampled_adjustment_candidate_available")
        !== (candidates.length === 1)) throw new Error("画布调整摘要不一致");
}
