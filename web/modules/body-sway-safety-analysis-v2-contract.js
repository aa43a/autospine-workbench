"use strict";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const SHA256 = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MAX_RECEIPT_BYTES = 160 * 1024 * 1024;
const RUN_STATUSES = new Set([
  "queued", "running", "completed", "failed_retryable", "failed_terminal",
]);
const ENTRY_STATUSES = new Set(["ready", ...RUN_STATUSES]);
const RUN_STAGES = new Set([
  "queued", "review_admission", "exact_source", "amplitude_probes",
  "continuous_segments", "continuous_boxes", "continuous_validation",
  "current_head_recheck",
  "sealing", "completed", "failed",
]);
const AMPLITUDE_STATUSES = new Set([
  "sampled_structural_passed", "sampled_structural_rejected",
]);
const VISUAL_STATUSES = new Set([
  "not_reviewed", "official_runtime_sampled_cases_approved",
]);
const CONTINUOUS_STATUSES = new Set([
  "continuous_structural_certified", "indeterminate",
]);
const CONTINUOUS_REASONS = new Set([
  "absolute_triangle_area_unproven", "canvas_containment_unproven",
  "empty_attachment_geometry", "interval_backend_error",
  "maximum_area_ratio_unproven", "maximum_edge_stretch_unproven",
  "minimum_area_ratio_unproven", "non_finite_interval_bound",
  "parameter_resolution_exhausted", "subdivision_box_budget_exhausted",
  "subdivision_depth_exhausted",
]);
const CLAIM_KEYS = [
  "continuous_preview_model_structural_safety",
  "uniform_gain_zero_to_reviewed_structurally_certified",
  "official_runtime_continuous_equivalence", "visual_gain_range", "reviewed_seam_anchors",
  "motion_instance_v3", "publishable_timeline", "release_authority",
].sort();
const FALSE_CLAIMS = CLAIM_KEYS.slice(2);

export function safetyAnalysisV2Path(rawJobId) {
  const jobId = requireReviewJobId(rawJobId);
  return `/api/p10/runtime-capture/jobs/${jobId}/visual-review-v2/safety-analysis-v2`;
}

export function safetyAnalysisV2RunsPath(rawJobId) {
  return `${safetyAnalysisV2Path(rawJobId)}/runs`;
}
export function safetyAnalysisV2RunPath(rawJobId, rawRunId) {
  return `${safetyAnalysisV2RunsPath(rawJobId)}/${requireSha(rawRunId, "run_id")}`;
}

export function safetyAnalysisV2ResultPath(rawJobId, rawRunId) {
  return `${safetyAnalysisV2RunPath(rawJobId, rawRunId)}/result`;
}
export function safetyAnalysisV2Href(rawJobId) {
  const jobId = requireReviewJobId(rawJobId);
  return `./body-sway-safety-analysis-v2.html?job_id=${encodeURIComponent(jobId)}`;
}

export function normalizeSafetyAnalysisEntry(payload, expectedJobId) {
  object(payload, "安全分析状态");
  rejectPaths(payload);
  if (payload.ok !== true || !ENTRY_STATUSES.has(payload.status)) {
    throw new Error("安全分析状态响应无效");
  }
  const jobId = requireReviewJobId(expectedJobId);
  if (requireReviewJobId(payload.job_id) !== jobId) {
    throw new Error("安全分析状态与采集任务不一致");
  }
  const run = payload.run === undefined || payload.run === null
    ? null : normalizeRun(payload.run, jobId);
  if (payload.status === "ready" && run !== null) {
    throw new Error("ready 状态不能绑定历史 run");
  }
  if (payload.status !== "ready" && (!run || run.status !== payload.status)) {
    throw new Error("安全分析 run 状态交叉接线");
  }
  return Object.freeze({ ok: true, status: payload.status, jobId, run });
}

export function normalizeSafetyAnalysisResult(payload, expectedJobId, expectedRunId) {
  object(payload, "安全分析结果");
  rejectPaths(payload);
  const jobId = requireReviewJobId(expectedJobId);
  const runId = requireSha(expectedRunId, "run_id");
  if (payload.ok !== true || payload.status !== "completed"
      || requireReviewJobId(payload.job_id) !== jobId
      || payload.authority_scope !== "compile_time_snapshot") {
    throw new Error("安全分析结果状态无效");
  }
  const run = normalizeRun(payload.run, jobId);
  if (run.runId !== runId || run.status !== "completed") {
    throw new Error("安全分析结果与 run 不一致");
  }
  const amplitude = normalizeAmplitude(payload.amplitude);
  const continuous = normalizeContinuous(payload.continuous);
  const claims = object(payload.claims, "claims");
  const certified = continuous.status === "continuous_preview_model_structural_certified";
  if (Object.keys(claims).sort().join("\u0000") !== CLAIM_KEYS.join("\u0000")
      || claims.continuous_preview_model_structural_safety !== certified
      || claims.uniform_gain_zero_to_reviewed_structurally_certified !== certified
      || FALSE_CLAIMS.some((key) => claims[key] !== false)) {
    throw new Error("安全分析 claims 超出固定权威范围");
  }
  const releaseGate = object(payload.release_gate, "release_gate");
  if (claims.release_authority !== false || releaseGate.status !== "blocked") {
    throw new Error("P10.4b v2 不得解除发布门禁");
  }
  const releaseReasons = tokens(releaseGate.reason_codes, null, "release reason");
  const documents = object(payload.documents, "document receipts");
  const receipts = Object.freeze({
    amplitude: normalizeReceipt(
      documents.amplitude, amplitude.sha256,
      "autospine-body-sway-amplitude-envelope-candidate", "amplitude receipt",
    ),
    continuous: normalizeReceipt(
      documents.continuous, continuous.sha256,
      "autospine-body-sway-continuous-preview-proof", "continuous receipt",
    ),
  });
  const indeterminate = amplitude.status === "indeterminate"
    || continuous.status === "indeterminate"
    || continuous.summary.indeterminateSegmentCount > 0;
  return Object.freeze({
    ok: true, status: "completed", jobId, run,
    projectId: requireToken(payload.project_id, "project_id"),
    clipId: requireToken(payload.clip_id, "clip_id"),
    amplitude, continuous, claims: Object.freeze({ ...claims }),
    releaseGate: Object.freeze({ status: "blocked", reason_codes: releaseReasons }),
    receipts, authorityScope: "compile_time_snapshot", indeterminate,
  });
}

function normalizeReceipt(value, expectedSha, expectedFormat, label) {
  const row = object(value, label);
  const expected = ["format", "format_version", "sha256", "size_bytes"];
  if (Object.keys(row).sort().join("\u0000") !== expected.sort().join("\u0000")) {
    throw new Error(`${label} 字段无效`);
  }
  const sha256 = requireSha(row.sha256, `${label} SHA-256`);
  if (sha256 !== expectedSha || row.format !== expectedFormat
      || row.format_version !== 2) throw new Error(`${label} 与结果身份不一致`);
  return Object.freeze({
    format: expectedFormat, formatVersion: 2,
    sha256,
    sizeBytes: integer(row.size_bytes, `${label} size`, 1, MAX_RECEIPT_BYTES),
  });
}

function normalizeRun(value, jobId) {
  const row = object(value, "run");
  const status = requireOneOf(row.status, RUN_STATUSES, "run status");
  const stage = requireOneOf(row.stage, RUN_STAGES, "run stage");
  const validStage = status === "queued" ? stage === "queued"
    : status === "running" ? !["queued", "completed", "failed"].includes(stage)
      : status === "completed" ? stage === "completed" : stage === "failed";
  if (!validStage) throw new Error("run status 与 stage 不一致");
  const progress = object(row.progress, "run progress");
  const total = integer(progress.total, "progress total", 1, 1000000);
  const current = integer(progress.current, "progress current", 0, total);
  const failure = row.failure_code == null
    ? null : requireToken(row.failure_code, "failure_code");
  if (status.startsWith("failed_") !== (failure !== null)) {
    throw new Error("run failure_code 与状态不一致");
  }
  return Object.freeze({
    runId: requireSha(row.run_id, "run_id"), jobId,
    status, stage,
    progress: Object.freeze({ current, total }),
    failureCode: failure,
  });
}

function normalizeAmplitude(value) {
  const row = object(value, "amplitude");
  if (row.status !== "candidate_only"
      || !Array.isArray(row.probes) || row.probes.length !== 9) {
    throw new Error("幅度结构点必须恰好为九档");
  }
  const probes = row.probes.map((probe, index) => {
    const item = object(probe, `amplitude probe ${index}`);
    const gain = object(item.gain, `amplitude gain ${index}`);
    const denominator = integer(gain.denominator, "gain denominator", 1, 1024);
    const numerator = integer(gain.numerator, "gain numerator", 0, denominator);
    if (denominator !== 8 || numerator !== index) {
      throw new Error("幅度结构点必须严格按 0/8 到 8/8 排列");
    }
    const status = requireOneOf(item.status, AMPLITUDE_STATUSES, "amplitude status");
    const visual = requireOneOf(
      item.visual_review_status, VISUAL_STATUSES, "visual review status",
    );
    const expectedVisual = index === 8
      ? "official_runtime_sampled_cases_approved" : "not_reviewed";
    if (visual !== expectedVisual) throw new Error("人工视觉范围与 reviewed gain 不一致");
    return Object.freeze({
      gain: Object.freeze({ numerator, denominator }),
      status, visualReviewStatus: visual,
    });
  });
  return Object.freeze({
    sha256: requireSha(row.sha256, "amplitude SHA-256"),
    status: "candidate_only",
    probes: Object.freeze(probes),
  });
}

function normalizeContinuous(value) {
  const row = object(value, "continuous");
  const summary = object(row.summary, "continuous summary");
  const segments = Array.isArray(row.segments) ? row.segments.map((segment, index) => {
    const item = object(segment, `continuous segment ${index}`);
    const status = requireOneOf(item.status, CONTINUOUS_STATUSES, "segment status");
    const reasons = tokens(item.reason_codes, CONTINUOUS_REASONS, "reason code");
    if ((status === "continuous_structural_certified") !== (reasons.length === 0)) {
      throw new Error("连续区间状态与原因不一致");
    }
    return Object.freeze({
      leftTick: integer(item.left_tick, "left tick", 0, 1_000_000_000),
      rightTick: integer(item.right_tick, "right tick", 1, 1_000_000_000),
      status, reasonCodes: reasons,
    });
  }) : null;
  if (!segments) throw new Error("连续区间列表无效");
  const count = integer(summary.segment_count, "segment count", 0, 1000000);
  const certified = integer(
    summary.certified_segment_count, "certified segment count", 0, count,
  );
  const indeterminate = integer(
    summary.indeterminate_segment_count, "indeterminate segment count", 0, count,
  );
  const adjacent = segments.every((item, index) => item.leftTick < item.rightTick
    && (!index || segments[index - 1].rightTick === item.leftTick));
  const expectedStatus = indeterminate ? "indeterminate"
    : "continuous_preview_model_structural_certified";
  if (count !== segments.length || certified + indeterminate !== count
      || !adjacent || row.status !== expectedStatus) {
    throw new Error("连续区间摘要与区间列表不一致");
  }
  return Object.freeze({
    sha256: requireSha(row.sha256, "continuous SHA-256"),
    status: expectedStatus,
    summary: Object.freeze({
      segmentCount: count, certifiedSegmentCount: certified,
      indeterminateSegmentCount: indeterminate,
    }),
    segments: Object.freeze(segments),
  });
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 必须是对象`);
  }
  return value;
}

function requireSha(value, label) {
  if (!SHA256.test(String(value ?? ""))) throw new Error(`${label} 无效`);
  return String(value);
}

function requireToken(value, label) {
  if (!TOKEN.test(String(value ?? ""))) throw new Error(`${label} 无效`);
  return String(value);
}

function requireOneOf(value, choices, label) {
  const token = requireToken(value, label);
  if (!choices.has(token)) throw new Error(`${label} 无效`);
  return token;
}
function integer(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label} 无效`);
  }
  return value;
}

function tokens(value, allowed, label) {
  if (!Array.isArray(value)) throw new Error(`${label} 列表无效`);
  const result = value.map((item) => requireToken(item, label));
  if ((allowed && result.some((item) => !allowed.has(item)))
      || result.join("\u0000") !== [...new Set(result)].sort().join("\u0000")) {
    throw new Error(`${label} 列表无效`);
  }
  return Object.freeze(result);
}

function rejectPaths(value) {
  const pending = [value];
  while (pending.length) {
    const row = pending.pop();
    for (const [key, item] of Object.entries(row)) {
      if (key.toLowerCase().includes("path")) throw new Error("响应泄漏本地路径");
      if (item && typeof item === "object") pending.push(item);
    }
  }
}
