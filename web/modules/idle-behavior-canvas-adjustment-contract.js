"use strict";

import {
  digestValue, exactFields, sameJson,
} from "./body-sway-probe-contract-utils.js";
import {
  normalizeCanvasAdjustmentEnvelope,
} from "./body-sway-canvas-adjustment-contract.js";
import { normalizeIdleReviewEntry } from "./idle-behavior-review-contract.js";

export const IDLE_CANVAS_DRAFT_FORMAT =
  "autospine-idle-behavior-canvas-adjustment-draft-entry";

export function normalizeIdleCanvasAdjustmentDraft(value, expected) {
  exactFields(value, [
    "format", "format_version", "status", "entry", "canvas_adjustment", "proposal",
  ], "P10.1 画布调整草稿入口");
  if (value.format !== IDLE_CANVAS_DRAFT_FORMAT || value.format_version !== 1
      || value.status !== "unvalidated_draft") {
    throw new Error("P10.1 画布调整草稿入口合同无效");
  }
  const entry = normalizeIdleReviewEntry(value.entry, expected.packageId);
  const head = entry.history?.items?.at(-1);
  const feature = entry.candidate.features.find((row) => row.feature_id === "body_sway");
  if (!head || head.action !== "adjust" || head.probe_status !== "pending_probe") {
    throw new Error("P10.1 画布调整草稿缺少当前 adjust head");
  }
  const expectedInputs = {
    idle_behavior_candidates_sha256: entry.candidate_sha256,
    idle_behavior_decision_sha256: entry.history.head_decision_sha256,
    ...entry.package.source,
  };
  const canvasAdjustment = normalizeCanvasAdjustmentEnvelope(value.canvas_adjustment, {
    packageRow: entry.package,
    candidateSha: entry.candidate_sha256,
    sourceReview: {
      revision: entry.history.current_revision,
      decision_sha256: entry.history.head_decision_sha256,
      action: head.action, probe_status: head.probe_status,
    },
    expectedProbeInputs: expectedInputs,
  });
  digestValue(expected.canvasAdjustmentSha256, "请求的画布调整 SHA");
  if (canvasAdjustment.candidateSha256 !== expected.canvasAdjustmentSha256
      || !canvasAdjustment.proposal
      || !sameJson(value.proposal, canvasAdjustment.proposal)
      || !sameJson(canvasAdjustment.document.timing, entry.candidate.timing)
      || !sameJson(canvasAdjustment.document.reviewed_selection, {
        candidate_id: feature?.candidate_id, feature_id: "body_sway",
        action: head.action, probe_status: head.probe_status, parameters: head.parameters,
      })) {
    throw new Error("P10.1 画布调整草稿与当前 head 或请求身份不一致");
  }
  return { entry, canvasAdjustment, proposal: canvasAdjustment.proposal };
}
