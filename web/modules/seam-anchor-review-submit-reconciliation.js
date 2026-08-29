"use strict";

import { SeamAnchorReviewApiError } from "./seam-anchor-review-api.js";
import { normalizeSeamReviewHistory } from "./seam-anchor-review-history.js";

function serverResponseError(error) {
  if (error instanceof SeamAnchorReviewApiError) return error;
  return error?.cause instanceof SeamAnchorReviewApiError ? error.cause : null;
}

export function isDefinitiveServerResponseFailure(error) {
  return serverResponseError(error) !== null;
}

function validBaseline(baseline) {
  return baseline && Number.isInteger(baseline.revision)
    && baseline.revision >= 0 && baseline.revision < 64
    && (baseline.revision === 0
      ? baseline.decisionSha256 === null
      : /^[0-9a-f]{64}$/.test(baseline.decisionSha256));
}

export function assessDefinitiveNoCommit({
  error, historyPayload, candidateSha256, baseline,
}) {
  if (!isDefinitiveServerResponseFailure(error)) return null;
  if (!validBaseline(baseline)) throw new Error("提交基线无法用于安全核对");
  const history = normalizeSeamReviewHistory(historyPayload, candidateSha256);
  return Object.freeze({
    status: history.currentRevision === baseline.revision
        && history.headDecisionSha256 === baseline.decisionSha256
      ? "not_committed" : "history_changed",
    history,
  });
}
