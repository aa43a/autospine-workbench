"use strict";

import {
  renderSeamHistory, renderSeamRelationships,
} from "./seam-anchor-review-markup.js";
import { deriveSeamReviewSummary } from "./seam-anchor-review-state.js";

const IDS = [
  "addressForm", "projectId", "layerManifestSha256", "p3RigSha256",
  "p3BundleSha256", "loadCandidateBtn", "addressStatus", "reviewWorkspace",
  "candidateDigest", "reviewProgress", "derivedStatus", "releaseStatus",
  "releaseReasons", "reviewRelationships", "refreshHistoryBtn", "historyList",
  "useHeadBtn", "baselineStatus", "historySelectionStatus", "decisionDocument",
  "reviewerId", "reviewNotes", "submitReviewBtn", "submitStatus", "liveRegion",
];
const REVIEWER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function seamReviewElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少 seam 复核页面元素：${id}`);
    return [id, element];
  }));
}

export function seamAddressValues(elements) {
  return {
    projectId: elements.projectId.value,
    layerManifestSha256: elements.layerManifestSha256.value,
    p3RigSha256: elements.p3RigSha256.value,
    p3BundleSha256: elements.p3BundleSha256.value,
  };
}

export function setStatus(element, message, tone = "neutral") {
  element.textContent = message;
  element.dataset.tone = tone;
}

export function setSeamDraftDisabled(elements, disabled) {
  elements.reviewRelationships.inert = disabled;
  elements.reviewerId.disabled = disabled;
  elements.reviewNotes.disabled = disabled;
}

export function resetSeamReviewView(elements) {
  elements.reviewWorkspace.hidden = true;
  elements.reviewRelationships.replaceChildren();
  elements.historyList.replaceChildren();
  elements.decisionDocument.textContent = "—";
  elements.candidateDigest.textContent = "—";
  elements.reviewerId.value = "";
  elements.reviewNotes.value = "";
  elements.useHeadBtn.disabled = true;
  elements.loadCandidateBtn.disabled = false;
  elements.refreshHistoryBtn.disabled = false;
  elements.submitReviewBtn.disabled = true;
  setStatus(elements.baselineStatus, "尚未选择提交基线。");
  setStatus(elements.historySelectionStatus, "尚未选择历史 revision。");
  setStatus(elements.submitStatus, "完成六项判定并显式选择基线后可提交。");
}

export function showSeamCandidate(
  elements, state, focusRelationshipId = null, focusSelector = null,
) {
  elements.reviewWorkspace.hidden = false;
  elements.candidateDigest.textContent = state.candidateSha256;
  elements.candidateDigest.title = state.candidateSha256;
  renderSeamRelationships({
    container: elements.reviewRelationships,
    relationships: state.candidate.relationships,
    decisions: state.decisions,
    attachmentImages: state.attachmentImages,
    focusRelationshipId, focusSelector,
  });
  updateSeamReviewSummary(elements, state);
}

export function updateSeamReviewSummary(elements, state) {
  const summary = deriveSeamReviewSummary(state.candidate, state.decisions);
  const completed = summary.relationshipCount - summary.counts.pending;
  elements.reviewProgress.textContent = `${completed} / ${summary.relationshipCount}`;
  elements.derivedStatus.textContent = summary.status;
  elements.releaseStatus.textContent = summary.releaseGate.status;
  const doc = elements.releaseReasons.ownerDocument || document;
  const reasons = summary.releaseGate.reasonCodes.map((reason) => {
    const item = doc.createElement("li");
    item.textContent = reason;
    return item;
  });
  elements.releaseReasons.replaceChildren(...reasons);
  const canSubmit = completed === summary.relationshipCount && Boolean(state.baseline)
    && REVIEWER_PATTERN.test(state.reviewerId) && !state.stale;
  elements.submitReviewBtn.disabled = !canSubmit;
  return summary;
}

export function updateAnchorValidity(elements, relationshipId, message) {
  const textarea = [...elements.reviewRelationships.querySelectorAll(
    "textarea[data-anchor-json]",
  )].find((item) => item.dataset.anchorJson === relationshipId);
  if (!textarea) return;
  textarea.setAttribute("aria-invalid", message ? "true" : "false");
  const error = textarea.parentElement?.querySelector(".field-error");
  if (error) error.textContent = message || "";
}

export function showSeamHistory(elements, history) {
  const doc = elements.historyList.ownerDocument || document;
  renderSeamHistory(doc, elements.historyList, history);
  elements.useHeadBtn.disabled = false;
  elements.useHeadBtn.textContent = history.currentRevision
    ? `以当前 head（revision ${history.currentRevision}）为基线`
    : "以空历史（revision 0）为基线";
  setStatus(elements.baselineStatus, "历史已读取；仍需显式选择基线。");
}

export function showSeamBaseline(elements, baseline) {
  setStatus(
    elements.baselineStatus,
    `已选择 base revision ${baseline.revision} / previous ${
      baseline.decisionSha256 || "null"}`,
    "success",
  );
}

export function renderDecisionDocument(element, payload) {
  element.textContent = JSON.stringify(payload, null, 2);
}

export function announce(elements, message) {
  elements.liveRegion.textContent = "";
  requestAnimationFrame(() => { elements.liveRegion.textContent = message; });
}
