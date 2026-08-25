export const SHA_A = "a".repeat(64);
export const SHA_B = "b".repeat(64);

export function geometryDocument(projectId = "fixture") {
  const anchors = {
    proximal: { joint_id: "shoulder.left", input_xy: [10, 10], projected_xy: [11, 11], residual_px: 1.4 },
    hinge: { joint_id: "elbow.left", input_xy: [20, 20], projected_xy: [21, 20], residual_px: 1 },
    distal: { joint_id: "wrist.left", input_xy: [30, 30], projected_xy: [30, 31], residual_px: 1 },
  };
  return {
    format: "autospine-alpha-geometry-evidence",
    format_version: 1,
    project_id: projectId,
    layers: [{
      layer_id: "arm.left", components: [{ component_id: 0, area: 120, bbox_xywh: [5, 6, 30, 40] }],
    }],
    paths: [{
      path_id: "arm.left.path.000", layer_id: "arm.left", component_id: 0,
      anchors, polyline_xy: [[11, 11], [21, 20], [30, 31]],
      hinge_candidate_xy: [21, 20], error_radius_px: 7,
    }],
    contacts: [{
      contact_id: "contact.torso_arm.000", mode: "overlap", layer_ids: ["torso", "arm.left"],
      bbox_xywh: [8, 9, 12, 14], representative_xy: [14, 16], error_radius_px: 5,
      endpoints_xy: [[13, 16], [15, 16]],
    }],
  };
}

export function reviewWithReference(sourceRef, evidenceKind = "layer_alpha", candidateId = "candidate-1") {
  return {
    status: "ready",
    projectId: "fixture",
    jointId: "elbow.left",
    candidateId,
    artifact: {
      joints: {
        "elbow.left": {
          candidates: [{
            candidate_id: candidateId,
            evidence: [{ kind: evidenceKind, source_ref: sourceRef }],
          }],
        },
      },
    },
  };
}
