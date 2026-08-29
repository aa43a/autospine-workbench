"use strict";

import {
  requireSafeId, requireSha256,
} from "./seam-anchor-review-address.js";

export const SEAM_PUBLICATION_INTENT = "reviewed-seam-anchor-set-publication-v1";
export const SEAM_PUBLICATION_REQUEST_FORMAT =
  "autospine-seam-review-publication-request";
export const SEAM_PUBLICATION_RECEIPT_FORMAT =
  "autospine-reviewed-seam-anchor-set-receipt";
export const SEAM_REVIEW_READY_STATUS =
  "reviewed_anchor_set_ready_for_compile";

const BLOCKED_STATUS = "reviewed_anchor_set_blocked";
const READY_GATE_REASONS = Object.freeze([
  "dynamic_seam_safety_unproven",
  "reviewed_seam_anchor_set_missing",
  "runtime_equivalence_unproven",
  "visual_seam_quality_unproven",
]);
const BLOCKED_GATE_REASONS = Object.freeze([
  "dynamic_seam_safety_unproven",
  "reviewed_seam_anchor_selection_blocked",
  "reviewed_seam_anchor_set_missing",
  "runtime_equivalence_unproven",
  "visual_seam_quality_unproven",
]);
const PUBLICATION_GATE_REASONS = Object.freeze([
  "dynamic_seam_safety_unproven",
  "runtime_equivalence_unproven",
  "visual_seam_quality_unproven",
]);

function exactObject(value, fields, label) {
  const keys = value && typeof value === "object" && !Array.isArray(value)
    ? Object.keys(value).sort() : [];
  if (keys.join("\0") !== [...fields].sort().join("\0")) {
    throw new Error(`${label}字段无效`);
  }
  return value;
}

function requireInteger(value, minimum, maximum, label) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label} 无效`);
  }
  return value;
}

function requireGate(raw, expectedReasons, label) {
  exactObject(raw, ["status", "reason_codes"], label);
  if (raw.status !== "blocked" || !Array.isArray(raw.reason_codes)
      || raw.reason_codes.length !== expectedReasons.length
      || raw.reason_codes.some((reason, index) => reason !== expectedReasons[index])) {
    throw new Error(`${label}未保持 fail-closed`);
  }
  return Object.freeze({
    status: "blocked", reasonCodes: Object.freeze([...raw.reason_codes]),
  });
}

function normalizeDecisionSummary(raw, status) {
  exactObject(raw, [
    "relationship_count", "accept_count", "adjust_count", "reject_count",
    "unobservable_count", "anchor_pair_count",
  ], "P10.5b 摘要");
  const values = [
    raw.accept_count, raw.adjust_count, raw.reject_count,
    raw.unobservable_count, raw.anchor_pair_count,
  ];
  if (raw.relationship_count !== 6
      || values.some((value) => !Number.isInteger(value) || value < 0)
      || values.slice(0, 4).reduce((total, value) => total + value, 0) !== 6) {
    throw new Error("P10.5b 摘要计数无效");
  }
  const selected = raw.accept_count + raw.adjust_count;
  if (raw.anchor_pair_count < selected * 2 || raw.anchor_pair_count > selected * 8
      || status === SEAM_REVIEW_READY_STATUS && selected !== 6
      || status === BLOCKED_STATUS && selected === 6) {
    throw new Error("P10.5b 摘要与决定状态不一致");
  }
  return Object.freeze({
    relationshipCount: 6,
    acceptCount: raw.accept_count,
    adjustCount: raw.adjust_count,
    rejectCount: raw.reject_count,
    unobservableCount: raw.unobservable_count,
    anchorPairCount: raw.anchor_pair_count,
  });
}

export function normalizeSeamReviewDecisionReceipt(raw, expectedCandidateSha256 = null) {
  exactObject(raw, [
    "candidate_sha256", "decision_sha256", "revision", "status",
    "release_gate", "summary", "reused",
  ], "P10.5b 提交回执");
  const candidateSha256 = requireSha256(raw.candidate_sha256, "candidate SHA-256");
  const decisionSha256 = requireSha256(raw.decision_sha256, "decision SHA-256");
  const revision = requireInteger(raw.revision, 1, 64, "review revision");
  if (expectedCandidateSha256 !== null
      && candidateSha256 !== requireSha256(
        expectedCandidateSha256, "预期 candidate SHA-256",
      )) {
    throw new Error("P10.5b 回执与当前 candidate 不一致");
  }
  if (![SEAM_REVIEW_READY_STATUS, BLOCKED_STATUS].includes(raw.status)
      || typeof raw.reused !== "boolean") {
    throw new Error("P10.5b 提交状态无效");
  }
  const expectedReasons = raw.status === SEAM_REVIEW_READY_STATUS
    ? READY_GATE_REASONS : BLOCKED_GATE_REASONS;
  return Object.freeze({
    candidateSha256,
    decisionSha256,
    revision,
    status: raw.status,
    releaseGate: requireGate(raw.release_gate, expectedReasons, "P10.5b release gate"),
    summary: normalizeDecisionSummary(raw.summary, raw.status),
    reused: raw.reused,
  });
}

export function normalizeSeamPublicationRequest(raw, requestedPackageId = null) {
  exactObject(raw, [
    "format", "format_version", "intent", "package_id", "candidate_sha256",
    "review_revision", "decision_sha256",
  ], "P10.5c 发布请求");
  const packageId = requireSha256(raw.package_id, "Motion Policy package ID");
  if (requestedPackageId !== null
      && packageId !== requireSha256(requestedPackageId, "Motion Policy package ID")) {
    throw new Error("P10.5c 请求与 URL package 不一致");
  }
  if (raw.format !== SEAM_PUBLICATION_REQUEST_FORMAT || raw.format_version !== 1
      || raw.intent !== SEAM_PUBLICATION_INTENT) {
    throw new Error("P10.5c 发布请求版本无效");
  }
  return Object.freeze({
    format: raw.format,
    format_version: 1,
    intent: raw.intent,
    package_id: packageId,
    candidate_sha256: requireSha256(raw.candidate_sha256, "candidate SHA-256"),
    review_revision: requireInteger(raw.review_revision, 1, 64, "review revision"),
    decision_sha256: requireSha256(raw.decision_sha256, "decision SHA-256"),
  });
}

export function buildSeamPublicationRequest(packageId, decisionReceipt) {
  const decision = normalizeSeamReviewDecisionReceipt(decisionReceipt);
  if (decision.status !== SEAM_REVIEW_READY_STATUS) {
    throw new Error("blocked seam review 不可发布 P10.5c");
  }
  return normalizeSeamPublicationRequest({
    format: SEAM_PUBLICATION_REQUEST_FORMAT,
    format_version: 1,
    intent: SEAM_PUBLICATION_INTENT,
    package_id: requireSha256(packageId, "Motion Policy package ID"),
    candidate_sha256: decision.candidateSha256,
    review_revision: decision.revision,
    decision_sha256: decision.decisionSha256,
  });
}

export function normalizeSeamPublicationReceipt(raw, expectedRequest) {
  const expected = normalizeSeamPublicationRequest(expectedRequest);
  exactObject(raw, [
    "format", "format_version", "status", "package_id", "source", "address",
    "verification", "release_gate", "summary",
  ], "P10.5c 发布回执");
  if (raw.format !== SEAM_PUBLICATION_RECEIPT_FORMAT || raw.format_version !== 1
      || raw.status !== "passed" || raw.package_id !== expected.package_id) {
    throw new Error("P10.5c 发布回执版本或 package 无效");
  }
  exactObject(raw.source, [
    "project_id", "candidate_sha256", "review_revision", "decision_sha256",
  ], "P10.5c source");
  const projectId = requireSafeId(raw.source.project_id, "P10.5c project ID");
  if (raw.source.candidate_sha256 !== expected.candidate_sha256
      || raw.source.review_revision !== expected.review_revision
      || raw.source.decision_sha256 !== expected.decision_sha256) {
    throw new Error("P10.5c 回执与已提交 decision 不一致");
  }
  exactObject(raw.address, [
    "project_id", "reviewed_set_sha256", "bundle_sha256",
  ], "P10.5c address");
  if (raw.address.project_id !== projectId) {
    throw new Error("P10.5c address 与 source project 不一致");
  }
  const reviewedSetSha256 = requireSha256(
    raw.address.reviewed_set_sha256, "ReviewedSeamAnchorSet SHA-256",
  );
  const bundleSha256 = requireSha256(raw.address.bundle_sha256, "P10.5c bundle SHA-256");
  exactObject(raw.verification, [
    "status", "replayed_from_exact_upstreams", "head_observation",
  ], "P10.5c verification");
  exactObject(raw.verification.head_observation, [
    "method", "scope", "revision", "head_decision_sha256",
    "permanent_authority_claimed",
  ], "P10.5c head observation");
  const head = raw.verification.head_observation;
  if (raw.verification.status !== "passed"
      || raw.verification.replayed_from_exact_upstreams !== true
      || head.method !== "double_snapshot" || head.scope !== "compile_time"
      || head.revision !== expected.review_revision
      || head.head_decision_sha256 !== expected.decision_sha256
      || head.permanent_authority_claimed !== false) {
    throw new Error("P10.5c 回执未证明 current-head 精确复验");
  }
  exactObject(raw.summary, ["relationship_count", "anchor_pair_count"], "P10.5c 摘要");
  if (raw.summary.relationship_count !== 6
      || !Number.isInteger(raw.summary.anchor_pair_count)
      || raw.summary.anchor_pair_count < 12 || raw.summary.anchor_pair_count > 48) {
    throw new Error("P10.5c 摘要无效");
  }
  return Object.freeze({
    format: raw.format,
    formatVersion: 1,
    status: "passed",
    packageId: raw.package_id,
    source: Object.freeze({
      projectId, candidateSha256: expected.candidate_sha256,
      reviewRevision: expected.review_revision,
      decisionSha256: expected.decision_sha256,
    }),
    address: Object.freeze({ projectId, reviewedSetSha256, bundleSha256 }),
    verification: Object.freeze({
      status: "passed", replayedFromExactUpstreams: true,
      headObservation: Object.freeze({
        method: "double_snapshot", scope: "compile_time",
        revision: expected.review_revision,
        headDecisionSha256: expected.decision_sha256,
        permanentAuthorityClaimed: false,
      }),
    }),
    releaseGate: requireGate(
      raw.release_gate, PUBLICATION_GATE_REASONS, "P10.5c release gate",
    ),
    summary: Object.freeze({
      relationshipCount: 6, anchorPairCount: raw.summary.anchor_pair_count,
    }),
  });
}
