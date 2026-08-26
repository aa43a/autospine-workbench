"use strict";

import { renderReviewCases } from "./body-sway-review-markup.js";
import { renderHistory } from "./body-sway-review-history.js";
import { deriveReviewSummary } from "./body-sway-review-state.js";

const IDS = [
  "addressForm", "projectId", "previewSha256", "bundleSha256", "artifactSha256",
  "loadCandidateBtn", "addressStatus", "reviewWorkspace", "candidateDigest",
  "reviewProgress", "derivedStatus", "releaseStatus", "releaseReasons", "reviewCases",
  "refreshHistoryBtn", "historyList", "useHeadBtn", "baselineStatus",
  "historySelectionStatus", "decisionDocument", "reviewerId", "reviewNotes",
  "submitReviewBtn", "submitStatus", "liveRegion",
];
const REVIEWER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function reviewElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少复核页面元素：${id}`);
    return [id, element];
  }));
}

export function addressValues(elements) {
  return {
    projectId: elements.projectId.value,
    previewSha256: elements.previewSha256.value,
    bundleSha256: elements.bundleSha256.value,
    artifactSha256: elements.artifactSha256.value,
  };
}

export function setStatus(element, message, tone = "neutral") {
  element.textContent = message;
  element.dataset.tone = tone;
}

export function setDraftControlsDisabled(elements, disabled) {
  elements.reviewCases.inert = disabled;
  elements.reviewerId.disabled = disabled;
  elements.reviewNotes.disabled = disabled;
}

export function resetReviewView(elements) {
  elements.reviewWorkspace.hidden = true;
  elements.reviewCases.replaceChildren();
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
  setStatus(elements.submitStatus, "完成全部 case 并显式选择基线后可提交。");
}

export function showCandidate(elements, state, api, address, focusCaseId = null) {
  elements.reviewWorkspace.hidden = false;
  elements.candidateDigest.textContent = state.candidateSha256;
  elements.candidateDigest.title = state.candidateSha256;
  renderReviewCases({
    container: elements.reviewCases,
    cases: state.candidate.cases,
    decisions: state.decisions,
    focusCaseId,
    imageUrl: (row) => api.imageUrl(
      address, state.candidateSha256, row.case_id, row.image.png_sha256,
    ),
  });
  updateReviewSummary(elements, state);
}

export function updateReviewSummary(elements, state) {
  const summary = deriveReviewSummary(state.candidate, state.decisions);
  const completed = summary.caseCount - summary.counts.pending;
  elements.reviewProgress.textContent = `${completed} / ${summary.caseCount}`;
  elements.derivedStatus.textContent = summary.status;
  elements.releaseStatus.textContent = summary.releaseGate.status;
  const items = summary.releaseGate.reasonCodes.map((reason) => {
    const item = document.createElement("li");
    item.textContent = reason;
    return item;
  });
  elements.releaseReasons.replaceChildren(...items);
  const canSubmit = completed === summary.caseCount && Boolean(state.baseline)
    && REVIEWER_PATTERN.test(state.reviewerId) && !state.stale;
  elements.submitReviewBtn.disabled = !canSubmit;
  return summary;
}

export function showHistory(elements, history) {
  renderHistory(document, elements.historyList, history);
  elements.useHeadBtn.disabled = false;
  const label = history.currentRevision
    ? `以当前 head（revision ${history.currentRevision}）为基线`
    : "以空历史（revision 0）为基线";
  elements.useHeadBtn.textContent = label;
  setStatus(elements.baselineStatus, "历史已读取；仍需显式选择基线。");
}

export function showBaseline(elements, baseline) {
  const digest = baseline.decisionSha256 || "null";
  setStatus(
    elements.baselineStatus,
    `已选择 base revision ${baseline.revision} / previous ${digest}`,
    "success",
  );
}

export function announce(elements, message) {
  elements.liveRegion.textContent = "";
  requestAnimationFrame(() => { elements.liveRegion.textContent = message; });
}
