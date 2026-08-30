"use strict";

import { CHECK_COPY, deriveProbeOutcome } from "./body-sway-probe-contract.js";

const IDS = [
  "autoEntryPanel", "projectSelect", "reloadProject", "autoLoadStatus",
  "probeWorkspace", "projectTitle", "projectFacts", "sourceBadge",
  "previewImage", "previewSvg", "previewFallback", "playPreview",
  "sampleTimeline", "sampleTime", "samplePosition", "probeResult",
  "outcomeBadge", "outcomeMessage", "probeStats", "checkCards",
  "releaseMessage", "returnToP10", "visualNext", "nextHint",
  "downloadReport", "expertDocument", "liveRegion",
];

export function probeElements(document = globalThis.document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = document.getElementById(id);
    if (!element) throw new Error(`缺少 P10.2 页面元素：${id}`);
    return [id, element];
  }));
}

export function resetProbeView(elements) {
  elements.probeWorkspace.hidden = true;
  elements.checkCards.replaceChildren();
  elements.probeStats.replaceChildren();
  elements.returnToP10.hidden = true;
  elements.visualNext.hidden = true;
  elements.downloadReport.disabled = true;
  elements.expertDocument.textContent = "—";
  setStatus(elements.nextHint, "等待结构检查。", "neutral");
}

export function renderProbeEntry(elements, entry) {
  const outcome = deriveProbeOutcome(entry);
  elements.probeWorkspace.hidden = false;
  elements.projectTitle.textContent = `${entry.package.project_id} · ${entry.package.motion_id}`;
  elements.projectFacts.textContent = sourceFacts(entry);
  renderSourceBadge(elements.sourceBadge, entry);
  renderOutcome(elements, entry, outcome);
  renderStats(elements.probeStats, entry);
  renderChecks(elements.checkCards, entry);
  renderNext(elements, entry, outcome);
  elements.expertDocument.textContent = JSON.stringify(entry.raw, null, 2);
  elements.downloadReport.disabled = !entry.result?.reportSha256;
  elements.probeResult.focus({ preventScroll: true });
  announce(elements, outcomeAnnouncement(outcome));
  return outcome;
}

export function setStatus(element, message, tone = "neutral") {
  element.textContent = message;
  element.dataset.tone = tone;
}

function renderSourceBadge(element, entry) {
  const revision = entry.sourceReview?.revision;
  element.textContent = revision ? `P10.1 revision ${revision}` : "尚无 P10.1 决定";
  element.dataset.tone = revision ? "success" : "warning";
}

function renderOutcome(elements, entry, outcome) {
  const upstream = entry.canvasAdjustment?.classification
    === "upstream_base_motion_canvas_overflow";
  const copy = upstream ? [
    "基础动作需要修复",
    "0% 身体摆动仍然越界；请检查画布、附件、骨绑定或上游动作，单纯降低摆动参数无效。",
    "error",
  ] : ({
    visual_required: ["结构检查完成", "自动结构项未发现阻断；下一步仍须进行 P10.3 Runtime 与视觉复核。", "success"],
    rejected: ["需要返回调整", "至少一项自动结构检查被拒绝。请返回 P10.1 降低或修改摆动参数后重试。", "error"],
    not_applicable: ["本项目不运行探针", "当前 P10.1 决定是不使用或不可观测，因此没有可检查的身体摆动参数。", "warning"],
    p10_1_required: ["需要先完成设置", "当前项目尚无可用于结构探针的 P10.1 人工参数。", "warning"],
    unavailable: ["暂时无法检查", "精确来源目前无法安全重放。请重新读取，或返回 P10.1 检查项目状态。", "error"],
  })[outcome.kind];
  elements.outcomeBadge.textContent = copy[0];
  elements.outcomeBadge.dataset.tone = copy[2];
  elements.outcomeMessage.textContent = copy[1];
  elements.releaseMessage.textContent = entry.result
    ? "结构检查只覆盖采样结构。接缝、官方 Runtime、视觉质量、安全范围和发布权仍保持阻塞。"
    : "没有结构探针结果；Runtime、视觉质量、安全范围和发布权仍保持阻塞。";
}

function renderStats(container, entry) {
  const document = container.ownerDocument;
  const checks = entry.result?.checks || [];
  const values = [
    ["采样姿势", entry.result?.summary?.schedule_sample_count ?? 0],
    ["自动通过", checks.filter((row) => row.status === "passed").length],
    ["需要调整", checks.filter((row) => row.status === "rejected").length],
    ["后续阶段", checks.filter((row) => row.status === "unobservable").length],
  ];
  container.replaceChildren(...values.map(([label, value]) => {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = String(value);
    group.append(term, detail);
    return group;
  }));
}

function renderChecks(container, entry) {
  const document = container.ownerDocument;
  const rows = entry.result?.checks || [];
  if (!rows.length) {
    const message = document.createElement("p");
    message.className = "lede";
    message.textContent = "当前没有结构检查结果。";
    container.replaceChildren(message);
    return;
  }
  container.replaceChildren(...rows.map((row) => checkCard(document, row)));
}

function checkCard(document, row) {
  const card = document.createElement("article");
  card.className = "check-card";
  card.dataset.tone = checkTone(row.status);
  const header = document.createElement("header");
  const title = document.createElement("h3");
  const status = document.createElement("span");
  title.textContent = CHECK_COPY[row.check_id][0];
  status.className = "check-status";
  status.textContent = checkStatus(row.status);
  header.append(title, status);
  const description = document.createElement("p");
  description.textContent = checkDescription(row);
  card.append(header, description);
  return card;
}

function checkDescription(row) {
  const base = CHECK_COPY[row.check_id][1];
  if (row.status === "rejected") {
    return `${base} 发现 ${row.failure_count} 个失败采样，请返回调整。`;
  }
  if (row.status === "passed") {
    return `${base} 已检查 ${row.sample_count} 个采样。`;
  }
  return base;
}

function renderNext(elements, entry, outcome) {
  const query = `?package_id=${encodeURIComponent(entry.package.package_id)}`;
  const upstream = entry.canvasAdjustment?.classification
    === "upstream_base_motion_canvas_overflow";
  elements.returnToP10.href = `./idle-behavior-review.html${query}`;
  elements.visualNext.href =
    "./document-viewer.html?doc=docs%2Fhow-to-capture-body-sway-runtime.md";
  elements.returnToP10.hidden = !outcome.shouldReturnToP10 || upstream;
  elements.visualNext.hidden = !outcome.canEnterVisual;
  setStatus(
    elements.nextHint,
    upstream
      ? "基础动作在 0% 摆动时仍越界；请使用上方绑定工作台入口，不能进入 P10.3。"
      : outcome.canEnterVisual
      ? "结构检查允许准备视觉阶段，但自动 Runtime capture 交接尚未交付；请按文档先生成精确证据。"
      : "返回 P10.1 只会创建新的人工 revision，不会改写现有历史。",
    outcome.canEnterVisual ? "success" : "warning",
  );
}

function sourceFacts(entry) {
  const base = `片段 ${entry.package.clip_id}`;
  return entry.sourceReview
    ? `${base} · P10.1 动作 ${entry.sourceReview.action} · ${entry.sourceReview.probe_status}`
    : `${base} · 尚无可用 P10.1 current head`;
}

function checkTone(status) {
  return status === "passed" ? "success" : status === "rejected" ? "error" : "warning";
}

function checkStatus(status) {
  return ({ passed: "已通过", rejected: "需调整", unobservable: "后续检查", not_applicable: "不适用" })[status];
}

function outcomeAnnouncement(outcome) {
  return outcome.canEnterVisual ? "P10.2 结构检查完成，可进入视觉阶段"
    : "P10.2 当前不能进入视觉阶段";
}

function announce(elements, message) {
  elements.liveRegion.textContent = "";
  globalThis.requestAnimationFrame?.(() => { elements.liveRegion.textContent = message; });
}
