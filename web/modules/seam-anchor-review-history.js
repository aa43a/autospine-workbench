"use strict";

import { requireSha256 } from "./seam-anchor-review-address.js";

const STATUSES = new Set([
  "reviewed_anchor_set_ready_for_compile", "reviewed_anchor_set_blocked",
]);

export function normalizeSeamReviewHistory(payload, candidateSha256) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || payload.candidate_sha256 !== candidateSha256
      || !Number.isInteger(payload.current_revision) || payload.current_revision < 0
      || payload.current_revision > 64
      || !Array.isArray(payload.items)) {
    throw new Error("历史响应结构无效");
  }
  const head = payload.head_decision_sha256;
  if (head !== null) requireSha256(head, "head decision SHA-256");
  const rows = payload.items.map((row, index) => {
    if (!row || typeof row !== "object" || row.revision !== index + 1
        || !STATUSES.has(row.status)) {
      throw new Error("历史 revision 不连续或状态无效");
    }
    return {
      revision: row.revision,
      decisionSha256: requireSha256(row.decision_sha256, "decision SHA-256"),
      status: row.status,
    };
  });
  if (payload.current_revision !== rows.length
      || (rows.length ? rows.at(-1).decisionSha256 : null) !== head) {
    throw new Error("历史 head 与 revision 列表不一致");
  }
  return {
    currentRevision: payload.current_revision,
    headDecisionSha256: head,
    rows,
  };
}

export function normalizeSeamDecisionEnvelope(
  payload, candidateSha256, revision, decisionSha256,
) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || payload.candidate_sha256 !== candidateSha256
      || payload.decision_sha256 !== decisionSha256
      || payload.revision !== revision
      || payload.decision?.review?.revision !== revision) {
    throw new Error("历史 decision 与精确地址不一致");
  }
  requireSha256(payload.decision_sha256, "decision SHA-256");
  return payload.decision;
}

export function currentSeamHeadBaseline(history) {
  if (!history) throw new Error("请先加载历史");
  return Object.freeze({
    revision: history.currentRevision,
    decisionSha256: history.headDecisionSha256,
  });
}
