"use strict";

const SHA256 = /^[0-9a-f]{64}$/;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ALLOWED_SECTIONS = {
  layer_alpha: new Set(["layers", "paths"]),
  contact_geometry: new Set(["contacts"]),
  kinematic_residual: new Set(["paths"]),
};

export function geometryReferencesForCandidate(candidate) {
  const references = [];
  for (const evidence of candidate?.evidence || []) {
    const sourceRef = evidence?.source_ref;
    if (typeof sourceRef !== "string" || !sourceRef.startsWith("alpha-geometry-evidence:")) continue;
    references.push(parseGeometryEvidenceRef(sourceRef, evidence.kind));
  }
  const unique = new Map(references.map((item) => [item.sourceRef, item]));
  return [...unique.values()];
}

export function parseGeometryEvidenceRef(sourceRef, evidenceKind) {
  if (typeof sourceRef !== "string") throw new Error("几何证据引用不是字符串");
  const match = /^alpha-geometry-evidence:([0-9a-f]{64})#(.+)$/.exec(sourceRef);
  if (!match) throw new Error("几何证据引用格式损坏");
  const [, sha256, fragment] = match;
  const parts = fragment.split("/");
  const section = parts[0];
  if (!ALLOWED_SECTIONS[evidenceKind]?.has(section)) {
    throw new Error("几何证据类型与 fragment 不匹配");
  }
  if (["paths", "contacts"].includes(section)) {
    if (parts.length !== 2 || !SAFE_ID.test(parts[1])) throw new Error("几何证据 fragment 格式损坏");
    return { sourceRef, sha256, fragment, section, itemId: parts[1], componentId: null };
  }
  if (parts.length === 2 && SAFE_ID.test(parts[1])) {
    return { sourceRef, sha256, fragment, section, itemId: parts[1], componentId: null };
  }
  if (parts.length === 4 && SAFE_ID.test(parts[1]) && parts[2] === "components"
      && /^(0|[1-9][0-9]*)$/.test(parts[3])) {
    return { sourceRef, sha256, fragment, section, itemId: parts[1], componentId: Number(parts[3]) };
  }
  throw new Error("几何证据 layer fragment 格式损坏");
}

export function resolveGeometryEvidenceTargets(document, { projectId, sha256, references }) {
  validateDocumentRoot(document, projectId);
  if (!SHA256.test(String(sha256))) throw new Error("几何证据 SHA 无效");
  const targets = [];
  for (const reference of references) {
    if (reference.sha256 !== sha256) throw new Error("候选引用了不同的几何证据 SHA");
    const target = resolveReference(document, reference);
    validateTarget(target);
    targets.push(target);
  }
  return targets;
}

function validateDocumentRoot(document, projectId) {
  if (!document || typeof document !== "object"
      || document.format !== "autospine-alpha-geometry-evidence"
      || document.format_version !== 1
      || String(document.project_id) !== String(projectId)
      || !Array.isArray(document.layers) || !Array.isArray(document.paths)
      || !Array.isArray(document.contacts)) {
    throw new Error("几何证据文档格式或项目绑定损坏");
  }
}

function resolveReference(document, reference) {
  if (reference.section === "paths") {
    const item = document.paths.find((entry) => entry?.path_id === reference.itemId);
    if (!item) throw new Error(`几何路径 ${reference.itemId} 不存在`);
    return { ...reference, item };
  }
  if (reference.section === "contacts") {
    const item = document.contacts.find((entry) => entry?.contact_id === reference.itemId);
    if (!item) throw new Error(`几何接触 ${reference.itemId} 不存在`);
    return { ...reference, item };
  }
  const layer = document.layers.find((entry) => entry?.layer_id === reference.itemId);
  if (!layer) throw new Error(`几何图层 ${reference.itemId} 不存在`);
  const component = reference.componentId == null
    ? null
    : layer.components?.find((entry) => entry?.component_id === reference.componentId);
  if (reference.componentId != null && !component) {
    throw new Error(`几何图层 component ${reference.componentId} 不存在`);
  }
  return { ...reference, item: layer, component };
}

function validateTarget(target) {
  if (target.section === "paths") return validatePath(target.item);
  if (target.section === "contacts") return validateContact(target.item);
  const components = target.component ? [target.component] : target.item.components;
  if (!Array.isArray(components) || !components.length || components.some((item) => !bbox(item?.bbox_xywh))) {
    throw new Error("几何图层 bbox 损坏");
  }
}

function validatePath(item) {
  const anchors = item?.anchors;
  if (!SAFE_ID.test(String(item?.path_id)) || !Array.isArray(item.polyline_xy)
      || !item.polyline_xy.every(point) || !point(item.hinge_candidate_xy)
      || !nonnegative(item.error_radius_px) || !anchors
      || [anchors.proximal, anchors.hinge, anchors.distal].some((anchor) => (
        !point(anchor?.input_xy) || (anchor.projected_xy != null && !point(anchor.projected_xy))
        || (anchor.residual_px != null && !nonnegative(anchor.residual_px))
      ))) {
    throw new Error("几何路径数据损坏");
  }
}

function validateContact(item) {
  if (!SAFE_ID.test(String(item?.contact_id)) || !bbox(item.bbox_xywh)
      || !point(item.representative_xy) || !nonnegative(item.error_radius_px)
      || !Array.isArray(item.endpoints_xy) || item.endpoints_xy.length !== 2
      || !item.endpoints_xy.every(point) || !Array.isArray(item.layer_ids)
      || item.layer_ids.some((id) => !SAFE_ID.test(String(id))) || typeof item.mode !== "string") {
    throw new Error("几何接触数据损坏");
  }
}

function point(value) {
  return Array.isArray(value) && value.length === 2 && value.every(Number.isFinite);
}

function bbox(value) {
  return Array.isArray(value) && value.length === 4 && value.every(Number.isFinite)
    && value[2] > 0 && value[3] > 0;
}

function nonnegative(value) {
  return Number.isFinite(value) && value >= 0;
}
