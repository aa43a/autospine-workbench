"use strict";

import {
  requireSafeId, requireSha256,
} from "./seam-anchor-review-address.js";

const RELATIONSHIP_IDS = [
  "seam.torso_arm.left", "seam.torso_arm.right",
  "seam.pelvis_leg.left", "seam.pelvis_leg.right",
  "seam.leg_foot.left", "seam.leg_foot.right",
];
const IMAGE_FIELDS = [
  "option_id", "attachment_role", "attachment_id", "attachment_type",
  "image_sha256", "width", "height", "url",
];

export const hasExactFields = (value, fields) => value
  && typeof value === "object" && !Array.isArray(value)
  && Object.keys(value).length === fields.length
  && fields.every((field) => Object.hasOwn(value, field));

export function requireSeamLocator(
  locator, attachmentId, attachmentType, bounds = null,
) {
  if (!locator || typeof locator !== "object" || Array.isArray(locator)
      || locator.attachment_id !== attachmentId
      || locator.attachment_type !== attachmentType) {
    throw new Error("锚点 locator 与 attachment 身份不一致");
  }
  if (attachmentType === "region") {
    if (!hasExactFields(locator, [
      "attachment_id", "attachment_type", "locator_type", "local_xy_q4096",
    ]) || locator.locator_type !== "region-local-q4096"
        || !Array.isArray(locator.local_xy_q4096)
        || locator.local_xy_q4096.length !== 2
        || locator.local_xy_q4096.some((item) => !Number.isInteger(item) || item < 0)
        || bounds && (locator.local_xy_q4096[0] > bounds.width * 4096
          || locator.local_xy_q4096[1] > bounds.height * 4096)) {
      throw new Error("region locator 无效");
    }
  } else if (attachmentType === "mesh") {
    if (!hasExactFields(locator, [
      "attachment_id", "attachment_type", "locator_type",
      "triangle_index", "vertex_indices", "weights_q65535",
    ]) || locator.locator_type !== "mesh-barycentric-q65535"
        || !Number.isInteger(locator.triangle_index)
        || !Array.isArray(locator.vertex_indices) || locator.vertex_indices.length !== 3
        || locator.triangle_index < 0 || locator.triangle_index >= 8192
        || !Array.isArray(locator.weights_q65535) || locator.weights_q65535.length !== 3
        || locator.vertex_indices.some((item) => !Number.isInteger(item)
          || item < 0 || item >= 4096)
        || new Set(locator.vertex_indices).size !== 3
        || locator.weights_q65535.some((item) => !Number.isInteger(item)
          || item < 0 || item > 65535)
        || locator.weights_q65535.reduce((sum, item) => sum + item, 0) !== 65535) {
      throw new Error("mesh locator 无效");
    }
  } else throw new Error("attachment type 无效");
  return locator;
}

function requireOption(raw, relationshipId, index) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)
      || raw.option_id !== `${relationshipId}.option.${String(index).padStart(3, "0")}`
      || !["candidate", "unavailable"].includes(raw.status)
      || !["region", "mesh"].includes(raw.parent_attachment_type)
      || !["region", "mesh"].includes(raw.child_attachment_type)
      || !Array.isArray(raw.anchors) || !Array.isArray(raw.reason_codes)) {
    throw new Error("候选包含无效 seam option");
  }
  requireSafeId(raw.parent_attachment_id, "parent attachment ID");
  requireSafeId(raw.child_attachment_id, "child attachment ID");
  requireSha256(raw.evidence_sha256, "option evidence SHA-256");
  raw.anchors.forEach((row, anchorIndex) => {
    if (!hasExactFields(row, ["pair_id", "parent", "child"])
        || row.pair_id !== `anchor.${String(anchorIndex).padStart(3, "0")}`) {
      throw new Error("候选 anchor 序列无效");
    }
    requireSeamLocator(row.parent, raw.parent_attachment_id, raw.parent_attachment_type);
    requireSeamLocator(row.child, raw.child_attachment_id, raw.child_attachment_type);
  });
  return raw;
}

function requireRelationships(candidate) {
  if (!Array.isArray(candidate.relationships) || candidate.relationships.length !== 6) {
    throw new Error("候选必须包含固定六个 seam relationship");
  }
  candidate.relationships.forEach((row, index) => {
    if (!row || typeof row !== "object" || row.relationship_id !== RELATIONSHIP_IDS[index]
        || !["review_required", "unobservable"].includes(row.status)
        || !Array.isArray(row.options) || !Array.isArray(row.reason_codes)) {
      throw new Error("候选 relationship 顺序或状态无效");
    }
    requireSha256(row.evidence_sha256, "relationship evidence SHA-256");
    row.options.forEach((option, optionIndex) =>
      requireOption(option, row.relationship_id, optionIndex));
    const expectedStatus = row.options.some((option) => option.status === "candidate")
      ? "review_required" : "unobservable";
    if (row.status !== expectedStatus) throw new Error("候选 relationship 状态与 options 不一致");
  });
}

function requireAttachmentImages(rows, candidate, expectedUrl) {
  if (!Array.isArray(rows) || typeof expectedUrl !== "function") {
    throw new Error("attachment image evidence 缺失");
  }
  const expected = candidate.relationships.flatMap((relationship) =>
    relationship.options.flatMap((option) => ["parent", "child"].map((role) => ({
      option, role,
    })))).sort((left, right) => {
      if (left.option.option_id < right.option.option_id) return -1;
      if (left.option.option_id > right.option.option_id) return 1;
      return left.role === "parent" ? -1 : 1;
    });
  if (rows.length !== expected.length) throw new Error("attachment image evidence 不完整");
  rows.forEach((row, index) => {
    const { option, role } = expected[index];
    const id = option[`${role}_attachment_id`];
    const type = option[`${role}_attachment_type`];
    if (!hasExactFields(row, IMAGE_FIELDS) || row.option_id !== option.option_id
        || row.attachment_role !== role || row.attachment_id !== id
        || row.attachment_type !== type || !Number.isInteger(row.width) || row.width < 1
        || !Number.isInteger(row.height) || row.height < 1) {
      throw new Error("attachment image evidence 与 option 不一致");
    }
    const sha = requireSha256(row.image_sha256, "attachment image SHA-256");
    if (row.url !== expectedUrl(option.option_id, id, sha)) {
      throw new Error("attachment image URL 与精确证据地址不一致");
    }
  });
  return rows.map((row) => ({ ...row }));
}

export function normalizeSeamCandidateEnvelope(payload, address, expectedUrl) {
  const candidateSha256 = requireSha256(payload?.candidate_sha256, "candidate SHA-256");
  const candidate = payload?.candidate;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)
      || candidate.format !== "autospine-seam-anchor-candidates"
      || candidate.format_version !== 1 || candidate.project_id !== address.projectId
      || candidate.source?.layer_manifest_sha256 !== address.layerManifestSha256
      || candidate.source?.rig_sha256 !== address.p3RigSha256
      || candidate.source?.bundle_sha256 !== address.p3BundleSha256
      || candidate.summary?.status !== "manual_review_required"
      || candidate.release_gate?.status !== "blocked") {
    throw new Error("候选响应与显式地址不一致");
  }
  requireRelationships(candidate);
  const attachmentImages = requireAttachmentImages(
    payload.attachment_images, candidate, expectedUrl,
  );
  return { candidateSha256, candidate, attachmentImages };
}
