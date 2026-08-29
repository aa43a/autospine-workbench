"use strict";

const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const PACKAGE_FIELDS = new Set([
  "format", "format_version", "package_id", "motion_policy_package_id",
  "project_id", "motion_id", "clip_id", "motion_instance_v2_sha256",
  "reviewed_motion_bundle_sha256", "p9_decision_sha256", "status", "source", "project",
]);
const CANDIDATE_FIELDS = new Set([
  "format", "format_version", "project_id", "clip_id", "source", "timing",
  "target_capabilities", "generator", "semantics", "features", "summary",
]);
const FEATURE_FIELDS = new Set([
  "feature_id", "availability", "candidate_id", "evidence", "reason_codes", "proposal",
]);
const P3_FIELDS = new Set([
  "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
  "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
  "visuals_sha256", "bundle_sha256",
]);
const P5_FIELDS = new Set([
  "target_profile_sha256", "instance_sha256", "run_sha256",
  "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
]);
const P9_FIELDS = new Set([
  "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
  "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
  "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
]);

export function normalizeIdleReviewDetailPackage(value, expectedPackageId) {
  const row = object(value, "P10 精确复核包");
  exact(row, PACKAGE_FIELDS, "P10 精确复核包");
  constant(row.format, "autospine-idle-behavior-review-package", "package format");
  constant(row.format_version, 1, "package format_version");
  constant(row.status, "ready_for_candidate_replay", "package status");
  for (const field of [
    "package_id", "motion_policy_package_id", "motion_instance_v2_sha256",
    "reviewed_motion_bundle_sha256", "p9_decision_sha256",
  ]) digest(row[field], field);
  for (const field of ["project_id", "motion_id", "clip_id"]) identifier(row[field], field);
  if (row.package_id !== expectedPackageId) throw new Error("P10 复核包身份串线");
  const source = exactSource(row.source);
  if (source.p9.motion_instance_v2_sha256 !== row.motion_instance_v2_sha256
      || source.p9.bundle_sha256 !== row.reviewed_motion_bundle_sha256
      || source.p9.motion_policy_decision_sha256 !== row.p9_decision_sha256) {
    throw new Error("P10 复核包与 P9 source 身份串线");
  }
  project(row.project, row.project_id);
  return row;
}

export function normalizeIdleCandidateDocument(value, reviewPackage, targetBones) {
  const row = object(value, "Idle 候选");
  exact(row, CANDIDATE_FIELDS, "Idle 候选");
  constant(row.format, "autospine-idle-behavior-candidates", "candidate format");
  constant(row.format_version, 1, "candidate format_version");
  if (row.project_id !== reviewPackage.project_id || row.clip_id !== reviewPackage.clip_id) {
    throw new Error("Idle 候选与项目或动作片段不一致");
  }
  const source = exactSource(row.source);
  if (canonical(source) !== canonical(reviewPackage.source)) {
    throw new Error("Idle 候选 source 与精确复核包不一致");
  }
  timing(row.timing);
  for (const field of ["target_capabilities", "generator", "semantics", "summary"]) {
    object(row[field], `candidate ${field}`);
  }
  const features = array(row.features, "Idle 特性");
  const expected = ["blink", "body_sway", "hair_spring", "mouth"];
  if (features.length !== expected.length
      || features.some((item, index) => item?.feature_id !== expected[index])) {
    throw new Error("Idle 特性顺序无效");
  }
  for (const feature of features) featureDocument(feature, targetBones);
  return row;
}

function exactSource(value) {
  const row = object(value, "P10 source");
  exact(row, new Set(["layer_manifest_sha256", "p3", "p5", "p9"]), "P10 source");
  digest(row.layer_manifest_sha256, "source layer_manifest_sha256");
  digestObject(row.p3, P3_FIELDS, "P3 source");
  digestObject(row.p5, P5_FIELDS, "P5 source");
  digestObject(row.p9, P9_FIELDS, "P9 source");
  if (row.p3.layer_manifest_sha256 !== row.layer_manifest_sha256) {
    throw new Error("P10 source layer manifest 身份串线");
  }
  return row;
}

function project(value, projectId) {
  const row = object(value, "P10 project");
  exact(row, new Set(["project_id", "canvas", "composite_url"]), "P10 project");
  if (row.project_id !== projectId) throw new Error("P10 project 身份串线");
  const canvas = object(row.canvas, "P10 project canvas");
  exact(canvas, new Set(["width", "height"]), "P10 project canvas");
  for (const field of ["width", "height"]) {
    if (!Number.isInteger(canvas[field]) || canvas[field] <= 0) throw new Error("P10 canvas 无效");
  }
  const expected = `/api/projects/${encodeURIComponent(projectId)}/composite`;
  if (row.composite_url !== expected) throw new Error("P10 composite URL 无效");
}

function timing(value) {
  const row = object(value, "candidate timing");
  exact(row, new Set(["ticks_per_second", "duration_ticks", "loop"]), "candidate timing");
  if (row.ticks_per_second !== 1_000_000
      || !Number.isInteger(row.duration_ticks) || row.duration_ticks <= 0
      || typeof row.loop !== "boolean") throw new Error("candidate timing 无效");
}

function featureDocument(value, targetBones) {
  const row = object(value, "Idle 特性");
  exact(row, FEATURE_FIELDS, "Idle 特性");
  if (!["candidate", "unobservable", "unsupported"].includes(row.availability)) {
    throw new Error("Idle 特性 availability 无效");
  }
  evidence(row.evidence);
  const reasons = array(row.reason_codes, "Idle reason_codes");
  if (new Set(reasons).size !== reasons.length) throw new Error("Idle reason_codes 重复");
  for (const reason of reasons) identifier(reason, "reason_code");
  if (row.feature_id !== "body_sway") {
    if (row.candidate_id !== null || row.proposal !== null) throw new Error("非身体候选携带了 proposal");
    return;
  }
  if (row.availability !== "candidate") {
    if (row.candidate_id !== null || row.proposal !== null) throw new Error("不可观测身体候选携带了 proposal");
    return;
  }
  if (!/^body-sway-[0-9a-f]{64}$/.test(row.candidate_id)) throw new Error("身体摆动 candidate_id 无效");
  const proposal = object(row.proposal, "身体摆动 proposal");
  exact(proposal, new Set([
    "kind", "target_bone_ids", "required_review_parameters", "safe_range_evidence",
  ]), "身体摆动 proposal");
  if (proposal.kind !== "reviewed-periodic-body-sway"
      || !sameArray(proposal.target_bone_ids, targetBones)
      || !sameArray(proposal.required_review_parameters, [
        "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
      ]) || proposal.safe_range_evidence !== "unprobed") {
    throw new Error("身体摆动 proposal 无效");
  }
}

function evidence(value) {
  const row = object(value, "Idle evidence");
  exact(row, new Set([
    "layers", "bindings", "bone_ids", "existing_tracks",
  ]), "Idle evidence");
  for (const field of ["layers", "bindings", "bone_ids", "existing_tracks"]) array(row[field], field);
}

function digestObject(value, fields, label) {
  const row = object(value, label);
  exact(row, fields, label);
  for (const field of fields) digest(row[field], `${label} ${field}`);
}

function digest(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 不是 SHA-256`);
}

function identifier(value, label) {
  if (typeof value !== "string" || !ID.test(value)) throw new Error(`${label} 无效`);
}

function constant(value, expected, label) {
  if (value !== expected) throw new Error(`${label} 不受支持`);
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
      || Object.keys(value).some((key) => !fields.has(key))) throw new Error(`${label} 字段无效`);
}

function sameArray(left, right) {
  return Array.isArray(left) && left.length === right.length
    && left.every((item, index) => item === right[index]);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
