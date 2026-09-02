"use strict";

import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const SHA256 = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/;
const STATUSES = new Set([
  "queued", "running", "completed", "failed_retryable", "failed_terminal",
]);
const ENTRY_STATUSES = new Set(["ready", ...STATUSES]);
const STAGES = new Set([
  "queued", "exact_motion_instance", "source_adapter", "spine_adapter",
  "publication", "parent_exact_readback", "completed", "failed",
]);
const INVENTORY = Object.freeze([
  "skeleton.json", "skeleton.atlas", "skeleton.png",
  "run-manifest.json", "export-report.json",
]);
const AUTHORITY = Object.freeze({
  spine_adapter_emitted: true,
  attachment_area_overlap_assessed: false,
  dynamic_seam_safety: false,
  full_attachment_boundary_continuity: false,
  official_runtime_loaded: false,
  runtime_equivalence: false,
  raster_visual_quality: false,
  persistent_current_head_authority: false,
  publishable_spine_timeline: false,
  release_authority: false,
});
const RELEASE_REASONS = Object.freeze([
  "attachment_area_overlap_not_assessed",
  "dynamic_seam_safety_unproven",
  "full_attachment_boundary_continuity_unproven",
  "official_runtime_not_loaded",
  "persistent_current_head_authority_not_granted",
  "publishable_spine_timeline_not_granted",
  "raster_visual_quality_unproven",
  "release_authority_not_granted",
  "runtime_equivalence_unproven",
]);

export function spine42V3V2Path(job, safety, dynamic, motion) {
  return motionRunPath(job, safety, dynamic, motion) + "/spine42-v3-v2";
}

export function spine42V3V2RunsPath(job, safety, dynamic, motion) {
  return spine42V3V2Path(job, safety, dynamic, motion) + "/runs";
}

export function spine42V3V2RunPath(job, safety, dynamic, motion, run) {
  return spine42V3V2RunsPath(job, safety, dynamic, motion)
    + `/${sha(run, "run_id")}`;
}

export function spine42V3V2ResultPath(job, safety, dynamic, motion, run) {
  return spine42V3V2RunPath(job, safety, dynamic, motion, run) + "/result";
}

export function spine42V3V2Href(job, safety, dynamic, motion) {
  const ids = exactIds(job, safety, dynamic, motion);
  return `./spine42-v3-v2.html?job_id=${encodeURIComponent(ids.jobId)}`
    + `&safety_run_id=${encodeURIComponent(ids.safetyRunId)}`
    + `&dynamic_run_id=${encodeURIComponent(ids.dynamicRunId)}`
    + `&motion_run_id=${encodeURIComponent(ids.motionRunId)}`;
}

export function normalizeSpine42V3V2Entry(
  payload, job, safety, dynamic, motion,
) {
  object(payload, "Spine adapter 状态");
  rejectPaths(payload);
  const ids = exactIds(job, safety, dynamic, motion);
  if (payload.ok !== true || !ENTRY_STATUSES.has(payload.status)
      || requireReviewJobId(payload.job_id) !== ids.jobId
      || sha(payload.safety_run_id, "safety_run_id") !== ids.safetyRunId
      || sha(payload.dynamic_run_id, "dynamic_run_id") !== ids.dynamicRunId
      || sha(payload.motion_run_id, "motion_run_id") !== ids.motionRunId) {
    throw new Error("Spine adapter 状态与精确来源不一致");
  }
  const run = payload.run == null ? null : normalizeRun(payload.run);
  if ((payload.status === "ready") !== (run === null)
      || (run && run.status !== payload.status)) {
    throw new Error("Spine adapter entry 与 run 交叉接线");
  }
  return Object.freeze({ ok: true, status: payload.status, ...ids, run });
}

export function normalizeSpine42V3V2Result(
  payload, job, safety, dynamic, motion, expectedRun,
) {
  object(payload, "Spine adapter 结果");
  rejectPaths(payload);
  const entry = normalizeSpine42V3V2Entry(
    payload, job, safety, dynamic, motion,
  );
  if (entry.status !== "completed" || !entry.run
      || entry.run.runId !== sha(expectedRun, "run_id")) {
    throw new Error("Spine adapter completed run 无效");
  }
  const address = exactObject(payload.address, [
    "skeleton_json_sha256", "bundle_sha256",
  ], "Spine adapter address");
  const inventory = stringList(payload.inventory, "inventory");
  if (inventory.join("\0") !== INVENTORY.join("\0")) {
    throw new Error("Spine adapter 五文件 inventory 无效");
  }
  const authority = normalizeAuthority(payload.authority);
  const release = exactObject(
    payload.release_gate, ["status", "reason_codes"], "release gate",
  );
  const reasons = tokenList(release.reason_codes, "release reason");
  const verification = exactObject(
    payload.verification, ["status", "exact_readback"], "verification",
  );
  if (release.status !== "blocked"
      || reasons.join("\0") !== RELEASE_REASONS.join("\0")
      || verification.status !== "passed"
      || verification.exact_readback !== true) {
    throw new Error("Spine adapter 精确读回或发布门禁无效");
  }
  return Object.freeze({
    ok: true, status: "completed", ...entry,
    projectId: token(payload.project_id, "project_id"),
    clipId: token(payload.clip_id, "clip_id"),
    address: Object.freeze({
      skeletonJsonSha256: sha(
        address.skeleton_json_sha256, "skeleton JSON SHA-256",
      ),
      bundleSha256: sha(address.bundle_sha256, "bundle SHA-256"),
    }),
    inventory: Object.freeze(inventory), authority,
    releaseGate: Object.freeze({ status: "blocked", reasonCodes: reasons }),
    verification: Object.freeze({ status: "passed", exactReadback: true }),
    reused: boolean(payload.reused, "reused"),
  });
}

function motionRunPath(job, safety, dynamic, motion) {
  const ids = exactIds(job, safety, dynamic, motion);
  return `/api/p10/runtime-capture/jobs/${ids.jobId}/visual-review-v2/`
    + `safety-analysis-v2/runs/${ids.safetyRunId}/dynamic-seam-v2/`
    + `runs/${ids.dynamicRunId}/motion-instance-v3-v2/runs/`
    + ids.motionRunId;
}

function exactIds(job, safety, dynamic, motion) {
  return Object.freeze({
    jobId: requireReviewJobId(job),
    safetyRunId: sha(safety, "safety_run_id"),
    dynamicRunId: sha(dynamic, "dynamic_run_id"),
    motionRunId: sha(motion, "motion_run_id"),
  });
}

function normalizeRun(row) {
  object(row, "run");
  const status = oneOf(row.status, STATUSES, "run status");
  const stage = oneOf(row.stage, STAGES, "run stage");
  const valid = status === "queued" ? stage === "queued"
    : status === "running" ? !["queued", "completed", "failed"].includes(stage)
      : status === "completed" ? stage === "completed" : stage === "failed";
  if (!valid) throw new Error("Spine adapter run stage 无效");
  const progress = object(row.progress, "progress");
  const total = integer(progress.total, "progress total", 1, 100);
  const current = integer(progress.current, "progress current", 0, total);
  const failureCode = row.failure_code == null
    ? null : token(row.failure_code, "failure code");
  const attempt = integer(row.attempt, "attempt", 1, 10_000);
  const previousRunId = row.previous_run_id == null
    ? null : sha(row.previous_run_id, "previous_run_id");
  if (status.startsWith("failed_") !== (failureCode !== null)
      || (attempt === 1) !== (previousRunId === null)
      || row.terminal !== [
        "completed", "failed_retryable", "failed_terminal",
      ].includes(status)
      || row.retryable !== (status === "failed_retryable")) {
    throw new Error("Spine adapter attempt 状态无效");
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
    if (row[key] !== expected) throw new Error(`Spine adapter authority 越权：${key}`);
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
  AUTHORITY as SPINE42_V3_V2_AUTHORITY,
  INVENTORY as SPINE42_V3_V2_INVENTORY,
  RELEASE_REASONS as SPINE42_V3_V2_RELEASE_REASONS,
};
