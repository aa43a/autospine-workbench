"use strict";

const IDS = [
  "canvasDraftPanel", "canvasDraftBadge", "canvasDraftMessage",
  "canvasDraftGain", "canvasDraftCurrent", "restoreCanvasParameters",
];

export function idleCanvasDraftElements(document = globalThis.document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = document.getElementById(id);
    if (!element) throw new Error(`缺少 P10.1 画布调整元素：${id}`);
    return [id, element];
  }));
}

export function resetIdleCanvasDraftView(elements) {
  elements.canvasDraftPanel.hidden = true;
  elements.restoreCanvasParameters.disabled = true;
  elements.canvasDraftGain.textContent = "—";
  elements.canvasDraftCurrent.textContent = "—";
}

export function renderIdleCanvasDraft(elements, draft, currentParameters) {
  resetIdleCanvasDraftView(elements);
  if (!draft) return;
  const proposal = draft.proposal;
  const percent = Math.round(
    proposal.gain.numerator / proposal.gain.denominator * 100,
  );
  elements.canvasDraftPanel.hidden = false;
  elements.canvasDraftBadge.textContent = "未验证草稿";
  elements.canvasDraftBadge.dataset.tone = "warning";
  elements.canvasDraftMessage.textContent =
    "已按 P10.2 的离散实测结果预填参数。它尚未获得安全范围、视觉质量或发布权。";
  elements.canvasDraftGain.textContent = `${percent}%（${proposal.gain.numerator}/${proposal.gain.denominator} 档）`;
  elements.canvasDraftCurrent.textContent = parameterComparison(
    currentParameters, proposal.parameters,
  );
  elements.restoreCanvasParameters.disabled = false;
}

export function markIdleCanvasDraftRestored(elements) {
  elements.canvasDraftBadge.textContent = "已恢复当前参数";
  elements.canvasDraftBadge.dataset.tone = "success";
  elements.canvasDraftMessage.textContent =
    "P10.2 建议已从编辑器移除；当前 revision 参数已恢复，尚未提交任何内容。";
  elements.restoreCanvasParameters.disabled = true;
}

function parameterComparison(current, proposed) {
  const list = (value) => value.per_bone_amplitude_deg
    .map((row) => `${shortBone(row.bone_id)} ${Number(row.value).toFixed(2)}°`).join("、");
  return `当前：${list(current)}；建议：${list(proposed)}`;
}

function shortBone(value) {
  return ({
    "pelvis-spine": "骨盆", "spine-chest": "腰胸",
    "chest-neck": "胸颈", "neck-head": "头颈",
  })[value] || value;
}
