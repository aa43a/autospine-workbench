"use strict";

const IDS = [
  "captureFramingPanel", "captureFramingBadge", "captureFramingMessage",
  "captureFramingCoverage", "captureFramingWitnesses", "captureFramingStatus",
  "acceptCaptureFraming", "rejectCaptureFraming", "unobservableCaptureFraming",
];

const DOMAIN_COPY = Object.freeze({
  setup: ["初始姿势", "角色未播放动作时的完整外观"],
  base: ["基础动作", "不叠加身体摆动时的完整动作"],
  combined: ["合成动作", "基础动作与身体摆动叠加后的完整动作"],
});

const SIDE_COPY = Object.freeze({
  left: "最左侧", right: "最右侧", top: "最上方", bottom: "最下方",
});

export function captureFramingElements(doc = globalThis.document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少自动取景元素：${id}`);
    return [id, element];
  }));
}

export function resetCaptureFramingView(elements) {
  elements.captureFramingPanel.hidden = true;
  elements.captureFramingCoverage.replaceChildren();
  elements.captureFramingWitnesses.replaceChildren();
  elements.captureFramingMessage.textContent = "—";
  elements.captureFramingStatus.textContent = "等待自动取景候选。";
  elements.captureFramingStatus.dataset.tone = "neutral";
  setCaptureFramingBusy(elements, true);
}

export function renderCaptureFraming(elements, entry) {
  resetCaptureFramingView(elements);
  const framing = entry.captureFraming;
  if (!framing) return;
  const document = elements.captureFramingCoverage.ownerDocument;
  elements.captureFramingPanel.hidden = false;
  elements.captureFramingMessage.textContent =
    "系统已把初始姿势、基础动作和合成动作放进同一个安全取景范围。你只需看责任点并决定是否采用。";
  elements.captureFramingCoverage.replaceChildren(...["setup", "base", "combined"]
    .map((kind) => coverageCard(document, kind, framing.document.coverage[kind])));
  elements.captureFramingWitnesses.replaceChildren(...Object.entries(
    framing.document.union_extrema_witnesses,
  ).slice(0, 4).map(([side, witness]) => witnessCard(
    document, side, witness, framing.document.timing.ticks_per_second,
  )));
  renderHistory(elements, framing.history);
  setCaptureFramingBusy(elements, false);
}

export function setCaptureFramingBusy(elements, busy) {
  for (const button of [
    elements.acceptCaptureFraming, elements.rejectCaptureFraming,
    elements.unobservableCaptureFraming,
  ]) button.disabled = busy;
  elements.captureFramingPanel.toggleAttribute("aria-busy", busy);
}

export function setCaptureFramingStatus(elements, message, tone = "neutral") {
  elements.captureFramingStatus.textContent = message;
  elements.captureFramingStatus.dataset.tone = tone;
}

function coverageCard(document, kind, covered) {
  const card = document.createElement("article");
  card.className = "capture-coverage-card";
  card.dataset.tone = covered ? "success" : "error";
  card.setAttribute("role", "listitem");
  const heading = document.createElement("h4");
  heading.textContent = DOMAIN_COPY[kind][0];
  const status = document.createElement("strong");
  status.textContent = covered ? "已覆盖" : "未完整覆盖";
  const detail = document.createElement("p");
  detail.textContent = DOMAIN_COPY[kind][1];
  card.append(heading, status, detail);
  return card;
}

function witnessCard(document, side, witness, ticksPerSecond) {
  const card = document.createElement("li");
  card.className = "capture-witness-card";
  const title = document.createElement("strong");
  title.textContent = SIDE_COPY[side] || side;
  const attachment = document.createElement("span");
  attachment.textContent = `责任附件：${witness.attachment_id}`;
  const timing = document.createElement("span");
  timing.textContent = witness.envelope_kind === "setup"
    ? "时刻：初始姿势"
    : `时刻：${formatSeconds(witness.tick, ticksPerSecond)}`;
  card.append(title, attachment, timing);
  return card;
}

function renderHistory(elements, history) {
  if (history.currentRevision === 0) {
    elements.captureFramingBadge.textContent = "等待确认";
    elements.captureFramingBadge.dataset.tone = "warning";
    setCaptureFramingStatus(elements,
      "自动建议尚未写入决定；采用、不采用和无法判断都必须经过确认弹窗。", "warning");
    return;
  }
  const approved = history.status === "ready_for_temporary_preview_v2";
  elements.captureFramingBadge.textContent = approved
    ? `已采用 · revision ${history.currentRevision}`
    : `已记录 · revision ${history.currentRevision}`;
  elements.captureFramingBadge.dataset.tone = approved ? "success" : "warning";
  setCaptureFramingStatus(elements, approved
    ? "该取景已获人工确认，可以交给临时 Runtime 预览阶段；接缝、视觉质量和发布门禁仍未通过。"
    : "该取景当前未获采用；可在查看责任点后创建新的决定 revision。",
  approved ? "success" : "warning");
}

function formatSeconds(tick, ticksPerSecond) {
  return `${(tick / ticksPerSecond).toFixed(2)} 秒`;
}
