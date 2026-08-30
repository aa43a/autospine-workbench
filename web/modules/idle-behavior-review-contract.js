"use strict";

import {
  normalizeIdleReviewHistory, normalizeIdleReviewPreview, rejectPrivateKeys,
} from "./idle-behavior-review-contract-evidence.js";
import {
  normalizeIdleCandidateDocument, normalizeIdleReviewDetailPackage,
} from "./idle-behavior-review-contract-package.js";

export const TARGET_BONES = Object.freeze([
  "pelvis-spine", "spine-chest", "chest-neck", "neck-head",
]);

const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const PACKAGE_STATUSES = new Set([
  "ready_for_candidate_replay", "stale_for_current_project",
]);
const LIST_FIELDS = new Set([
  "package_id", "project_id", "motion_id", "clip_id",
  "motion_policy_package_id", "p9_decision_sha256", "status",
]);
const ENTRY_FIELDS = new Set([
  "format", "format_version", "status", "package", "candidate_sha256",
  "candidate", "suggestion", "preview", "history",
]);

export function normalizeIdleReviewPackageList(value) {
  const root = object(value, "P10 复核包清单");
  exact(root, new Set([
    "format", "format_version", "count", "skipped_count",
    "recommended_package_id", "packages",
  ]), "P10 复核包清单");
  requireConst(root, "format", "autospine-idle-behavior-review-package-list");
  requireConst(root, "format_version", 1);
  const rows = array(root.packages, "P10 复核包").map(packageSummary);
  integer(root.count, "count", 0, 128);
  integer(root.skipped_count, "skipped_count", 0, Number.MAX_SAFE_INTEGER);
  if (root.count !== rows.length) throw new Error("P10 复核包数量不一致");
  const ids = rows.map((row) => row.package_id);
  if (new Set(ids).size !== ids.length) throw new Error("P10 复核包 ID 重复");
  if (root.recommended_package_id !== null) {
    digest(root.recommended_package_id, "recommended_package_id");
    const recommended = rows.find(
      (row) => row.package_id === root.recommended_package_id,
    );
    if (!recommended) {
      throw new Error("P10 推荐复核包不在清单中");
    }
    if (recommended.status !== "ready_for_candidate_replay") {
      throw new Error("P10 推荐复核包不是当前可重放版本");
    }
  }
  return { ...root, packages: rows };
}

export function normalizeIdleReviewEntry(value, expectedPackageId) {
  const root = object(value, "P10 复核入口");
  exact(root, ENTRY_FIELDS, "P10 复核入口");
  requireConst(root, "format", "autospine-idle-behavior-review-entry");
  requireConst(root, "format_version", 1);
  identifier(root.status, "entry status");
  const reviewPackage = normalizeIdleReviewDetailPackage(root.package, expectedPackageId);
  digest(root.candidate_sha256, "candidate_sha256");
  const candidate = normalizeIdleCandidateDocument(root.candidate, reviewPackage, TARGET_BONES);
  const feature = candidate.features.find((row) => row.feature_id === "body_sway");
  const suggestion = suggestionDocument(root.suggestion, feature);
  const preview = normalizeIdleReviewPreview(
    root.preview, feature, TARGET_BONES, reviewPackage, candidate,
  );
  const history = normalizeIdleReviewHistory(root.history, TARGET_BONES);
  const expectedStatus = feature.availability !== "candidate"
    ? "candidate_unobservable"
    : history.current_revision ? "reviewed" : "review_required";
  if (root.status !== expectedStatus) throw new Error("P10 复核状态与历史不一致");
  rejectPrivateKeys(root, "P10 复核入口");
  return { ...root, package: reviewPackage, candidate, suggestion, preview, history };
}

export function normalizeIdleReviewReceipt(value, expected) {
  const root = object(value, "P10 提交回执");
  exact(root, new Set([
    "format", "format_version", "status", "package_id", "candidate_sha256",
    "decision_sha256", "revision", "action", "probe_status", "reused", "history",
  ]), "P10 提交回执");
  requireConst(root, "format", "autospine-idle-behavior-review-receipt");
  requireConst(root, "format_version", 1);
  requireConst(root, "status", "recorded");
  digest(root.package_id, "receipt package_id");
  digest(root.candidate_sha256, "receipt candidate_sha256");
  digest(root.decision_sha256, "receipt decision_sha256");
  integer(root.revision, "receipt revision", 1, 2_147_483_647);
  identifier(root.action, "receipt action");
  identifier(root.probe_status, "receipt probe_status");
  if (typeof root.reused !== "boolean") throw new Error("receipt reused 无效");
  const history = object(root.history, "receipt history");
  exact(history, new Set([
    "current_revision", "head_decision_sha256",
  ]), "receipt history");
  if (history.current_revision !== root.revision
      || history.head_decision_sha256 !== root.decision_sha256) {
    throw new Error("P10 提交回执历史未读回新决定");
  }
  if (root.package_id !== expected.packageId
      || root.candidate_sha256 !== expected.candidateSha256
      || root.revision !== expected.baseRevision + 1
      || root.action !== expected.action) {
    throw new Error("P10 提交回执与请求身份不一致");
  }
  rejectPrivateKeys(root, "P10 提交回执");
  return root;
}

function packageSummary(value) {
  const row = object(value, "P10 复核包摘要");
  exact(row, LIST_FIELDS, "P10 复核包摘要");
  for (const field of ["package_id", "motion_policy_package_id", "p9_decision_sha256"]) {
    digest(row[field], field);
  }
  for (const field of ["project_id", "motion_id", "clip_id", "status"]) {
    identifier(row[field], field);
  }
  if (!PACKAGE_STATUSES.has(row.status)) {
    throw new Error("P10 复核包摘要 status 不受支持");
  }
  return row;
}

function suggestionDocument(value, feature) {
  if (feature.availability !== "candidate") {
    if (value !== null) throw new Error("不可观测候选不能携带参数建议");
    return null;
  }
  const row = object(value, "身体摆动建议");
  exact(row, new Set([
    "profile", "authority", "status", "action", "reason_code", "payload", "claims",
  ]), "身体摆动建议");
  const profile = object(row.profile, "身体摆动建议 profile");
  exact(profile, new Set(["id", "version"]), "身体摆动建议 profile");
  if (profile.id !== "body-sway-subtle-draft" || profile.version !== "1.0.0") {
    throw new Error("身体摆动建议 profile 不受支持");
  }
  if (row.authority !== "none" || row.status !== "unvalidated_draft"
      || row.action !== "adjust") {
    throw new Error("身体摆动建议越过了人工复核边界");
  }
  identifier(row.reason_code, "suggestion reason_code");
  parameters(row.payload);
  const claims = object(row.claims, "suggestion claims");
  exact(claims, new Set([
    "human_approved", "structural_safety", "visual_quality",
    "runtime_equivalence", "safe_range", "release_authority",
  ]), "suggestion claims");
  if (Object.values(claims).some((claim) => claim !== false)) {
    throw new Error("未验证建议不能声明通过");
  }
  return row;
}

function parameters(value) {
  const row = object(value, "身体摆动参数");
  exact(row, new Set([
    "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
  ]), "身体摆动参数");
  integer(row.cycles, "cycles", 1, 64);
  perBone(row.per_bone_amplitude_deg, "amplitude", 0, 10);
  perBone(row.per_bone_phase_fraction, "phase", 0, 1, true);
  return row;
}

function perBone(value, label, min, max, exclusiveMax = false) {
  const rows = array(value, `per-bone ${label}`);
  if (rows.length !== TARGET_BONES.length
      || rows.some((row, index) => row?.bone_id !== TARGET_BONES[index])) {
    throw new Error(`per-bone ${label} 骨骼顺序无效`);
  }
  for (const row of rows) {
    const number = row.value;
    if (typeof number !== "number" || !Number.isFinite(number) || number < min
        || (exclusiveMax ? number >= max : number > max)) {
      throw new Error(`per-bone ${label} 数值无效`);
    }
  }
}

function digest(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 不是 SHA-256`);
}

function identifier(value, label) {
  if (typeof value !== "string" || !ID.test(value)) throw new Error(`${label} 无效`);
}

function integer(value, label, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${label} 无效`);
}

function requireConst(value, key, expected) {
  if (value[key] !== expected) throw new Error(`${key} 不受支持`);
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

function sameArray(left, right) {
  return Array.isArray(left) && left.length === right.length
    && left.every((value, index) => value === right[index]);
}
