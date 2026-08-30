"use strict";

import {
  digestValue, exactCopy, exactFields, integer, objectValue, sameJson,
} from "./body-sway-probe-contract-utils.js";

export const CHECK_IDS = Object.freeze([
  "loop_closure", "fk_finite", "sampled_mesh_deformation",
  "sampled_canvas_containment", "shared_index_internal_continuity",
  "inter_attachment_seams", "visual_quality",
]);

const RESULT_FIELDS = ["status", "release_gate", "schedule", "checks", "summary"];
const CHECK_FIELDS = [
  "check_id", "status", "reason_code", "subject_count", "sample_count",
  "failure_count", "evidence_sha256",
];
const SUMMARY_FIELDS = [
  "schedule_sample_count", "representative_sample_count", "rig_bone_count",
  "rotation_bone_count", "overlay_bone_count", "attachment_count",
  "mesh_attachment_count", "check_count", "passed_check_count",
  "rejected_check_count", "unobservable_check_count", "not_applicable_check_count",
];
const REPORT_FIELDS = [
  "format", "format_version", "project_id", "clip_id", "source", "timing",
  "selection", "prober", "semantics", "schedule", "sample_stream", "checks",
  "status", "release_gate", "summary",
];
const P3_FIELDS = [
  "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
  "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
  "visuals_sha256", "bundle_sha256",
];
const P5_FIELDS = [
  "target_profile_sha256", "instance_sha256", "run_sha256",
  "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
];
const P9_FIELDS = [
  "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
  "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
  "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
];
const TECHNICAL_SEMANTICS = Object.freeze({
  diagnostic_only: true,
  release_authority: false,
  runtime_equivalence_claimed: false,
  visual_quality_claimed: false,
  continuous_time_safety_claimed: false,
});

export function normalizeProbeResult(value, entryStatus, reportSha256) {
  if (value === null && ["p10_1_review_required", "not_applicable"].includes(entryStatus)) {
    if (reportSha256 !== null) throw new Error("无探针结果时不能声明报告身份");
    return null;
  }
  exactFields(value, RESULT_FIELDS, "结构探针报告摘要");
  digestValue(reportSha256, "结构探针报告 SHA");
  const schedule = normalizeSchedule(value.schedule);
  if (!Array.isArray(value.checks) || value.checks.length !== CHECK_IDS.length) {
    throw new Error("结构探针必须包含七项有序检查");
  }
  const checks = value.checks.map((row, index) => normalizeCheck(row, index));
  const rejected = checks.slice(0, 5).some((row) => row.status === "rejected");
  const expectedStatus = rejected ? "structural_rejected" : "manual_visual_required";
  if (value.status !== expectedStatus || entryStatus !== expectedStatus) {
    throw new Error("结构探针状态与结构检查不一致");
  }
  const releaseGate = normalizeReleaseGate(value.release_gate, rejected);
  const summary = normalizeSummary(value.summary, schedule, checks);
  return {
    status: value.status, reportSha256, schedule, checks, summary, releaseGate,
  };
}

export function normalizeProbeTechnical(value, context) {
  exactFields(value, ["report", "semantics"], "结构探针技术详情");
  if (!sameJson(value.semantics, TECHNICAL_SEMANTICS)) {
    throw new Error("结构探针技术语义无效");
  }
  if (!context.result) {
    if (value.report !== null) throw new Error("无结果时技术报告必须为空");
    return exactCopy(value);
  }
  const report = exactFields(value.report, REPORT_FIELDS, "结构探针完整报告");
  if (report.format !== "autospine-body-sway-probe-report" || report.format_version !== 1
      || report.project_id !== context.packageRow.project_id
      || report.clip_id !== context.packageRow.clip_id
      || report.status !== context.result.status) {
    throw new Error("结构探针完整报告身份无效");
  }
  for (const field of ["schedule", "checks", "summary", "release_gate"]) {
    const projected = field === "release_gate" ? context.result.releaseGate
      : context.result[field === "release_gate" ? "releaseGate" : field];
    if (!sameJson(report[field], projected)) throw new Error(`结构探针 ${field} 投影不一致`);
  }
  requireReportSource(report.source, context);
  requireReportSelection(report.selection, context.sourceReview);
  requireReportTiming(report.timing, context.preview);
  return exactCopy(value);
}

function normalizeSchedule(value) {
  exactFields(value, ["tick_schedule_sha256", "sample_count", "first_tick", "last_tick"],
    "结构探针采样计划");
  digestValue(value.tick_schedule_sha256, "结构探针采样计划 SHA");
  const sampleCount = integer(value.sample_count, 2, "结构探针采样数");
  const lastTick = integer(value.last_tick, 1, "结构探针结束 tick");
  if (value.first_tick !== 0) throw new Error("结构探针采样必须从 tick 0 开始");
  return { ...exactCopy(value), sample_count: sampleCount, last_tick: lastTick };
}

function normalizeCheck(value, index) {
  exactFields(value, CHECK_FIELDS, `结构检查 ${CHECK_IDS[index]}`);
  if (value.check_id !== CHECK_IDS[index]) throw new Error("结构检查顺序无效");
  for (const field of ["subject_count", "sample_count", "failure_count"]) {
    integer(value[field], 0, `结构检查 ${value.check_id} ${field}`);
  }
  if (index >= 5) {
    const reason = index === 5 ? "reviewed_seam_anchors_missing"
      : "manual_runtime_preview_required";
    if (value.status !== "unobservable" || value.reason_code !== reason
        || value.subject_count !== 0 || value.sample_count !== 0
        || value.failure_count !== 0 || value.evidence_sha256 !== null) {
      throw new Error(`结构检查 ${value.check_id} 必须留待后续阶段`);
    }
    return exactCopy(value);
  }
  if (value.status === "not_applicable") {
    if (!["clip_not_looping", "reviewed_noop"].includes(value.reason_code)
        || value.subject_count !== 0 || value.sample_count !== 0
        || value.failure_count !== 0 || value.evidence_sha256 !== null) {
      throw new Error(`结构检查 ${value.check_id} 不适用状态无效`);
    }
    return exactCopy(value);
  }
  if (!["passed", "rejected"].includes(value.status)
      || value.reason_code !== `sampled_check_${value.status}`
      || value.subject_count < 1 || value.sample_count < 2
      || value.failure_count > value.sample_count
      || (value.status === "passed") !== (value.failure_count === 0)) {
    throw new Error(`结构检查 ${value.check_id} 计算状态无效`);
  }
  digestValue(value.evidence_sha256, `结构检查 ${value.check_id} 证据 SHA`);
  return exactCopy(value);
}

function normalizeReleaseGate(value, rejected) {
  exactFields(value, ["status", "reason_codes"], "结构探针发布门禁");
  const expected = [
    "manual_runtime_preview_required", "reviewed_seam_anchors_missing",
    "safe_range_unproven",
  ];
  if (rejected) expected.push("sampled_structural_check_rejected");
  expected.sort();
  if (value.status !== "blocked" || !sameJson(value.reason_codes, expected)) {
    throw new Error("结构探针发布门禁无效");
  }
  return exactCopy(value);
}

function normalizeSummary(value, schedule, checks) {
  exactFields(value, SUMMARY_FIELDS, "结构探针统计");
  for (const field of SUMMARY_FIELDS) integer(value[field], 0, `结构探针统计 ${field}`);
  const count = (status) => checks.filter((row) => row.status === status).length;
  const expected = {
    schedule_sample_count: schedule.sample_count,
    check_count: CHECK_IDS.length,
    passed_check_count: count("passed"), rejected_check_count: count("rejected"),
    unobservable_check_count: count("unobservable"),
    not_applicable_check_count: count("not_applicable"),
  };
  if (Object.entries(expected).some(([field, expectedValue]) => value[field] !== expectedValue)
      || value.representative_sample_count < 2 || value.overlay_bone_count !== 4
      || value.rig_bone_count < 4 || value.rotation_bone_count < 4
      || value.attachment_count < 1 || value.mesh_attachment_count > value.attachment_count) {
    throw new Error("结构探针统计与检查证据不一致");
  }
  return exactCopy(value);
}

function requireReportSource(value, context) {
  exactFields(value, ["idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
    "layer_manifest_sha256", "p3", "p5", "p9"], "结构探针报告来源");
  for (const field of ["idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
    "layer_manifest_sha256"]) digestValue(value[field], `报告来源 ${field}`);
  for (const [stage, fields] of [["p3", P3_FIELDS], ["p5", P5_FIELDS], ["p9", P9_FIELDS]]) {
    exactFields(value[stage], fields, `结构探针 ${stage} 来源`);
    for (const field of fields) digestValue(value[stage][field], `${stage}.${field}`);
  }
  if (value.idle_behavior_candidates_sha256 !== context.candidateSha
      || value.idle_behavior_decision_sha256 !== context.sourceReview?.decision_sha256
      || value.layer_manifest_sha256 !== value.p3.layer_manifest_sha256
      || value.p9.motion_instance_v2_sha256 !== context.packageRow.motion_instance_v2_sha256
      || value.p9.motion_policy_decision_sha256 !== context.packageRow.p9_decision_sha256
      || value.p9.bundle_sha256 !== context.packageRow.reviewed_motion_bundle_sha256) {
    throw new Error("结构探针报告来源与当前 head 不一致");
  }
}

function requireReportSelection(value, sourceReview) {
  objectValue(value, "结构探针报告选择");
  if (value.feature_id !== "body_sway" || value.action !== sourceReview?.action
      || value.probe_status !== sourceReview?.probe_status || !objectValue(value.parameters,
        "结构探针报告参数")) {
    throw new Error("结构探针报告选择与 P10.1 head 不一致");
  }
}

function requireReportTiming(value, preview) {
  exactFields(value, ["ticks_per_second", "duration_ticks", "loop"], "结构探针时间基准");
  if (!preview || value.ticks_per_second !== preview.ticksPerSecond
      || value.duration_ticks !== preview.durationTicks || typeof value.loop !== "boolean") {
    throw new Error("结构探针报告与预览时间基准不一致");
  }
}
