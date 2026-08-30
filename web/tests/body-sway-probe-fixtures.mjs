export const PACKAGE_A = "a".repeat(64);
export const PACKAGE_B = "b".repeat(64);
export const REPORT_SHA = "c".repeat(64);
export const BODY_SWAY_PARAMETERS = Object.freeze({
  cycles: 2,
  per_bone_amplitude_deg: [8, 7, 4, 2].map((value, index) => ({
    bone_id: ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"][index], value,
  })),
  per_bone_phase_fraction: [0, 0.04, 0.08, 0.12].map((value, index) => ({
    bone_id: ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"][index], value,
  })),
});

export function inventoryFixture(
  packages = [packageRow(PACKAGE_B, "probe_ready")], recommended = PACKAGE_B, skippedCount = 0,
) {
  const count = (status) => packages.filter((row) => row.status === status).length;
  return {
    format: "autospine-body-sway-probe-package-list",
    format_version: 1,
    count: packages.length,
    ready_count: count("probe_ready"),
    not_applicable_count: count("not_applicable"),
    review_required_count: count("p10_1_review_required"),
    packages,
    recommended_package_id: recommended,
    skipped_count: skippedCount,
  };
}

export function packageRow(packageId, status, projectId = "seethrough_output_5") {
  return {
    format: "autospine-body-sway-probe-package",
    format_version: 1,
    package_id: packageId,
    project_id: projectId,
    motion_id: "wave-left-v1",
    clip_id: "kimodo.wave-left.semantic.front",
    p9_decision_sha256: "9".repeat(64),
    candidate_sha256: "e".repeat(64),
    current_revision: status === "p10_1_review_required" ? 0 : 2,
    decision_sha256: status === "p10_1_review_required" ? null : "d".repeat(64),
    action: status === "probe_ready" ? "adjust" : status === "not_applicable" ? "unobservable" : null,
    probe_status: status === "probe_ready" ? "pending_probe" : status === "not_applicable" ? "not_applicable" : null,
    status,
  };
}

export function probeEntryFixture({
  packageId = PACKAGE_B,
  resultStatus = "manual_visual_required",
  rejectedCheck = null,
} = {}) {
  const checks = CHECK_IDS.map((checkId, index) => ({
    check_id: checkId,
    status: index >= 5 ? "unobservable" : checkId === rejectedCheck ? "rejected" : "passed",
    reason_code: index >= 5
      ? (index === 5 ? "reviewed_seam_anchors_missing" : "manual_runtime_preview_required")
      : checkId === rejectedCheck ? "sampled_check_rejected" : "sampled_check_passed",
    subject_count: index >= 5 ? 0 : index === 0 ? 1 : 4,
    sample_count: index >= 5 ? 0 : index === 0 ? 2 : 81,
    failure_count: checkId === rejectedCheck ? 2 : 0,
    evidence_sha256: index >= 5 ? null : String(index + 1).repeat(64),
  }));
  const schedule = {
    tick_schedule_sha256: "5".repeat(64),
    sample_count: 81,
    first_tick: 0,
    last_tick: 3_966_667,
  };
  const summary = {
    schedule_sample_count: 81,
    representative_sample_count: 81,
    rig_bone_count: 20,
    rotation_bone_count: 17,
    overlay_bone_count: 4,
    attachment_count: 20,
    mesh_attachment_count: 4,
    check_count: 7,
    passed_check_count: checks.filter((row) => row.status === "passed").length,
    rejected_check_count: checks.filter((row) => row.status === "rejected").length,
    unobservable_check_count: 2,
    not_applicable_check_count: 0,
  };
  const reasonCodes = [
    "manual_runtime_preview_required",
    "reviewed_seam_anchors_missing",
    "safe_range_unproven",
  ];
  if (resultStatus === "structural_rejected") {
    reasonCodes.push("sampled_structural_check_rejected");
  }
  reasonCodes.sort();
  const releaseGate = { status: "blocked", reason_codes: reasonCodes };
  const timing = { ticks_per_second: 1_000_000, duration_ticks: 3_966_667, loop: false };
  const result = {
    status: resultStatus,
    release_gate: releaseGate,
    schedule,
    checks,
    summary,
  };
  const report = reportFixture({ result, timing });
  return {
    format: "autospine-body-sway-probe-entry",
    format_version: 2,
    status: resultStatus,
    probeability: "probe_ready",
    package: {
      package_id: packageId,
      motion_policy_package_id: "8".repeat(64),
      project_id: "seethrough_output_5",
      motion_id: "wave-left-v1",
      clip_id: "kimodo.wave-left.semantic.front",
      motion_instance_v2_sha256: "7".repeat(64),
      reviewed_motion_bundle_sha256: "6".repeat(64),
      p9_decision_sha256: "9".repeat(64),
    },
    candidate_sha256: "e".repeat(64),
    history: {
      current_revision: 2,
      head_decision_sha256: "d".repeat(64),
      action: "adjust",
      probe_status: "pending_probe",
    },
    report_sha256: REPORT_SHA,
    preview: {
      kind: "sampled-structural-witness-preview",
      authority: "none",
      scope: "sampled-diagnostic-only",
      canonical_checks_are_authoritative: true,
      witnesses_are_exhaustive: false,
      timing,
      representative_sample_count: 81,
      witness_count: 3,
      witnesses_truncated: true,
      canvas_failure_marker_limit: 16,
      canvas: { width: 1024, height: 1024 },
      composite_url: "/api/projects/seethrough_output_5/composite",
      witnesses: [
        witness(0, 0),
        witness(1_950_000, 12, rejectedCheck === "sampled_canvas_containment"),
        witness(3_966_667, 0),
      ],
    },
    result,
    technical: {
      report,
      semantics: {
        diagnostic_only: true,
        release_authority: false,
        runtime_equivalence_claimed: false,
        visual_quality_claimed: false,
        continuous_time_safety_claimed: false,
      },
    },
    canvas_adjustment: null,
  };
}

export const CHECK_IDS = [
  "loop_closure",
  "fk_finite",
  "sampled_mesh_deformation",
  "sampled_canvas_containment",
  "shared_index_internal_continuity",
  "inter_attachment_seams",
  "visual_quality",
];

function setupBones(offset) {
  const ids = ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"];
  return ids.map((boneId, index) => ({
    bone_id: boneId,
    start_xy: [500 + offset + index * 4, 740 - index * 110],
    end_xy: [504 + offset + index * 4, 630 - index * 110],
    rotation_deg: -88,
  }));
}

function witness(tick, offset, canvasRejected = false) {
  return {
    tick,
    status: canvasRejected ? "rejected" : "passed",
    target_bones: setupBones(offset),
    canvas_failure_count: canvasRejected ? 334 : 0,
    canvas_failure_markers: canvasRejected ? Array.from({ length: 16 }, (_, index) => ({
      attachment_id: "layer-007",
      vertex_index: 12 + index,
      point_xy: [1040 + index, 488 + index],
      sides: ["right"],
    })) : [],
    canvas_failure_markers_truncated: canvasRejected,
  };
}

function reportFixture({ result, timing }) {
  const stage = (fields, value) => Object.fromEntries(fields.map((field) => [field, value]));
  const p3Fields = [
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
    "visuals_sha256", "bundle_sha256",
  ];
  const p5Fields = [
    "target_profile_sha256", "instance_sha256", "run_sha256",
    "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
  ];
  const p9Fields = [
    "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
    "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
    "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
  ];
  const p3 = stage(p3Fields, "4".repeat(64));
  const p5 = stage(p5Fields, "3".repeat(64));
  const p9 = stage(p9Fields, "2".repeat(64));
  p9.motion_policy_decision_sha256 = "9".repeat(64);
  p9.motion_instance_v2_sha256 = "7".repeat(64);
  p9.bundle_sha256 = "6".repeat(64);
  return {
    format: "autospine-body-sway-probe-report",
    format_version: 1,
    project_id: "seethrough_output_5",
    clip_id: "kimodo.wave-left.semantic.front",
    source: {
      idle_behavior_candidates_sha256: "e".repeat(64),
      idle_behavior_decision_sha256: "d".repeat(64),
      layer_manifest_sha256: "4".repeat(64),
      p3, p5, p9,
    },
    timing,
    selection: {
      candidate_id: "body-sway-candidate", feature_id: "body_sway",
      action: "adjust", probe_status: "pending_probe",
      parameters: structuredClone(BODY_SWAY_PARAMETERS),
    },
    prober: {},
    semantics: {},
    schedule: result.schedule,
    sample_stream: {},
    checks: result.checks,
    status: result.status,
    release_gate: result.release_gate,
    summary: result.summary,
  };
}
