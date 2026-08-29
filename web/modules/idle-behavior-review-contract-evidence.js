"use strict";

const SHA = /^[0-9a-f]{64}$/;

export function normalizeIdleReviewPreview(
  value, feature, targetBones, reviewPackage, candidate,
) {
  if (value === null) return null;
  const row = object(value, "身体摆动示意");
  exact(row, new Set([
    "kind", "evidence_authority", "coordinate_space", "canvas",
    "composite_url", "ticks_per_second", "duration_ticks", "anchor_px", "bones",
  ]), "身体摆动示意");
  if (feature.availability !== "candidate"
      || row.kind !== "setup-local-bone-schematic"
      || row.evidence_authority !== "none") {
    throw new Error("身体摆动示意语义无效");
  }
  const space = object(row.coordinate_space, "preview coordinate_space");
  exact(space, new Set(["origin", "x_axis", "y_axis", "units"]), "preview coordinate_space");
  if (space.origin !== "top_left" || space.x_axis !== "right"
      || space.y_axis !== "down" || space.units !== "pixel") {
    throw new Error("身体摆动示意坐标系无效");
  }
  const canvas = object(row.canvas, "preview canvas");
  exact(canvas, new Set(["width", "height"]), "preview canvas");
  positive(canvas.width, "canvas width");
  positive(canvas.height, "canvas height");
  positive(row.ticks_per_second, "preview ticks_per_second");
  positive(row.duration_ticks, "preview duration_ticks");
  point(row.anchor_px, "preview anchor");
  if (row.composite_url !== reviewPackage.project.composite_url
      || !safeApiUrl(row.composite_url)) {
    throw new Error("身体摆动 composite URL 与项目不一致");
  }
  if (row.canvas.width !== reviewPackage.project.canvas.width
      || row.canvas.height !== reviewPackage.project.canvas.height
      || row.ticks_per_second !== candidate.timing.ticks_per_second
      || row.duration_ticks !== candidate.timing.duration_ticks) {
    throw new Error("身体摆动示意与项目画布或候选时间不一致");
  }
  const bones = array(row.bones, "preview bones");
  if (bones.length !== targetBones.length
      || bones.some((bone, index) => bone?.bone_id !== targetBones[index])) {
    throw new Error("身体摆动示意骨骼顺序无效");
  }
  for (const bone of bones) validateBone(bone);
  return row;
}

export function normalizeIdleReviewHistory(value, targetBones) {
  if (value === null) return null;
  const row = object(value, "P10 历史");
  exact(row, new Set([
    "current_revision", "head_decision_sha256", "revision_count", "items",
  ]), "P10 历史");
  integer(row.current_revision, "current_revision", 0, 2_147_483_647);
  integer(row.revision_count, "revision_count", 0, 10_000);
  if (row.head_decision_sha256 !== null) digest(row.head_decision_sha256, "history head");
  const items = array(row.items, "history items");
  if (items.length !== row.revision_count) throw new Error("P10 历史数量不一致");
  if (row.current_revision !== row.revision_count) {
    throw new Error("P10 历史 current revision 与数量不一致");
  }
  if ((row.current_revision === 0) !== (row.head_decision_sha256 === null)) {
    throw new Error("P10 历史 head 无效");
  }
  for (const [index, item] of items.entries()) {
    exact(object(item, "history item"), new Set([
      "revision", "decision_sha256", "action", "probe_status", "parameters",
    ]), "history item");
    integer(item.revision, "history revision", 1, 2_147_483_647);
    digest(item.decision_sha256, "history decision_sha256");
    if (item.revision !== index + 1) throw new Error("P10 历史 revision 不连续");
    if (!["adjust", "reject", "unobservable"].includes(item.action)) {
      throw new Error("P10 历史 action 无效");
    }
    const adjusted = item.action === "adjust";
    if (item.probe_status !== (adjusted ? "pending_probe" : "not_applicable")) {
      throw new Error("P10 历史 probe status 与 action 不一致");
    }
    if (adjusted) reviewParameters(item.parameters, targetBones);
    else if (item.parameters !== null) throw new Error("终止决定不能携带参数");
  }
  if (items.length && (items.at(-1).revision !== row.current_revision
      || items.at(-1).decision_sha256 !== row.head_decision_sha256)) {
    throw new Error("P10 历史 head 与列表不一致");
  }
  return row;
}

function reviewParameters(value, targetBones) {
  const row = object(value, "history parameters");
  exact(row, new Set([
    "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
  ]), "history parameters");
  integer(row.cycles, "history cycles", 1, 64);
  reviewPerBone(row.per_bone_amplitude_deg, targetBones, 10, false);
  reviewPerBone(row.per_bone_phase_fraction, targetBones, 1, true);
}

function reviewPerBone(value, targetBones, maximum, exclusiveMaximum) {
  const rows = array(value, "history per-bone values");
  if (rows.length !== targetBones.length
      || rows.some((item, index) => item?.bone_id !== targetBones[index])) {
    throw new Error("history per-bone 骨骼顺序无效");
  }
  for (const item of rows) {
    finite(item.value, "history per-bone value");
    if (item.value < 0 || (exclusiveMaximum
      ? item.value >= maximum : item.value > maximum)) {
      throw new Error("history per-bone 数值无效");
    }
  }
}

export function rejectPrivateKeys(value, label) {
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    if (/(^|_)(path|file|directory|state_root)$/i.test(key)) {
      throw new Error(`${label} 包含本机路径字段`);
    }
    rejectPrivateKeys(child, label);
  }
}

function validateBone(bone) {
  exact(object(bone, "preview bone"), new Set([
    "bone_id", "parent_bone_id", "length_px", "setup_world_rotation_deg",
    "setup_start_px", "setup_end_px",
  ]), "preview bone");
  positive(bone.length_px, "bone length");
  finite(bone.setup_world_rotation_deg, "bone rotation");
  point(bone.setup_start_px, "bone start");
  point(bone.setup_end_px, "bone end");
}

function safeApiUrl(value) {
  return typeof value === "string" && value.startsWith("/api/projects/")
    && !value.includes("\\") && !value.includes("://") && !/[\u0000-\u001f]/.test(value);
}

function point(value, label) {
  const row = object(value, label);
  exact(row, new Set(["x", "y"]), label);
  finite(row.x, `${label} x`);
  finite(row.y, `${label} y`);
}

function positive(value, label) {
  finite(value, label);
  if (value <= 0) throw new Error(`${label} 必须为正数`);
}

function finite(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} 无效`);
}

function digest(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 不是 SHA-256`);
}

function integer(value, label, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${label} 无效`);
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} 必须为对象`);
  return value;
}

function array(value, label) {
  if (!Array.isArray(value)) throw new Error(`${label} 必须为数组`);
  return value;
}

function exact(value, fields, label) {
  if (Object.keys(value).length !== fields.size
      || Object.keys(value).some((key) => !fields.has(key))) {
    throw new Error(`${label} 字段无效`);
  }
}
