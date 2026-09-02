"use strict";

import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const SHA256 = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/;
const STATUSES = new Set([
  "queued", "running", "completed", "failed_retryable", "failed_terminal",
]);
const ENTRY_STATUSES = new Set(["ready", ...STATUSES]);
const STAGES = new Set([
  "queued", "compile_segments", "exact_inputs", "dynamic_seam_segments",
  "dynamic_seam_validation_segments", "publication", "parent_exact_readback",
  "completed", "failed",
]);
const PROBE_STATUSES = new Set([
  "continuous_preview_v2_reviewed_anchor_residual_certified", "indeterminate",
]);
const CLAIM_KEYS = Object.freeze([
  "attachment_area_overlap_assessed",
  "continuous_preview_v2_anchor_residual_within_engineering_tolerance",
  "dynamic_seam_safety", "official_runtime_equivalence",
  "publishable_timeline", "raster_gap_safety", "raster_overlap_safety",
  "release_authority", "reviewed_seam_anchor_set_v1_bound",
  "structural_gap_proxy_within_engineering_tolerance", "visual_seam_quality",
].sort());

export function dynamicSeamV2Path(rawJobId, rawSafetyRunId) {
  const jobId = requireReviewJobId(rawJobId);
  const safetyRunId = sha(rawSafetyRunId, "safety_run_id");
  return `/api/p10/runtime-capture/jobs/${jobId}/visual-review-v2/`
    + `safety-analysis-v2/runs/${safetyRunId}/dynamic-seam-v2`;
}

export function dynamicSeamV2RunsPath(jobId, safetyRunId) {
  return `${dynamicSeamV2Path(jobId, safetyRunId)}/runs`;
}

export function dynamicSeamV2RunPath(jobId, safetyRunId, rawRunId) {
  return `${dynamicSeamV2RunsPath(jobId, safetyRunId)}/${sha(rawRunId, "run_id")}`;
}

export function dynamicSeamV2ResultPath(jobId, safetyRunId, runId) {
  return `${dynamicSeamV2RunPath(jobId, safetyRunId, runId)}/result`;
}

export function dynamicSeamV2Href(rawJobId, rawSafetyRunId) {
  const jobId = requireReviewJobId(rawJobId);
  const safetyRunId = sha(rawSafetyRunId, "safety_run_id");
  return `./body-sway-dynamic-seam-v2.html?job_id=${encodeURIComponent(jobId)}`
    + `&safety_run_id=${encodeURIComponent(safetyRunId)}`;
}

export function normalizeDynamicSeamEntry(payload, expectedJobId, expectedSafetyRunId) {
  object(payload, "动态接缝状态");
  rejectPaths(payload);
  const jobId = requireReviewJobId(expectedJobId);
  const safetyRunId = sha(expectedSafetyRunId, "safety_run_id");
  if (payload.ok !== true || !ENTRY_STATUSES.has(payload.status)
      || requireReviewJobId(payload.job_id) !== jobId
      || sha(payload.safety_run_id, "safety_run_id") !== safetyRunId) {
    throw new Error("动态接缝状态与精确来源不一致");
  }
  const run = payload.run == null ? null : normalizeRun(payload.run);
  if ((payload.status === "ready") !== (run === null)
      || (run && run.status !== payload.status)) {
    throw new Error("动态接缝 entry 与 run 交叉接线");
  }
  return Object.freeze({ ok: true, status: payload.status, jobId, safetyRunId, run });
}

export function normalizeDynamicSeamResult(
  payload, expectedJobId, expectedSafetyRunId, expectedRunId,
) {
  object(payload, "动态接缝结果");
  rejectPaths(payload);
  const entry = normalizeDynamicSeamEntry(payload, expectedJobId, expectedSafetyRunId);
  const runId = sha(expectedRunId, "run_id");
  if (entry.status !== "completed" || !entry.run || entry.run.runId !== runId
      || payload.permanent_current_authority_claimed !== false
      || payload.release_authority_granted !== false) {
    throw new Error("动态接缝结果权威范围无效");
  }
  const probe = normalizeProbe(payload.probe);
  const bundle = normalizeBundle(payload.bundle, probe.sha256);
  const claims = normalizeClaims(payload.claims, probe.status);
  const releaseGate = object(payload.release_gate, "release gate");
  if (releaseGate.status !== "blocked" || claims.release_authority !== false) {
    throw new Error("P10.5d v2 不得解除发布门禁");
  }
  return Object.freeze({
    ok: true, status: "completed", jobId: entry.jobId,
    safetyRunId: entry.safetyRunId, run: entry.run,
    projectId: token(payload.project_id, "project_id"),
    clipId: token(payload.clip_id, "clip_id"), probe, bundle, claims,
    releaseGate: Object.freeze({
      status: "blocked", reasonCodes: tokens(releaseGate.reason_codes, "release reason"),
    }),
  });
}

function normalizeRun(value) {
  const row = object(value, "run");
  const status = oneOf(row.status, STATUSES, "run status");
  const stage = oneOf(row.stage, STAGES, "run stage");
  const validStage = status === "queued" ? stage === "queued"
    : status === "running" ? [
      "compile_segments", "exact_inputs", "dynamic_seam_segments",
      "dynamic_seam_validation_segments", "publication", "parent_exact_readback",
    ].includes(stage)
      : status === "completed" ? stage === "completed" : stage === "failed";
  if (!validStage) throw new Error("动态接缝 run stage 无效");
  const progress = object(row.progress, "progress");
  const total = integer(progress.total, "progress total", 1, 1_000_000);
  const current = integer(progress.current, "progress current", 0, total);
  const failureCode = row.failure_code == null ? null : token(row.failure_code, "failure code");
  if (status.startsWith("failed_") !== (failureCode !== null)) {
    throw new Error("动态接缝 failure code 无效");
  }
  const attempt = integer(row.attempt, "attempt", 1, 10_000);
  const previousRunId = row.previous_run_id == null
    ? null : sha(row.previous_run_id, "previous_run_id");
  if ((attempt === 1) !== (previousRunId === null)) throw new Error("attempt 链无效");
  if (typeof row.terminal !== "boolean" || typeof row.retryable !== "boolean"
      || row.terminal !== ["completed", "failed_retryable", "failed_terminal"].includes(status)
      || row.retryable !== (status === "failed_retryable")) {
    throw new Error("动态接缝 terminal/retryable 状态无效");
  }
  return Object.freeze({
    runId: sha(row.run_id, "run_id"), status, stage,
    progress: Object.freeze({ current, total }), failureCode, attempt, previousRunId,
    eventCount: integer(row.event_count, "event count", 1, 1_000_000),
    headEventSha256: sha(row.head_event_sha256, "head event SHA-256"),
    terminal: row.terminal, retryable: row.retryable,
  });
}

function normalizeProbe(value) {
  const row = object(value, "probe");
  const status = oneOf(row.status, PROBE_STATUSES, "probe status");
  const summary = normalizeSummary(row.summary);
  if (!Array.isArray(row.relationships) || row.relationships.length < 1
      || row.relationships.length > 64) throw new Error("接缝关系列表无效");
  const relationships = row.relationships.map((item) => normalizeRelationship(item));
  const ids = relationships.map(({ relationshipId }) => relationshipId);
  if (ids.join("\0") !== [...new Set(ids)].sort().join("\0")
      || relationships.length !== summary.relationshipCount
      || relationships.some(({ segmentCount }) => segmentCount !== summary.segmentCount)) {
    throw new Error("接缝关系与摘要不一致");
  }
  return Object.freeze({
    sha256: sha(row.sha256, "probe SHA-256"), status, summary,
    relationships: Object.freeze(relationships),
  });
}

function normalizeSummary(value) {
  const row = object(value, "probe summary");
  const segmentCount = integer(row.segment_count, "segment count", 1, 1_000_000);
  const certified = integer(row.certified_segment_count, "certified count", 0, segmentCount);
  const indeterminate = integer(
    row.indeterminate_segment_count, "indeterminate count", 0, segmentCount,
  );
  if (certified + indeterminate !== segmentCount) throw new Error("接缝区间摘要无效");
  return Object.freeze({
    segmentCount, certifiedSegmentCount: certified,
    indeterminateSegmentCount: indeterminate,
    relationshipCount: integer(row.relationship_count, "relationship count", 1, 64),
    anchorPairCount: integer(row.anchor_pair_count, "anchor pair count", 1, 4096),
    evaluatedBoxCount: integer(row.evaluated_box_count, "box count", 0, 100_000_000),
    thresholdSquaredPx2: finite(row.threshold_squared_px2, "threshold", false),
    maximumSquaredPx2: nullableFinite(
      row.max_squared_anchor_residual_upper_px2, "maximum residual",
    ),
    reasonCodes: tokens(row.reason_codes, "summary reason"),
  });
}

function normalizeRelationship(value) {
  const row = object(value, "relationship");
  const status = oneOf(row.status, new Set(["finite_upper_bound", "indeterminate"]),
    "relationship status");
  const maximum = nullableFinite(
    row.max_squared_anchor_residual_upper_px2, "relationship residual",
  );
  if (status === "finite_upper_bound" && maximum === null) {
    throw new Error("有限接缝关系缺少上界");
  }
  const gap = object(row.gap_proxy, "gap proxy");
  const overlap = object(row.overlap, "overlap");
  const gapMaximum = nullableFinite(gap.max_squared_upper_px2, "gap proxy bound");
  if (gap.model !== "anchor-residual-upper-bound-not-raster-gap"
      || gap.raster_gap_claimed !== false || gapMaximum !== maximum
      || overlap.status !== "not_evaluated" || overlap.raster_overlap_claimed !== false) {
    throw new Error("接缝代理证据越权或交叉接线");
  }
  return Object.freeze({
    relationshipId: token(row.relationship_id, "relationship_id"),
    segmentCount: integer(row.segment_count, "relationship segment count", 1, 1_000_000),
    status, maximumSquaredPx2: maximum,
    gapProxy: Object.freeze({ model: gap.model, maximumSquaredPx2: gapMaximum }),
    overlap: Object.freeze({ status: "not_evaluated" }),
    reasonCodes: tokens(row.reason_codes, "relationship reason"),
  });
}

function normalizeBundle(value, probeSha) {
  const row = object(value, "bundle receipt");
  const result = {
    sourceSetSha256: sha(row.source_set_sha256, "source set SHA-256"),
    sourceDocumentSha256: sha(row.source_document_sha256, "source document SHA-256"),
    probeSha256: sha(row.probe_sha256, "probe SHA-256"),
    bundleSha256: sha(row.bundle_sha256, "bundle SHA-256"),
  };
  if (result.probeSha256 !== probeSha) throw new Error("probe 与 bundle 地址不一致");
  return Object.freeze(result);
}

function normalizeClaims(value, status) {
  const row = object(value, "claims");
  if (Object.keys(row).sort().join("\0") !== CLAIM_KEYS.join("\0")) {
    throw new Error("动态接缝 claims 字段无效");
  }
  const certified = status === "continuous_preview_v2_reviewed_anchor_residual_certified";
  const expectedTrue = new Set(["reviewed_seam_anchor_set_v1_bound"]);
  if (certified) {
    expectedTrue.add("continuous_preview_v2_anchor_residual_within_engineering_tolerance");
    expectedTrue.add("structural_gap_proxy_within_engineering_tolerance");
  }
  for (const key of CLAIM_KEYS) {
    if (row[key] !== expectedTrue.has(key)) throw new Error("动态接缝 claims 越权");
  }
  return Object.freeze({ ...row });
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 必须是对象`);
  }
  return value;
}
function sha(value, label) {
  if (!SHA256.test(String(value ?? ""))) throw new Error(`${label} 无效`);
  return String(value);
}
function token(value, label) {
  if (!TOKEN.test(String(value ?? ""))) throw new Error(`${label} 无效`);
  return String(value);
}
function oneOf(value, values, label) {
  const result = token(value, label);
  if (!values.has(result)) throw new Error(`${label} 无效`);
  return result;
}
function integer(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label} 无效`);
  }
  return value;
}
function finite(value, label, allowZero = true) {
  if (typeof value !== "number" || !Number.isFinite(value)
      || value < (allowZero ? 0 : Number.EPSILON)) throw new Error(`${label} 无效`);
  return value;
}
function nullableFinite(value, label) {
  return value === null ? null : finite(value, label);
}
function tokens(value, label) {
  if (!Array.isArray(value)) throw new Error(`${label} 列表无效`);
  const result = value.map((item) => token(item, label));
  if (result.join("\0") !== [...new Set(result)].sort().join("\0")) {
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
