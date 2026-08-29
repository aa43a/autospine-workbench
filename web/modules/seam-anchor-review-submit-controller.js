"use strict";

import { requireSafeId, requireSha256 } from "./seam-anchor-review-address.js";
import {
  SEAM_REVIEW_READY_STATUS, buildSeamPublicationRequest,
  normalizeSeamReviewDecisionReceipt,
} from "./seam-anchor-review-publication.js";

export class SeamReviewSubmitControllerError extends Error {
  constructor(message, code, cause = null) {
    super(message, cause === null ? undefined : { cause });
    this.name = "SeamReviewSubmitControllerError";
    this.code = code;
  }
}

function initialState() {
  return Object.freeze({
    phase: "idle",
    busy: false,
    decisionCommitted: false,
    retryPublication: false,
    packageId: null,
    candidateSha256: null,
    decision: null,
    publication: null,
    failure: null,
  });
}

function exactObject(value, fields) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join("\0") === [...fields].sort().join("\0");
}

function optionalPackageId(value) {
  return value === null || value === undefined
    ? null : requireSha256(value, "Motion Policy package ID");
}

function fixedFailure(stage, code) {
  return Object.freeze({ stage, code });
}

function controllerError(message, code, cause = null) {
  return new SeamReviewSubmitControllerError(message, code, cause);
}

function requirePublicationResult(value, request) {
  const expectedReasons = [
    "dynamic_seam_safety_unproven",
    "runtime_equivalence_unproven",
    "visual_seam_quality_unproven",
  ];
  if (!exactObject(value, [
    "format", "formatVersion", "status", "packageId", "source", "address",
    "verification", "releaseGate", "summary",
  ]) || value.format !== "autospine-reviewed-seam-anchor-set-receipt"
      || value.formatVersion !== 1 || value.status !== "passed"
      || value.packageId !== request.package_id
      || !exactObject(value.source, [
        "projectId", "candidateSha256", "reviewRevision", "decisionSha256",
      ])
      || value.source.candidateSha256 !== request.candidate_sha256
      || value.source.reviewRevision !== request.review_revision
      || value.source.decisionSha256 !== request.decision_sha256
      || !exactObject(value.address, ["projectId", "reviewedSetSha256", "bundleSha256"])
      || value.address.projectId !== value.source.projectId
      || !exactObject(value.verification, [
        "status", "replayedFromExactUpstreams", "headObservation",
      ])
      || value.verification.status !== "passed"
      || value.verification.replayedFromExactUpstreams !== true
      || !exactObject(value.verification.headObservation, [
        "method", "scope", "revision", "headDecisionSha256",
        "permanentAuthorityClaimed",
      ])
      || value.verification.headObservation.method !== "double_snapshot"
      || value.verification.headObservation.scope !== "compile_time"
      || value.verification.headObservation.revision !== request.review_revision
      || value.verification.headObservation.headDecisionSha256 !== request.decision_sha256
      || value.verification.headObservation.permanentAuthorityClaimed !== false
      || !exactObject(value.releaseGate, ["status", "reasonCodes"])
      || value.releaseGate.status !== "blocked"
      || !Array.isArray(value.releaseGate.reasonCodes)
      || value.releaseGate.reasonCodes.length !== expectedReasons.length
      || value.releaseGate.reasonCodes.some(
        (reason, index) => reason !== expectedReasons[index],
      )
      || !exactObject(value.summary, ["relationshipCount", "anchorPairCount"])
      || value.summary.relationshipCount !== 6
      || !Number.isInteger(value.summary.anchorPairCount)
      || value.summary.anchorPairCount < 12 || value.summary.anchorPairCount > 48) {
    throw controllerError("P10.5c 发布回执合同无效", "publication_receipt_invalid");
  }
  requireSafeId(value.source.projectId, "P10.5c project ID");
  requireSha256(value.address.reviewedSetSha256, "ReviewedSeamAnchorSet SHA-256");
  requireSha256(value.address.bundleSha256, "P10.5c bundle SHA-256");
  return value;
}

export function createSeamReviewSubmitController({
  api, onChange = () => {}, validateDecision = () => {},
} = {}) {
  if (!api || typeof api.submit !== "function" || typeof api.publish !== "function") {
    throw new TypeError("Seam review API with submit and publish is required");
  }
  if (typeof onChange !== "function") throw new TypeError("onChange must be a function");
  if (typeof validateDecision !== "function") {
    throw new TypeError("validateDecision must be a function");
  }
  let state = initialState();
  let publicationRequest = null;
  let decisionLocked = false;

  function transition(patch) {
    state = Object.freeze({ ...state, ...patch });
    onChange(state);
    return state;
  }

  function requireIdle() {
    if (state.busy) {
      throw controllerError("Seam review 提交正在进行", "submission_busy");
    }
  }

  async function publishPending() {
    requireIdle();
    if (publicationRequest === null) {
      throw controllerError("没有可仅重试的 P10.5c 发布", "publication_retry_unavailable");
    }
    transition({ phase: "publishing", busy: true, failure: null });
    try {
      const published = requirePublicationResult(
        await api.publish(publicationRequest.package_id, publicationRequest),
        publicationRequest,
      );
      publicationRequest = null;
      return transition({
        phase: "complete", busy: false, retryPublication: false,
        publication: published, failure: null,
      });
    } catch (error) {
      transition({
        phase: "publication_retry_required", busy: false,
        retryPublication: true,
        failure: fixedFailure("publication", "publication_failed"),
      });
      if (error instanceof SeamReviewSubmitControllerError) throw error;
      throw controllerError(
        "P10.5b 已提交；P10.5c 发布失败，只能重试发布",
        "publication_failed",
      );
    }
  }

  async function submit({ address, candidateSha256, payload, packageId = null } = {}) {
    requireIdle();
    const candidate = requireSha256(candidateSha256, "candidate SHA-256");
    const requestedPackage = optionalPackageId(packageId);
    if (publicationRequest !== null) {
      if (candidate !== publicationRequest.candidate_sha256
          || requestedPackage !== publicationRequest.package_id) {
        throw controllerError(
          "待重试 publication 与当前输入身份不一致",
          "publication_retry_identity_mismatch",
        );
      }
      return publishPending();
    }
    if (decisionLocked) {
      if (candidate !== state.candidateSha256 || requestedPackage !== state.packageId) {
        throw controllerError("已提交 decision 与当前输入身份不一致", "decision_identity_mismatch");
      }
      return state;
    }
    decisionLocked = true;
    transition({
      phase: "submitting_decision", busy: true, packageId: requestedPackage,
      candidateSha256: candidate, failure: null,
    });
    let rawDecision;
    try {
      rawDecision = await api.submit(address, candidate, payload);
    } catch (error) {
      transition({
        phase: "decision_uncertain", busy: false,
        failure: fixedFailure("decision", "decision_request_failed"),
      });
      throw controllerError(
        "P10.5b 提交结果不确定；请刷新历史后再操作",
        "decision_request_failed",
        error,
      );
    }
    let decision;
    try {
      decision = normalizeSeamReviewDecisionReceipt(rawDecision, candidate);
      validateDecision(rawDecision, decision);
    } catch {
      transition({
        phase: "decision_receipt_invalid", busy: false, decisionCommitted: true,
        failure: fixedFailure("decision", "decision_receipt_invalid"),
      });
      throw controllerError(
        "P10.5b 已响应但回执无效；请刷新历史，不能重复提交",
        "decision_receipt_invalid",
      );
    }
    transition({ decisionCommitted: true, decision });
    if (decision.status !== SEAM_REVIEW_READY_STATUS) {
      return transition({ phase: "decision_blocked", busy: false });
    }
    if (requestedPackage === null) {
      return transition({ phase: "decision_ready_without_package", busy: false });
    }
    try {
      publicationRequest = buildSeamPublicationRequest(requestedPackage, rawDecision);
    } catch {
      return transition({
        phase: "decision_receipt_invalid", busy: false,
        failure: fixedFailure("decision", "publication_request_invalid"),
      });
    }
    transition({ busy: false, retryPublication: true });
    return publishPending();
  }

  function allowDecisionRetryAfterVerifiedNoCommit({
    candidateSha256, packageId = null,
  } = {}) {
    requireIdle();
    const candidate = requireSha256(candidateSha256, "candidate SHA-256");
    const requestedPackage = optionalPackageId(packageId);
    if (!decisionLocked || state.decisionCommitted
        || state.phase !== "decision_uncertain" || publicationRequest !== null) {
      throw controllerError(
        "当前提交状态不能按未写入结果恢复", "decision_retry_not_allowed",
      );
    }
    if (candidate !== state.candidateSha256 || requestedPackage !== state.packageId) {
      throw controllerError(
        "历史核对身份与待恢复提交不一致", "decision_retry_identity_mismatch",
      );
    }
    decisionLocked = false;
    return transition({
      phase: "decision_retry_available", failure: null,
      decision: null, decisionCommitted: false,
    });
  }

  function reset() {
    requireIdle();
    publicationRequest = null;
    decisionLocked = false;
    state = initialState();
    onChange(state);
    return state;
  }

  return Object.freeze({
    allowDecisionRetryAfterVerifiedNoCommit,
    submit,
    retryPublication: publishPending,
    reset,
    snapshot: () => state,
  });
}

export const createSeamAnchorReviewSubmitController = createSeamReviewSubmitController;
