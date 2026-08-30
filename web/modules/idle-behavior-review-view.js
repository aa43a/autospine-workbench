"use strict";

import { bodySwayFeature } from "./idle-behavior-review-model.js";

const IDS = [
  "autoEntryPanel", "projectSelect", "reloadProject", "autoLoadStatus",
  "reviewWorkspace", "projectTitle", "projectFacts", "featureList",
  "bodySwayForm", "bodySwayAvailability", "cycles", "cyclesValue",
  "lowerAmplitude", "lowerAmplitudeValue", "headAmplitude", "headAmplitudeValue",
  "phaseDelay", "phaseDelayValue", "explicitConfirmation", "confirmAdjust",
  "rejectBodySway", "unobservableBodySway", "decisionStatus",
  "previewImage", "previewSvg",
  "previewFallback", "playPreview", "timeline", "timeOutput",
  "candidateDigest", "historyList", "expertDocument", "receiptPanel",
  "receiptHeading", "receiptSummary", "liveRegion",
];

export function idleReviewElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少 P10 页面元素：${id}`);
    return [id, element];
  }));
}

export function renderIdleReviewEntry(elements, entry) {
  const feature = bodySwayFeature(entry);
  elements.reviewWorkspace.hidden = false;
  elements.projectTitle.textContent = `${entry.package.project_id} · ${entry.package.motion_id}`;
  elements.projectFacts.textContent = `片段 ${entry.package.clip_id} · 状态 ${entry.status}`;
  elements.candidateDigest.textContent = entry.candidate_sha256;
  renderFeatures(elements.featureList, entry.candidate.features);
  renderHistory(elements.historyList, entry.history);
  elements.expertDocument.textContent = JSON.stringify({
    package: entry.package,
    candidate_sha256: entry.candidate_sha256,
    candidate_id: feature?.candidate_id ?? null,
    history: entry.history,
  }, null, 2);
  const available = feature?.availability === "candidate";
  const head = entry.history?.items?.at(-1) ?? null;
  elements.bodySwayAvailability.textContent = available
    ? reviewedStatus(head)
    : `身体摆动目前${feature?.availability === "unsupported" ? "不受支持" : "不可观测"}。`;
  elements.bodySwayAvailability.dataset.tone = available ? "success" : "warning";
  setFormEnabled(elements, available);
  return available;
}

export function resetIdleReviewView(elements) {
  elements.reviewWorkspace.hidden = true;
  elements.receiptPanel.hidden = true;
  elements.explicitConfirmation.checked = false;
  elements.expertDocument.textContent = "—";
  elements.historyList.replaceChildren();
  setStatus(elements.decisionStatus, "等待自动加载候选。", "neutral");
}

export function controlValues(elements) {
  return {
    cycles: Number(elements.cycles.value),
    lowerAmplitude: Number(elements.lowerAmplitude.value),
    headAmplitude: Number(elements.headAmplitude.value),
    phaseDelay: Number(elements.phaseDelay.value),
  };
}

export function applyControlValues(elements, values) {
  for (const key of ["cycles", "lowerAmplitude", "headAmplitude", "phaseDelay"]) {
    elements[key].value = String(values[key]);
  }
  elements.cyclesValue.textContent = `${values.cycles} 次`;
  elements.lowerAmplitudeValue.textContent = `${values.lowerAmplitude.toFixed(1)}°`;
  elements.headAmplitudeValue.textContent = `${values.headAmplitude.toFixed(1)}°`;
  elements.phaseDelayValue.textContent = `${Math.round(values.phaseDelay * 100)}%`;
}

export function syncDecisionControls(elements, { available, busy = false }) {
  const confirmed = elements.explicitConfirmation.checked;
  elements.bodySwayForm.inert = busy;
  elements.confirmAdjust.disabled = busy || !available || !confirmed;
  elements.rejectBodySway.disabled = busy || !available || !confirmed;
  elements.unobservableBodySway.disabled = busy || !available || !confirmed;
}

export function setStatus(element, text, tone = "neutral") {
  element.textContent = text;
  element.dataset.tone = tone;
}

export function showIdleReviewReceipt(elements, receipt) {
  elements.receiptPanel.hidden = false;
  elements.receiptSummary.textContent =
    `P10.1 revision ${receipt.revision} 已保存；动作：${receipt.action}。下一步请运行结构探针。`;
  elements.liveRegion.textContent = `身体摆动决定 revision ${receipt.revision} 已保存`;
  elements.receiptHeading.focus({ preventScroll: true });
}

function setFormEnabled(elements, enabled) {
  for (const control of elements.bodySwayForm.querySelectorAll("input, button")) {
    control.disabled = !enabled;
  }
  elements.bodySwayForm.dataset.available = String(enabled);
}

function renderFeatures(container, features) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  for (const feature of features) {
    const item = doc.createElement("li");
    const name = doc.createElement("strong");
    const state = doc.createElement("span");
    name.textContent = featureName(feature.feature_id);
    state.textContent = feature.availability === "candidate" ? "可设置" : feature.availability;
    state.dataset.tone = feature.availability === "candidate" ? "success" : "muted";
    item.append(name, state);
    container.append(item);
  }
}

function renderHistory(container, history) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  if (history === null) {
    appendText(doc, container, "li", "历史暂不可用；提交已禁用。");
    return;
  }
  if (!history.items.length) {
    appendText(doc, container, "li", "尚无决定；本次将创建 revision 1。");
    return;
  }
  for (const row of history.items) {
    appendText(doc, container, "li", `revision ${row.revision} · ${row.action} · ${row.probe_status}`);
  }
}

function appendText(doc, parent, tag, text) {
  const child = doc.createElement(tag);
  child.textContent = text;
  parent.append(child);
  return child;
}

function featureName(value) {
  return ({ blink: "眨眼", body_sway: "身体摆动", hair_spring: "头发弹簧", mouth: "口型" })[value] || value;
}

function reviewedStatus(head) {
  if (head?.action === "adjust") {
    return `已载入 revision ${head.revision} 的人工参数；再次保存会创建新 revision。`;
  }
  if (head && ["reject", "unobservable"].includes(head.action)) {
    return `当前 revision ${head.revision} 为 ${head.action}；重新选择会创建新 revision。`;
  }
  return "已发现四段躯干链，可设置一个待探针的摆动草稿。";
}
