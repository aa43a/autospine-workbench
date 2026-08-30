"use strict";

import {
  renderSeamHistory, renderSeamRelationships,
} from "./seam-anchor-review-markup.js";
import { deriveSeamReviewSummary } from "./seam-anchor-review-state.js";

const IDS = [
  "entryBadge", "entryStatus", "entrySummary", "entryProject", "entryPackageId",
  "entryReviewRequired", "entryUnobservable", "entryBlockers", "entryBlockerList",
  "expertAddressDetails",
  "addressForm", "projectId", "layerManifestSha256", "p3RigSha256",
  "p3BundleSha256", "loadCandidateBtn", "addressStatus", "reviewWorkspace",
  "candidateDigest", "reviewProgress", "reviewProgressBar", "derivedStatus", "releaseStatus",
  "assistPanel", "assistStatus", "assistSummary", "applyAssistBtn", "undoAssistBtn",
  "releaseReasons", "reviewRelationships", "refreshHistoryBtn", "historyList",
  "useHeadBtn", "baselineStatus", "historySelectionStatus", "decisionDocument",
  "reviewerId", "reviewNotes", "submitReviewBtn", "submitStatus", "liveRegion",
  "publicationPanel", "publicationStatus", "publicationStage", "reviewedSetSha",
  "reviewedSetBundleSha", "retryPublicationBtn", "downloadPublicationBtn",
  "nextDynamicSeamLink",
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
  elements.assistSummary.textContent = "—";
  elements.applyAssistBtn.disabled = true;
  elements.undoAssistBtn.disabled = true;
  elements.reviewProgressBar.value = 0;
  elements.useHeadBtn.disabled = true;
  elements.loadCandidateBtn.disabled = false;
  elements.refreshHistoryBtn.disabled = false;
  elements.submitReviewBtn.disabled = true;
  setStatus(elements.baselineStatus, "尚未选择提交基线。");
  setStatus(elements.historySelectionStatus, "尚未选择历史 revision。");
  setStatus(elements.assistStatus, "正在等待候选证据。");
  setStatus(elements.submitStatus, "系统完成明确项后，请检查剩余候选。");
  resetSeamPublicationView(elements);
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
    setupCanvas: state.setupCanvas,
    reviewAssist: state.reviewAssist,
    focusRelationshipId, focusSelector,
  });
  updateSeamReviewSummary(elements, state);
}

export function updateSeamReviewSummary(elements, state) {
  const summary = deriveSeamReviewSummary(state.candidate, state.decisions);
  const completed = summary.relationshipCount - summary.counts.pending;
  elements.reviewProgress.textContent = `${completed} / ${summary.relationshipCount}`;
  elements.reviewProgressBar.max = Math.max(1, summary.relationshipCount);
  elements.reviewProgressBar.value = completed;
  elements.derivedStatus.textContent = summary.counts.pending
    ? `还需检查 ${summary.counts.pending} 项`
    : summary.status === "reviewed_anchor_set_ready_for_compile"
      ? "六项均可用" : "包含不可用接缝";
  elements.releaseStatus.textContent = summary.counts.pending
    ? "尚未完成"
    : summary.status === "reviewed_anchor_set_ready_for_compile"
      ? "可生成静态接缝集" : "需修复源图层";
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
  elements.submitReviewBtn.firstChild.textContent = summary.status
    === "reviewed_anchor_set_blocked"
    ? "确认并保存阻塞结论 " : "确认复核并生成静态接缝集 ";
  return summary;
}

export function showSeamAssist(elements, assist, automatic = false) {
  const rows = assist?.suggestions || [];
  const single = rows.filter((row) => row.disposition === "single_option").length;
  const compare = rows.filter((row) => row.disposition === "compare_options").length;
  const blocked = rows.filter((row) => row.disposition === "blocked_unobservable").length;
  elements.assistSummary.textContent = [
    `${single} 项唯一候选`, `${compare} 项需要图片比较`, `${blocked} 项源图不可观测`,
  ].join(" · ");
  setStatus(
    elements.assistStatus,
    automatic ? "已自动填入所有明确项；这只是可撤销草稿，最后一次确认前不会写入。"
      : "自动建议已就绪，不会在后台提交。",
    automatic ? "success" : "neutral",
  );
  elements.applyAssistBtn.disabled = rows.length === 0;
}

export function resetSeamPublicationView(elements) {
  elements.publicationPanel.hidden = true;
  elements.publicationPanel.dataset.status = "idle";
  elements.publicationStage.textContent = "—";
  elements.reviewedSetSha.textContent = "—";
  elements.reviewedSetBundleSha.textContent = "—";
  elements.retryPublicationBtn.hidden = true;
  elements.downloadPublicationBtn.disabled = true;
  elements.nextDynamicSeamLink.hidden = true;
  setStatus(elements.publicationStatus, "尚未生成。");
}

export function showSeamPublicationProgress(elements, stage, message) {
  elements.publicationPanel.hidden = false;
  elements.publicationPanel.dataset.status = "working";
  elements.publicationStage.textContent = stage;
  setStatus(elements.publicationStatus, message);
}

export function showSeamPublicationReceipt(elements, receipt) {
  elements.publicationPanel.hidden = false;
  elements.publicationPanel.dataset.status = "passed";
  elements.publicationStage.textContent = "P10.5c 已精确复验";
  elements.reviewedSetSha.textContent = receipt.address.reviewedSetSha256;
  elements.reviewedSetBundleSha.textContent = receipt.address.bundleSha256;
  elements.downloadPublicationBtn.disabled = false;
  elements.retryPublicationBtn.hidden = true;
  elements.nextDynamicSeamLink.href = `./idle-behavior-review.html?project_id=${
    encodeURIComponent(receipt.address.projectId)}`;
  elements.nextDynamicSeamLink.textContent = "继续同一项目：补齐身体摆动动作域";
  elements.nextDynamicSeamLink.hidden = false;
  setStatus(
    elements.publicationStatus,
    "静态接缝集已生成并精确复验；动态接缝仍需先补齐身体摆动动作域。",
    "success",
  );
}

export function showSeamPublicationFailure(elements, message, retryable = false) {
  elements.publicationPanel.hidden = false;
  elements.publicationPanel.dataset.status = "failed";
  elements.publicationStage.textContent = "P10.5b 已保存；P10.5c 未完成";
  elements.retryPublicationBtn.hidden = !retryable;
  setStatus(elements.publicationStatus, message, "error");
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

export function showSeamBaseline(elements, baseline, automatic = false) {
  setStatus(
    elements.baselineStatus,
    `${automatic ? "自动绑定" : "已选择"} base revision ${baseline.revision} / previous ${
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
