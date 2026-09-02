"use strict";

import { requireSha256 } from "./body-sway-review-address.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function reviewAdmissionV2Path(rawJobId) {
  const jobId = requireReviewJobId(rawJobId);
  return `/api/p10/runtime-capture/jobs/${jobId}/visual-review-v2/admission`;
}

export function reviewAdmissionV2Href(rawJobId) {
  const jobId = requireReviewJobId(rawJobId);
  return `./body-sway-review-admission-v2.html?job_id=${encodeURIComponent(jobId)}`;
}

export function normalizeReviewAdmissionV2(payload, expectedJobId) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("准入响应结构无效");
  }
  rejectPaths(payload);
  const jobId = requireReviewJobId(expectedJobId);
  const job = normalizeJob(payload.job, payload, jobId);
  const document = payload.document;
  if (payload.ok !== true || !document || typeof document !== "object"
      || Array.isArray(document)
      || document.format !== "autospine-body-sway-review-admission"
      || document.format_version !== 2
      || document.source?.job?.job_id !== jobId
      || (job.projectId && document.project_id !== job.projectId)
      || (job.clipId && document.clip_id !== job.clipId)) {
    throw new Error("准入响应没有包含可验证文档");
  }
  const admissionSha256 = requireSha256(
    payload.admission_sha256, "P10.4a v2 admission SHA-256",
  );
  const status = requireToken(
    payload.status ?? document.status, "P10.4a v2 status",
  );
  if (status !== "admitted_for_safety_analysis" || status !== document.status) {
    throw new Error("准入状态交叉接线");
  }
  const claims = document.claims ?? payload.claims;
  const releaseGate = document.release_gate ?? payload.release_gate;
  if ((payload.claims && JSON.stringify(payload.claims) !== JSON.stringify(claims))
      || (payload.release_gate
        && JSON.stringify(payload.release_gate) !== JSON.stringify(releaseGate))) {
    throw new Error("准入摘要与 canonical 文档不一致");
  }
  if (!claims || claims.sampled_visual_approved !== true
      || claims.head_observed_at_compile_time !== true
      || claims.release_authority !== false
      || claims.publishable_timeline !== false
      || releaseGate?.status !== "blocked"
      || !Array.isArray(releaseGate.reason_codes)) {
    throw new Error("准入文档越过了允许的证据边界");
  }
  const reasons = releaseGate.reason_codes.map((value) => (
    requireToken(value, "release blocker")
  ));
  const observation = document.head_observation
    ?? document.head_observations?.visual_review
    ?? document.visual_review_head_observation
    ?? {};
  const revision = finiteRevision(
    observation.revision ?? document.source?.visual_review_revision
      ?? payload.inputs?.visual_revision,
  );
  const decisionSha256 = optionalSha256(
    observation.head_decision_sha256
      ?? document.source?.visual_review_decision_sha256
      ?? payload.inputs?.visual_decision_sha256,
  );
  return Object.freeze({
    jobId, projectId: job.projectId, clipId: job.clipId,
    status, admissionSha256, document, claims,
    releaseReasons: Object.freeze(reasons), revision, decisionSha256,
  });
}

function normalizeJob(value, payload, expectedJobId) {
  const object = value && typeof value === "object" && !Array.isArray(value)
    ? value : {};
  const responseJobId = typeof value === "string"
    ? value : object.job_id ?? payload.job_id ?? expectedJobId;
  if (requireReviewJobId(responseJobId) !== expectedJobId) {
    throw new Error("准入响应与采集任务不一致");
  }
  return {
    projectId: optionalToken(
      object.project_id ?? payload.project_id ?? payload.document?.project_id,
    ),
    clipId: optionalToken(
      object.clip_id ?? payload.clip_id ?? payload.document?.clip_id,
    ),
  };
}

function finiteRevision(value) {
  return Number.isInteger(value) && value >= 1 && value <= 64 ? value : null;
}

function optionalSha256(value) {
  return value === undefined || value === null
    ? null : requireSha256(value, "visual decision SHA-256");
}

function optionalToken(value) {
  return value === undefined || value === null ? null : requireToken(value, "identity");
}

function requireToken(value, label) {
  if (!TOKEN.test(String(value ?? ""))) throw new Error(`${label} 无效`);
  return String(value);
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
