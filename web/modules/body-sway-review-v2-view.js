"use strict";

import { deriveReviewSummary } from "./body-sway-review-state.js";

const IDS = [
  "entryBadge", "jobFacts", "entryStatus", "reviewWorkspace",
  "reviewProgress", "derivedStatus", "releaseStatus", "releaseReasons",
  "timelineStage", "timelinePosition", "timelineLabel", "timelineTime",
  "previousTimeBtn", "nextTimeBtn", "frameCompare", "reviewTimeline",
  "timelineCoverage", "timelineMarkers", "exceptionCount", "exceptionList",
  "refreshHistoryBtn", "historyList",
  "useHeadBtn", "baselineStatus", "historySelectionStatus",
  "decisionSummary", "reviewerId", "reviewNotes", "submitReviewBtn",
  "submitStatus", "confirmDialog", "confirmSummary", "cancelSubmitBtn",
  "confirmSubmitBtn", "reviewAttestation", "liveRegion",
];

export function reviewV2Elements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const value = doc.getElementById(id);
    if (!value) throw new Error(`缺少复核页面元素：${id}`);
    return [id, value];
  }));
}

export function setStatus(element, message, tone = "neutral") {
  element.textContent = message;
  element.dataset.tone = tone;
}

export function renderJobFacts(elements, job, summary) {
  const rows = [
    ["项目", summary.project_id],
    ["动作", summary.clip_id],
    ["官方采样帧", `${summary.case_count} 帧`],
  ];
  const doc = elements.jobFacts.ownerDocument;
  const fragment = doc.createDocumentFragment();
  for (const [label, value] of rows) {
    const group = doc.createElement("div");
    const term = doc.createElement("dt");
    const detail = doc.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    group.append(term, detail);
    fragment.append(group);
  }
  elements.jobFacts.replaceChildren(fragment);
  elements.entryBadge.textContent = "已精确绑定";
  elements.entryBadge.dataset.tone = "success";
}

export function renderCandidate(elements) {
  elements.reviewWorkspace.hidden = false;
}

export function updateSummary(elements, state, coverage = {}) {
  const summary = deriveReviewSummary(state.candidate, state.decisions);
  const done = summary.caseCount - summary.counts.pending;
  elements.reviewProgress.textContent = `${done} / ${summary.caseCount}`;
  elements.derivedStatus.textContent = statusLabel(summary.status);
  elements.releaseStatus.textContent = "仍阻塞";
  const doc = elements.releaseReasons.ownerDocument;
  const reasons = state.candidate
    ? ["local_draft_not_submitted", ...summary.releaseGate.reasonCodes]
    : summary.releaseGate.reasonCodes;
  elements.releaseReasons.replaceChildren(...[...new Set(reasons)].map((reason) => {
    const item = doc.createElement("li");
    item.textContent = reasonLabel(reason);
    return item;
  }));
  const reviewerReady = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
    .test(state.reviewerId || "");
  elements.submitReviewBtn.disabled = summary.counts.pending > 0
    || !state.baseline || !reviewerReady || state.stale || !coverage.complete;
  return summary;
}

export function renderHistory(elements, history) {
  const doc = elements.historyList.ownerDocument;
  const rows = history.items.length ? history.items.map((row) => {
    const item = doc.createElement("li");
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.dataset.historyRevision = String(row.revision);
    button.dataset.historySha = row.decisionSha256;
    const title = doc.createElement("strong");
    const status = doc.createElement("span");
    title.textContent = `revision ${row.revision}`;
    status.textContent = row.status === "sampled_visual_approved" ? "采样帧通过" : "存在拒绝/不可观测";
    button.append(title, status);
    item.append(button);
    return item;
  }) : [emptyItem(doc, "尚无已提交 revision。")];
  elements.historyList.replaceChildren(...rows);
  elements.useHeadBtn.disabled = false;
}

export function renderDecisionSummary(elements, decision) {
  const summary = decision.summary;
  elements.decisionSummary.replaceChildren();
  const rows = [
    `revision ${decision.review.revision}`,
    `复核人：${decision.review.reviewer_id}`,
    `通过 ${summary.approve_count} / 拒绝 ${summary.reject_count} / 不可观测 ${summary.unobservable_count}`,
    `状态：${decision.status}`,
  ];
  for (const value of rows) {
    const line = elements.decisionSummary.ownerDocument.createElement("div");
    line.textContent = value;
    elements.decisionSummary.append(line);
  }
}

export function renderBaseline(elements, baseline) {
  setStatus(elements.baselineStatus,
    baseline.revision ? `已选择 current revision ${baseline.revision}。` : "已选择空历史作为初始基线。",
    "success");
}

export function setLocked(elements, locked) {
  elements.reviewerId.disabled = locked;
  elements.reviewNotes.disabled = locked;
  elements.refreshHistoryBtn.disabled = locked;
  elements.useHeadBtn.disabled = locked || !elements.historyList.children.length;
}

export function announce(elements, message) {
  elements.liveRegion.textContent = "";
  requestAnimationFrame(() => { elements.liveRegion.textContent = message; });
}

function emptyItem(doc, value) {
  const item = doc.createElement("li");
  item.className = "empty-state";
  item.textContent = value;
  return item;
}

function reasonLabel(value) {
  const labels = {
    continuous_time_safety_unproven: "连续时间安全尚未证明",
    preview_only_timeline: "时间线仍属于预览范围",
    reviewed_seam_anchors_missing: "接缝锚点门禁尚未闭合",
    safe_range_unproven: "安全参数范围尚未证明",
    manual_visual_review_required: "仍需完整人工看图",
    sampled_visual_review_rejected: "采样视觉复核存在拒绝",
    local_draft_not_submitted: "本页默认通过只是草稿；正式 authority 以 history revision 为准",
  };
  return labels[value] || value;
}

function statusLabel(value) {
  return {
    candidate_only: "仍有待补原因",
    sampled_visual_approved: "全部通过草稿",
    sampled_visual_rejected: "存在剔除项",
  }[value] || value;
}
