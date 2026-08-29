"use strict";

import {
  normalizeSeamReviewAddress, requireSafeId, requireSha256,
} from "./seam-anchor-review-address.js";
import { hasExactFields } from "./seam-anchor-review-candidate.js";

const ENTRY_FIELDS = [
  "format", "format_version", "package_id", "project_id", "address",
  "candidate_sha256", "status", "summary", "blocking_relationships",
];
const ADDRESS_FIELDS = [
  "project_id", "layer_manifest_sha256", "p3_rig_sha256", "p3_bundle_sha256",
];
const SUMMARY_FIELDS = [
  "relationship_count", "review_required_count", "unobservable_count",
];
const BLOCKER_FIELDS = ["relationship_id", "reason_codes"];
const RELATIONSHIP_IDS = [
  "seam.torso_arm.left", "seam.torso_arm.right",
  "seam.pelvis_leg.left", "seam.pelvis_leg.right",
  "seam.leg_foot.left", "seam.leg_foot.right",
];
const REASON_CODE = /^[A-Z][A-Z0-9_]{0,127}$/;

function requireCount(value, label) {
  if (!Number.isInteger(value) || value < 0 || value > 6) {
    throw new Error(`${label} 无效`);
  }
  return value;
}

function requireReasonCodes(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 8
      || value.some((item) => typeof item !== "string" || !REASON_CODE.test(item))
      || new Set(value).size !== value.length
      || value.some((item, index) => index && value[index - 1] >= item)) {
    throw new Error("Seam 自动入口 blocker reason codes 无效");
  }
  return Object.freeze([...value]);
}

function requireBlockers(rows, expectedCount) {
  if (!Array.isArray(rows) || rows.length !== expectedCount) {
    throw new Error("Seam 自动入口 blocker 数量不一致");
  }
  let previousIndex = -1;
  return Object.freeze(rows.map((row) => {
    if (!hasExactFields(row, BLOCKER_FIELDS)) {
      throw new Error("Seam 自动入口 blocker 字段无效");
    }
    const index = RELATIONSHIP_IDS.indexOf(row.relationship_id);
    if (index < 0 || index <= previousIndex) {
      throw new Error("Seam 自动入口 blocker 顺序或身份无效");
    }
    previousIndex = index;
    return Object.freeze({
      relationshipId: row.relationship_id,
      reasonCodes: requireReasonCodes(row.reason_codes),
    });
  }));
}

export function packageIdFromSearch(search) {
  const values = new URLSearchParams(String(search ?? "")).getAll("package_id");
  if (!values.length) return null;
  if (values.length !== 1) throw new Error("package_id 必须且只能出现一次");
  return requireSha256(values[0], "Motion Policy package ID");
}

export function normalizeSeamReviewEntry(payload, expectedPackageId) {
  if (!hasExactFields(payload, ENTRY_FIELDS)
      || payload.format !== "autospine-seam-review-entry"
      || payload.format_version !== 1) {
    throw new Error("Seam 自动入口不是受支持的 path-free v1 合同");
  }
  const packageId = requireSha256(payload.package_id, "Motion Policy package ID");
  if (packageId !== requireSha256(expectedPackageId, "请求 package ID")) {
    throw new Error("Seam 自动入口与请求 package ID 不一致");
  }
  const projectId = requireSafeId(payload.project_id, "Seam 自动入口项目 ID");
  if (!hasExactFields(payload.address, ADDRESS_FIELDS)) {
    throw new Error("Seam 自动入口地址字段无效");
  }
  const address = normalizeSeamReviewAddress({
    projectId: payload.address.project_id,
    layerManifestSha256: payload.address.layer_manifest_sha256,
    p3RigSha256: payload.address.p3_rig_sha256,
    p3BundleSha256: payload.address.p3_bundle_sha256,
  });
  if (address.projectId !== projectId) {
    throw new Error("Seam 自动入口项目与服务端地址不一致");
  }
  if (!hasExactFields(payload.summary, SUMMARY_FIELDS)) {
    throw new Error("Seam 自动入口 summary 字段无效");
  }
  const relationshipCount = requireCount(
    payload.summary.relationship_count, "relationship_count",
  );
  const reviewRequiredCount = requireCount(
    payload.summary.review_required_count, "review_required_count",
  );
  const unobservableCount = requireCount(
    payload.summary.unobservable_count, "unobservable_count",
  );
  if (relationshipCount !== 6 || reviewRequiredCount + unobservableCount !== 6) {
    throw new Error("Seam 自动入口 summary 计数不一致");
  }
  const blockers = requireBlockers(payload.blocking_relationships, unobservableCount);
  const expectedStatus = unobservableCount
    ? "blocked_unobservable" : "manual_review_required";
  if (payload.status !== expectedStatus) {
    throw new Error("Seam 自动入口状态与不可观测计数不一致");
  }
  return Object.freeze({
    packageId, projectId, address,
    candidateSha256: requireSha256(payload.candidate_sha256, "Seam candidate SHA-256"),
    status: expectedStatus,
    summary: Object.freeze({ relationshipCount, reviewRequiredCount, unobservableCount }),
    blockingRelationships: blockers,
  });
}

export function requireSeamEntryCandidate(entry, envelope) {
  if (!entry || envelope?.candidateSha256 !== entry.candidateSha256) {
    throw new Error("自动入口与加载到的 Seam candidate 身份不一致");
  }
  const relationships = envelope.candidate?.relationships;
  if (!Array.isArray(relationships) || relationships.length !== 6) {
    throw new Error("自动入口候选缺少固定六个 relationship");
  }
  const unobservable = relationships.filter((row) => row.status === "unobservable");
  if (unobservable.length !== entry.summary.unobservableCount
      || relationships.length - unobservable.length !== entry.summary.reviewRequiredCount
      || envelope.candidate.summary?.relationship_count !== 6
      || envelope.candidate.summary?.review_required_count !== entry.summary.reviewRequiredCount
      || envelope.candidate.summary?.unobservable_count !== entry.summary.unobservableCount) {
    throw new Error("自动入口与 Seam candidate summary 不一致");
  }
  entry.blockingRelationships.forEach((blocker, index) => {
    const row = unobservable[index];
    if (row?.relationship_id !== blocker.relationshipId
        || JSON.stringify(row.reason_codes) !== JSON.stringify(blocker.reasonCodes)
        || row.options.length !== 0) {
      throw new Error("自动入口 blocker 与 Seam candidate 证据不一致");
    }
  });
  return entry;
}

export const SEAM_REVIEW_RELATIONSHIP_IDS = Object.freeze([...RELATIONSHIP_IDS]);
