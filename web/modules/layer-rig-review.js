"use strict";

const ROLE_TOKEN = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;
const SIDES = new Set(["left", "right", "center", "bilateral", "unknown"]);
const BILATERAL_SPLIT_DISPOSITIONS = new Set(["split", "split_left_right"]);


export function semanticColor(role) {
  const text = String(role || "unknown");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  }
  const palette = ["#65c7ff", "#a998ff", "#54d89a", "#f0b85d", "#ff8ca0", "#57d5cc", "#7aa7ff"];
  return palette[Math.abs(hash) % palette.length];
}


export function renderLayerRigReview(elements, layer, bones, canvas) {
  const [x, y] = validPoint(layer?.pivot_xy) ? layer.pivot_xy.map(Number) : [0, 0];
  setNumberField(elements.layerPivotXInput, x, canvas?.width);
  setNumberField(elements.layerPivotYInput, y, canvas?.height);

  const selected = String(layer?.candidate_bone ?? "");
  const owner = elements.candidateBoneSelect.ownerDocument;
  const placeholder = owner.createElement("option");
  placeholder.value = "";
  placeholder.textContent = isBilateralSplit(layer?.disposition, layer?.side)
    ? "拆分后分配目标骨（可留空）"
    : "选择目标骨…";
  const options = [placeholder];
  for (const bone of Array.isArray(bones) ? bones : []) {
    const id = String(bone?.id ?? "");
    if (!id) continue;
    const option = owner.createElement("option");
    option.value = id;
    option.textContent = id;
    options.push(option);
  }
  elements.candidateBoneSelect.replaceChildren(...options);
  elements.candidateBoneSelect.value = selected;
}


export function readLayerRigReview(elements, canvas, boneIds, disposition = "keep") {
  const role = elements.semanticRoleInput.value.trim();
  const side = elements.semanticSideSelect.value;
  const x = Number(elements.layerPivotXInput.value);
  const y = Number(elements.layerPivotYInput.value);
  const candidateBone = elements.candidateBoneSelect.value.trim();
  const candidateBoneOptional = isBilateralSplit(disposition, side) && !candidateBone;
  const issues = {
    semanticRoleInput: ROLE_TOKEN.test(role) ? "" : "请输入有效的语义 token",
    semanticSideSelect: SIDES.has(side) ? "" : "请选择角色侧别",
    layerPivotXInput: coordinateIssue(x, canvas?.width),
    layerPivotYInput: coordinateIssue(y, canvas?.height),
    candidateBoneSelect: candidateBoneOptional || boneIds.has(candidateBone) ? "" : "请选择现有目标骨",
  };
  let valid = true;
  for (const [id, message] of Object.entries(issues)) {
    elements[id].setCustomValidity(message);
    if (message) valid = false;
  }
  if (!valid) {
    Object.keys(issues).map((id) => elements[id]).find((field) => !field.checkValidity())?.reportValidity();
    return null;
  }
  const patch = {
    canonical_role: role,
    side,
    pivot_xy: [x, y],
  };
  if (candidateBone) patch.candidate_bone = candidateBone;
  return patch;
}


export function applyLayerRigReviewPatch(override, patch) {
  if (!Object.hasOwn(patch, "candidate_bone")) delete override.candidate_bone;
  return Object.assign(override, patch);
}


function setNumberField(field, value, maximum) {
  field.value = String(Math.round(Number(value) * 10) / 10);
  field.min = "0";
  field.max = String(Math.max(0, Number(maximum) || 0));
}


function coordinateIssue(value, maximum) {
  if (!Number.isFinite(value)) return "请输入有限坐标";
  if (value < 0 || value > Number(maximum)) return "坐标必须位于画布内";
  return "";
}


function validPoint(value) {
  return Array.isArray(value) && value.length === 2 && value.every((item) => Number.isFinite(Number(item)));
}


function isBilateralSplit(disposition, side) {
  return side === "bilateral" && BILATERAL_SPLIT_DISPOSITIONS.has(disposition);
}
