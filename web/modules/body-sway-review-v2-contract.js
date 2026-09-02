"use strict";

import { requireSha256 } from "./body-sway-review-address.js";
import {
  normalizeDecisionEnvelope, normalizeHistoryEnvelope,
} from "./body-sway-review-history.js";
import { normalizeRuntimeCaptureJob } from "./p10-runtime-capture-contract.js";

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const IMAGE_SESSION = /^[A-Za-z0-9_-]{43}$/;

export function requireReviewJobId(value) {
  return requireSha256(value, "capture job ID");
}

export function normalizeCompletedReviewJob(value, expectedJobId) {
  const job = normalizeRuntimeCaptureJob(
    value, requireReviewJobId(expectedJobId),
  );
  if (job.status !== "completed" || !job.addresses) {
    throw new Error("官方 Runtime 采集尚未完成");
  }
  return job;
}

export function reviewV2Paths(rawJobId) {
  const jobId = requireReviewJobId(rawJobId);
  const base = `/api/p10/runtime-capture/jobs/${jobId}/visual-review-v2`;
  const candidate = (digest) => `${base}/candidates/${requireSha256(
    digest, "candidate SHA-256",
  )}`;
  return Object.freeze({
    job: () => `/api/p10/runtime-capture/jobs/${jobId}`,
    candidate: () => `${base}/candidate`,
    history: (digest) => `${candidate(digest)}/history`,
    decision: (digest, revision, decisionSha256) => {
      if (!Number.isInteger(revision) || revision < 1 || revision > 64) {
        throw new Error("历史 revision 超出允许范围");
      }
      return `${candidate(digest)}/history/${revision}/${requireSha256(
        decisionSha256, "decision SHA-256",
      )}`;
    },
    submit: (digest) => `${candidate(digest)}/decisions`,
    image: (digest, caseId, pngSha256, imageSession = null) => {
      if (!TOKEN.test(String(caseId ?? ""))) throw new Error("case ID 无效");
      const path = `${candidate(digest)}/cases/${encodeURIComponent(caseId)}/image/${
        requireSha256(pngSha256, "PNG SHA-256")}`;
      if (imageSession === null) return path;
      if (!IMAGE_SESSION.test(String(imageSession ?? ""))) {
        throw new Error("图片读取会话无效");
      }
      return `${path}?session=${encodeURIComponent(imageSession)}`;
    },
  });
}

export function normalizeReviewCandidateV2(payload, job) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("候选响应结构无效");
  }
  const summary = payload.job;
  if (!summary || summary.job_id !== job.job_id
      || summary.package_id !== job.request.package_id
      || summary.project_id !== job.addresses.project
      || !TOKEN.test(String(summary.clip_id ?? ""))
      || !Number.isInteger(summary.case_count)) {
    throw new Error("候选与采集任务不一致");
  }
  const candidateSha256 = requireSha256(
    payload.candidate_sha256, "candidate SHA-256",
  );
  const imageSession = normalizeImageSession(payload.image_session);
  const candidate = payload.candidate;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)
      || candidate.format_version !== 2
      || candidate.project_id !== job.addresses.project
      || candidate.clip_id !== summary.clip_id
      || candidate.status !== "candidate_only"
      || candidate.source?.temporary_preview_v2_sha256 !== job.addresses.preview
      || candidate.source?.runtime_execution_bundle_sha256
        !== job.addresses.execution_bundle
      || candidate.source?.capture_artifact_set_sha256 !== job.addresses.artifact
      || candidate.release_gate?.status !== "blocked"
      || !Array.isArray(candidate.release_gate?.reason_codes)
      || !Array.isArray(candidate.cases)
      || candidate.cases.length !== summary.case_count
      || candidate.cases.length < 3 || candidate.cases.length > 55) {
    throw new Error("候选与官方 Runtime 证据不一致");
  }
  const seen = new Set();
  for (const row of candidate.cases) {
    if (!row || !TOKEN.test(String(row.case_id ?? ""))
        || seen.has(row.case_id)
        || !(row.animation === null || TOKEN.test(String(row.animation ?? "")))
        || !Number.isInteger(row.tick) || row.tick < 0
        || !Number.isFinite(row.time_seconds) || row.time_seconds < 0
        || !row.image || Object.hasOwn(row.image, "path")
        || !Number.isInteger(row.image.width) || row.image.width !== 640
        || !Number.isInteger(row.image.height) || row.image.height !== 640
        || !Number.isInteger(row.image.size_bytes) || row.image.size_bytes < 1) {
      throw new Error("候选包含无效采样帧");
    }
    seen.add(row.case_id);
    requireSha256(row.evidence_sha256, "evidence SHA-256");
    requireSha256(row.image.png_sha256, "PNG SHA-256");
  }
  rejectPaths(payload);
  return {
    candidateSha256, candidate, job: summary, imageSession,
    history: normalizeReviewHistoryV2(
      payload.history, job.job_id, candidateSha256,
    ),
  };
}

function normalizeImageSession(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.format_version !== 1
      || !IMAGE_SESSION.test(String(value.token ?? ""))
      || !Number.isInteger(value.expires_in_seconds)
      || value.expires_in_seconds < 1 || value.expires_in_seconds > 600
      || value.authority !== "read_only_snapshot") {
    throw new Error("图片读取会话无效");
  }
  return Object.freeze({
    token: value.token, expiresInSeconds: value.expires_in_seconds,
  });
}

export function normalizeReviewHistoryV2(payload, jobId, candidateSha256) {
  if (payload?.job_id !== jobId) throw new Error("历史与采集任务不一致");
  return normalizeHistoryEnvelope(payload, candidateSha256);
}

export function normalizeReviewDecisionV2(
  payload, jobId, candidateSha256, revision, decisionSha256,
) {
  if (payload?.job_id !== jobId) throw new Error("决定与采集任务不一致");
  return normalizeDecisionEnvelope(
    payload, candidateSha256, revision, decisionSha256,
  );
}

export function normalizeReviewSubmissionV2(
  payload, jobId, expectedCandidateSha256, baseline,
) {
  if (!payload || payload.job_id !== jobId
      || payload.candidate_sha256 !== expectedCandidateSha256
      || payload.revision !== baseline.revision + 1
      || !["sampled_visual_approved", "sampled_visual_rejected"]
        .includes(payload.status)) {
    throw new Error("提交响应与当前任务或 revision 不一致");
  }
  requireSha256(expectedCandidateSha256, "candidate SHA-256");
  requireSha256(payload.decision_sha256, "decision SHA-256");
  return payload;
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
