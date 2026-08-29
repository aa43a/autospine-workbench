import {
  normalizeSeamReviewAddress, seamAnchorReviewPaths,
} from "../modules/seam-anchor-review-address.js";
import { normalizeSeamCandidateEnvelope } from "../modules/seam-anchor-review-candidate.js";
import {
  createSeamReviewState, setSeamAction, setSeamNotes, setSeamOption,
} from "../modules/seam-anchor-review-state.js";

export const SHA = {
  manifest: "a".repeat(64), rig: "b".repeat(64), bundle: "c".repeat(64),
  candidate: "d".repeat(64), relationship: "e".repeat(64),
  option: "f".repeat(64), image: "1".repeat(64), decision: "2".repeat(64),
  package: "3".repeat(64),
};
export const RELATIONSHIPS = [
  "seam.torso_arm.left", "seam.torso_arm.right",
  "seam.pelvis_leg.left", "seam.pelvis_leg.right",
  "seam.leg_foot.left", "seam.leg_foot.right",
];
export const ADDRESS = normalizeSeamReviewAddress({
  projectId: "sample.project", layerManifestSha256: SHA.manifest,
  p3RigSha256: SHA.rig, p3BundleSha256: SHA.bundle,
});

function locator(attachmentId, x, y) {
  return {
    attachment_id: attachmentId, attachment_type: "region",
    locator_type: "region-local-q4096", local_xy_q4096: [x, y],
  };
}

function option(relationshipId, index) {
  const optionId = `${relationshipId}.option.000`;
  const parent = `parent.${index}`;
  const child = `child.${index}`;
  return {
    option_id: optionId, parent_attachment_id: parent, child_attachment_id: child,
    parent_attachment_type: "region", child_attachment_type: "region",
    status: "candidate", reason_codes: [],
    contact_evidence: {
      contact_id: "overlap.000", mode: "overlap", area: 16,
      bbox_xywh: [10, 20, 4, 4], centroid_xy: [11.5, 21.5],
      variance_xy: [1.25, 1.25], representative_xy: [11, 21],
      error_radius_px: 1.581139, overlap_ratios: [0.2, 0.3],
      gap_distance_px: 0, endpoints_xy: [[11, 21], [11, 21]],
    },
    principal_axis: "x",
    sampling_profile: "bbox-major-axis-common-alpha-quantiles-v1",
    anchors: [0, 1].map((anchorIndex) => ({
      pair_id: `anchor.${String(anchorIndex).padStart(3, "0")}`,
      parent: locator(parent, 4096 + anchorIndex * 4096, 8192),
      child: locator(child, 12288 + anchorIndex * 4096, 16384),
    })),
    evidence_sha256: SHA.option,
  };
}

export function candidateEnvelope() {
  const relationships = RELATIONSHIPS.map((relationshipId, index) => ({
    relationship_id: relationshipId, relation: relationshipId.split(".")[1],
    joint: `joint.${index}`, side: relationshipId.split(".").at(-1),
    status: "review_required", reason_codes: [],
    options: [option(relationshipId, index)], evidence_sha256: SHA.relationship,
  }));
  const candidate = {
    format: "autospine-seam-anchor-candidates", format_version: 1,
    project_id: ADDRESS.projectId,
    source: {
      layer_manifest_sha256: SHA.manifest, rig_sha256: SHA.rig,
      bundle_sha256: SHA.bundle,
    },
    summary: {
      status: "manual_review_required", relationship_count: 6,
      review_required_count: 6, unobservable_count: 0,
    },
    release_gate: { status: "blocked", reason_codes: ["manual_review_required"] },
    relationships,
  };
  const paths = seamAnchorReviewPaths(ADDRESS);
  const attachmentImages = relationships.flatMap((relationship) => {
    const row = relationship.options[0];
    return ["parent", "child"].map((role) => {
      const attachmentId = row[`${role}_attachment_id`];
      return {
        option_id: row.option_id, attachment_role: role,
        attachment_id: attachmentId, attachment_type: "region",
        image_sha256: SHA.image, width: 64, height: 96,
        url: paths.optionImage(SHA.candidate, row.option_id, attachmentId, SHA.image),
      };
    });
  }).sort((left, right) => {
    if (left.option_id < right.option_id) return -1;
    if (left.option_id > right.option_id) return 1;
    return left.attachment_role === "parent" ? -1 : 1;
  });
  return {
    candidate_sha256: SHA.candidate, candidate, attachment_images: attachmentImages,
  };
}

export function blockedCandidateEnvelope() {
  const payload = candidateEnvelope();
  const reasonCodes = [
    ["CHILD_ROLE_MISSING", "NO_SUPPORTED_CANDIDATE_PAIR"],
    ["CHILD_ROLE_MISSING", "NO_SUPPORTED_CANDIDATE_PAIR"],
    ["NO_SUPPORTED_CANDIDATE_PAIR", "PARENT_ROLE_MISSING"],
    ["NO_SUPPORTED_CANDIDATE_PAIR", "PARENT_ROLE_MISSING"],
  ];
  payload.candidate.relationships.slice(2).forEach((relationship, index) => {
    const removed = relationship.options.map((row) => row.option_id);
    relationship.status = "unobservable";
    relationship.reason_codes = reasonCodes[index];
    relationship.options = [];
    payload.attachment_images = payload.attachment_images.filter(
      (row) => !removed.includes(row.option_id),
    );
  });
  payload.candidate.summary.review_required_count = 2;
  payload.candidate.summary.unobservable_count = 4;
  return payload;
}

export function seamEntryPayload(blocked = false, packageId = SHA.package) {
  const blockingRelationships = blocked ? [
    [RELATIONSHIPS[2], ["CHILD_ROLE_MISSING", "NO_SUPPORTED_CANDIDATE_PAIR"]],
    [RELATIONSHIPS[3], ["CHILD_ROLE_MISSING", "NO_SUPPORTED_CANDIDATE_PAIR"]],
    [RELATIONSHIPS[4], ["NO_SUPPORTED_CANDIDATE_PAIR", "PARENT_ROLE_MISSING"]],
    [RELATIONSHIPS[5], ["NO_SUPPORTED_CANDIDATE_PAIR", "PARENT_ROLE_MISSING"]],
  ].map(([relationship_id, reason_codes]) => ({ relationship_id, reason_codes })) : [];
  return {
    format: "autospine-seam-review-entry", format_version: 1,
    package_id: packageId, project_id: ADDRESS.projectId,
    address: {
      project_id: ADDRESS.projectId,
      layer_manifest_sha256: ADDRESS.layerManifestSha256,
      p3_rig_sha256: ADDRESS.p3RigSha256,
      p3_bundle_sha256: ADDRESS.p3BundleSha256,
    },
    candidate_sha256: SHA.candidate,
    status: blocked ? "blocked_unobservable" : "manual_review_required",
    summary: {
      relationship_count: 6,
      review_required_count: blocked ? 2 : 6,
      unobservable_count: blocked ? 4 : 0,
    },
    blocking_relationships: blockingRelationships,
  };
}

export function normalizedState() {
  const payload = candidateEnvelope();
  const paths = seamAnchorReviewPaths(ADDRESS);
  const result = normalizeSeamCandidateEnvelope(
    payload, ADDRESS, (optionId, attachmentId, sha) => paths.optionImage(
      SHA.candidate, optionId, attachmentId, sha,
    ),
  );
  return {
    ...createSeamReviewState(), candidate: result.candidate,
    candidateSha256: result.candidateSha256,
    attachmentImages: result.attachmentImages,
  };
}

export function decideAll(state, action = "accept") {
  let next = state;
  for (const relationship of state.candidate.relationships) {
    next = setSeamOption(next, relationship.relationship_id, relationship.options[0].option_id);
    next = setSeamAction(next, relationship.relationship_id, action);
    if (action !== "accept") {
      next = setSeamNotes(next, relationship.relationship_id, `${action} reviewed`);
    }
  }
  return next;
}

export function jsonResponse(status, payload) {
  return {
    status, ok: status >= 200 && status < 300,
    headers: { get: () => "application/json" },
    json: async () => payload, text: async () => JSON.stringify(payload),
  };
}
