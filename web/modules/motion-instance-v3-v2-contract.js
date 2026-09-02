"use strict";

import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const SHA256 = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/;
const STATUSES = new Set([
  "queued", "running", "completed", "failed_retryable", "failed_terminal",
]);
const ENTRY_STATUSES = new Set(["ready", ...STATUSES]);
const STAGES = new Set([
  "queued", "exact_inputs", "motion_consumer_admission",
  "motion_instance_v3", "publication", "parent_exact_readback",
  "completed", "failed",
]);
const INVENTORY = Object.freeze([
  "body-sway-motion-consumer-admission-v2.json",
  "motion-instance-v3.json",
  "run-manifest-v2.json",
]);
const AUTHORITY = Object.freeze({
  motion_instance_v3_emitted: true,
  attachment_area_overlap_assessed: false,
  dynamic_seam_safety: false,
  full_attachment_boundary_continuity: false,
  publishable_timeline: false,
  spine_adapter_emitted: false,
  runtime_equivalence: false,
  raster_visual_quality: false,
  persistent_current_head_authority: false,
  release_authority: false,
});
const RELEASE_REASONS = Object.freeze([
  "attachment_area_overlap_not_assessed",
  "dynamic_seam_safety_unproven",
  "full_attachment_boundary_raster_visual_regression_missing",
  "persistent_current_head_authority_not_granted",
  "publishable_timeline_not_emitted",
  "raster_visual_quality_unproven",
  "runtime_equivalence_unproven",
  "spine_adapter_not_emitted",
]);

export function motionInstanceV3V2Path(job, safetyRun, dynamicRun) {
  return dynamicRunPath(job, safetyRun, dynamicRun) + "/motion-instance-v3-v2";
}

export function motionInstanceV3V2RunsPath(job, safetyRun, dynamicRun) {
  return motionInstanceV3V2Path(job, safetyRun, dynamicRun) + "/runs";
}

export function motionInstanceV3V2RunPath(job, safetyRun, dynamicRun, run) {
  return motionInstanceV3V2RunsPath(job, safetyRun, dynamicRun)
    + `/${sha(run, "run_id")}`;
}

export function motionInstanceV3V2ResultPath(job, safetyRun, dynamicRun, run) {
  return motionInstanceV3V2RunPath(job, safetyRun, dynamicRun, run) + "/result";
}

export function motionInstanceV3V2Href(job, safetyRun, dynamicRun) {
  const ids = exactIds(job, safetyRun, dynamicRun);
  return `./motion-instance-v3-v2.html?job_id=${encodeURIComponent(ids.jobId)}`
    + `&safety_run_id=${encodeURIComponent(ids.safetyRunId)}`
    + `&dynamic_run_id=${encodeURIComponent(ids.dynamicRunId)}`;
}

export function normalizeMotionInstanceV3V2Entry(
  payload, expectedJob, expectedSafetyRun, expectedDynamicRun,
) {
  object(payload, "MotionInstance 状态");
  rejectPaths(payload);
  const ids = exactIds(expectedJob, expectedSafetyRun, expectedDynamicRun);
  if (payload.ok !== true || !ENTRY_STATUSES.has(payload.status)
      || requireReviewJobId(payload.job_id) !== ids.jobId
      || sha(payload.safety_run_id, "safety_run_id") !== ids.safetyRunId
      || sha(payload.dynamic_run_id, "dynamic_run_id") !== ids.dynamicRunId) {
    throw new Error("MotionInstance 状态与精确来源不一致");
  }
  const run = payload.run == null ? null : normalizeRun(payload.run);
  if ((payload.status === "ready") !== (run === null)
      || (run && run.status !== payload.status)) {
    throw new Error("MotionInstance entry 与 run 交叉接线");
  }
  return Object.freeze({ ok: true, status: payload.status, ...ids, run });
}

export function normalizeMotionInstanceV3V2Result(
  payload, expectedJob, expectedSafetyRun, expectedDynamicRun, expectedRun,
) {
  object(payload, "MotionInstance 结果");
  rejectPaths(payload);
  const entry = normalizeMotionInstanceV3V2Entry(
    payload, expectedJob, expectedSafetyRun, expectedDynamicRun,
  );
  const runId = sha(expectedRun, "run_id");
  if (entry.status !== "completed" || !entry.run || entry.run.runId !== runId) {
    throw new Error("MotionInstance completed run 无效");
  }
  const address = exactObject(payload.address, [
    "motion_instance_v3_sha256", "bundle_sha256",
  ], "MotionInstance address");
  const inventory = stringList(payload.inventory, "inventory");
  if (inventory.join("\0") !== INVENTORY.join("\0")) {
    throw new Error("MotionInstance 三文件 inventory 无效");
  }
  const authority = normalizeAuthority(payload.authority);
  const release = exactObject(
    payload.release_gate, ["status", "reason_codes"], "release gate",
  );
  const reasons = tokenList(release.reason_codes, "release reason");
  if (reasons.join("\0") !== RELEASE_REASONS.join("\0")) {
    throw new Error("MotionInstance 发布阻塞原因无效");
  }
  const verification = exactObject(
    payload.verification, ["status", "exact_readback"], "verification",
  );
  if (release.status !== "blocked" || verification.status !== "passed"
      || verification.exact_readback !== true) {
    throw new Error("MotionInstance 精确读回或发布门禁无效");
  }
  return Object.freeze({
    ok: true, status: "completed", ...entry,
    projectId: token(payload.project_id, "project_id"),
    clipId: token(payload.clip_id, "clip_id"),
    address: Object.freeze({
      motionInstanceV3Sha256: sha(
        address.motion_instance_v3_sha256, "MotionInstance v3 SHA-256",
      ),
      bundleSha256: sha(address.bundle_sha256, "bundle SHA-256"),
    }),
    runSha256: sha(payload.run_sha256, "run SHA-256"),
    inventory: Object.freeze(inventory), authority,
    releaseGate: Object.freeze({ status: "blocked", reasonCodes: reasons }),
    verification: Object.freeze({ status: "passed", exactReadback: true }),
    reused: boolean(payload.reused, "reused"),
  });
}

function dynamicRunPath(job, safetyRun, dynamicRun) {
  const ids = exactIds(job, safetyRun, dynamicRun);
  return `/api/p10/runtime-capture/jobs/${ids.jobId}/visual-review-v2/`
    + `safety-analysis-v2/runs/${ids.safetyRunId}/dynamic-seam-v2/`
    + `runs/${ids.dynamicRunId}`;
}

function exactIds(job, safetyRun, dynamicRun) {
  return Object.freeze({
    jobId: requireReviewJobId(job),
    safetyRunId: sha(safetyRun, "safety_run_id"),
    dynamicRunId: sha(dynamicRun, "dynamic_run_id"),
  });
}

function normalizeRun(value) {
  const row = object(value, "run");
  const status = oneOf(row.status, STATUSES, "run status");
  const stage = oneOf(row.stage, STAGES, "run stage");
  const valid = status === "queued" ? stage === "queued"
    : status === "running" ? [
      "exact_inputs", "motion_consumer_admission", "motion_instance_v3",
      "publication", "parent_exact_readback",
    ].includes(stage)
      : status === "completed" ? stage === "completed" : stage === "failed";
  if (!valid) throw new Error("MotionInstance run stage 无效");
  const progress = object(row.progress, "progress");
  const total = integer(progress.total, "progress total", 1, 1_000_000);
  const current = integer(progress.current, "progress current", 0, total);
  const failureCode = row.failure_code == null
    ? null : token(row.failure_code, "failure code");
  if (status.startsWith("failed_") !== (failureCode !== null)) {
    throw new Error("MotionInstance failure code 无效");
  }
  const attempt = integer(row.attempt, "attempt", 1, 10_000);
  const previousRunId = row.previous_run_id == null
    ? null : sha(row.previous_run_id, "previous_run_id");
  if ((attempt === 1) !== (previousRunId === null)
      || typeof row.terminal !== "boolean" || typeof row.retryable !== "boolean"
      || row.terminal !== [
        "completed", "failed_retryable", "failed_terminal",
      ].includes(status)
      || row.retryable !== (status === "failed_retryable")) {
    throw new Error("MotionInstance attempt 状态无效");
  }
  return Object.freeze({
    runId: sha(row.run_id, "run_id"), status, stage,
    progress: Object.freeze({ current, total }), failureCode, attempt,
    previousRunId,
    eventCount: integer(row.event_count, "event count", 1, 1_000_000),
    headEventSha256: sha(row.head_event_sha256, "head event SHA-256"),
    terminal: row.terminal, retryable: row.retryable,
  });
}

function normalizeAuthority(value) {
  const row = exactObject(value, Object.keys(AUTHORITY), "authority");
  for (const [key, expected] of Object.entries(AUTHORITY)) {
    if (row[key] !== expected) throw new Error(`MotionInstance authority 越权：${key}`);
  }
  return Object.freeze({ ...row });
}

function exactObject(value, keys, label) {
  const row = object(value, label);
  if (Object.keys(row).sort().join("\0") !== [...keys].sort().join("\0")) {
    throw new Error(`${label} 字段无效`);
  }
  return row;
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
function boolean(value, label) {
  if (typeof value !== "boolean") throw new Error(`${label} 无效`);
  return value;
}
function stringList(value, label) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${label} 列表无效`);
  }
  return [...value];
}
function tokenList(value, label) {
  const result = stringList(value, label).map((item) => token(item, label));
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

export {
  AUTHORITY as MOTION_INSTANCE_V3_V2_AUTHORITY,
  INVENTORY,
  RELEASE_REASONS as MOTION_INSTANCE_V3_V2_RELEASE_REASONS,
};
