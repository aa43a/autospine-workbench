import { canvasAdjustmentEnvelope } from "./body-sway-canvas-adjustment-fixtures.mjs";

export const DIGESTS = Object.freeze({
  package: "a".repeat(64), policy: "b".repeat(64), p9: "c".repeat(64),
  candidate: "d".repeat(64), decision: "e".repeat(64), bundle: "f".repeat(64),
});

export const BONES = Object.freeze([
  "pelvis-spine", "spine-chest", "chest-neck", "neck-head",
]);

export function sourceDocument() {
  const layer = "3".repeat(64);
  return {
    layer_manifest_sha256: layer,
    p3: {
      base_rig_sha256: "4".repeat(64), base_bundle_sha256: "5".repeat(64),
      layer_manifest_sha256: layer, resolved_project_sha256: "6".repeat(64),
      rig_sha256: "7".repeat(64), run_sha256: "8".repeat(64),
      probes_sha256: "9".repeat(64), visuals_sha256: "0".repeat(64),
      bundle_sha256: "1".repeat(64),
    },
    p5: {
      target_profile_sha256: "2".repeat(64), instance_sha256: "3".repeat(64),
      run_sha256: "4".repeat(64), retarget_report_sha256: "5".repeat(64),
      mesh_regression_sha256: "6".repeat(64), bundle_sha256: "7".repeat(64),
    },
    p9: {
      foot_lock_candidates_sha256: "8".repeat(64),
      depth_order_candidates_sha256: "9".repeat(64),
      motion_policy_decision_sha256: DIGESTS.p9,
      reviewed_motion_policy_sha256: "0".repeat(64),
      motion_instance_v2_sha256: "2".repeat(64),
      run_sha256: "1".repeat(64), bundle_sha256: DIGESTS.bundle,
    },
  };
}

export function packageSummary(overrides = {}) {
  return {
    package_id: DIGESTS.package,
    project_id: "seethrough_output",
    motion_id: "kimodo-idle",
    clip_id: "idle-001",
    motion_policy_package_id: DIGESTS.policy,
    p9_decision_sha256: DIGESTS.p9,
    status: "ready_for_candidate_replay",
    ...overrides,
  };
}

export function packageList(rows = [packageSummary()], recommended = DIGESTS.package) {
  return {
    format: "autospine-idle-behavior-review-package-list",
    format_version: 1,
    count: rows.length,
    skipped_count: 0,
    recommended_package_id: recommended,
    packages: rows,
  };
}

export function candidateDocument() {
  const unavailable = (feature_id, availability = "unobservable") => ({
    feature_id, availability, candidate_id: null,
    evidence: { layers: [], bindings: [], bone_ids: [], existing_tracks: [] },
    reason_codes: [`${feature_id}-not-observed`], proposal: null,
  });
  return {
    format: "autospine-idle-behavior-candidates",
    format_version: 1,
    project_id: "seethrough_output",
    clip_id: "idle-001",
    source: sourceDocument(), timing: { ticks_per_second: 1_000_000, duration_ticks: 4_000_000, loop: true },
    target_capabilities: {}, generator: {}, semantics: {},
    features: [
      unavailable("blink"),
      {
        feature_id: "body_sway", availability: "candidate",
        candidate_id: `body-sway-${"1".repeat(64)}`,
        evidence: { layers: [], bindings: [], bone_ids: BONES, existing_tracks: [] },
        reason_codes: ["human-parameters-required"],
        proposal: {
          kind: "reviewed-periodic-body-sway",
          target_bone_ids: [...BONES],
          required_review_parameters: [
            "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
          ],
          safe_range_evidence: "unprobed",
        },
      },
      unavailable("hair_spring", "unsupported"),
      unavailable("mouth"),
    ],
    summary: { status: "candidate_only" },
  };
}

export function suggestionDocument() {
  return {
    profile: { id: "body-sway-subtle-draft", version: "1.0.0" },
    authority: "none",
    status: "unvalidated_draft",
    action: "adjust",
    reason_code: "human-approved-assisted-draft-v1",
    payload: {
      cycles: 2,
      per_bone_amplitude_deg: BONES.map((bone_id, index) => ({
        bone_id, value: [0.8, 0.7, 0.4, 0.2][index],
      })),
      per_bone_phase_fraction: BONES.map((bone_id, index) => ({
        bone_id, value: index * 0.04,
      })),
    },
    claims: {
      human_approved: false, structural_safety: false, visual_quality: false,
      runtime_equivalence: false, safe_range: false, release_authority: false,
    },
  };
}

export function previewDocument() {
  const starts = [[500, 700], [500, 600], [500, 500], [500, 410]];
  const lengths = [100, 100, 90, 80];
  return {
    kind: "setup-local-bone-schematic",
    evidence_authority: "none",
    coordinate_space: { origin: "top_left", x_axis: "right", y_axis: "down", units: "pixel" },
    canvas: { width: 1024, height: 1024 },
    composite_url: "/api/projects/seethrough_output/composite",
    ticks_per_second: 1_000_000,
    duration_ticks: 4_000_000,
    anchor_px: { x: 500, y: 700 },
    bones: BONES.map((bone_id, index) => ({
      bone_id,
      parent_bone_id: index ? BONES[index - 1] : "root-pelvis",
      length_px: lengths[index],
      setup_world_rotation_deg: -90,
      setup_start_px: { x: starts[index][0], y: starts[index][1] },
      setup_end_px: { x: starts[index][0], y: starts[index][1] - lengths[index] },
    })),
  };
}

export function entryDocument(overrides = {}) {
  return {
    format: "autospine-idle-behavior-review-entry",
    format_version: 1,
    status: "review_required",
    package: {
      format: "autospine-idle-behavior-review-package", format_version: 1,
      ...packageSummary(),
      motion_instance_v2_sha256: "2".repeat(64),
      reviewed_motion_bundle_sha256: DIGESTS.bundle,
      source: sourceDocument(),
      project: {
        project_id: "seethrough_output",
        canvas: { width: 1024, height: 1024 },
        composite_url: "/api/projects/seethrough_output/composite",
      },
    },
    candidate_sha256: DIGESTS.candidate,
    candidate: candidateDocument(),
    suggestion: suggestionDocument(),
    preview: previewDocument(),
    history: {
      current_revision: 0, head_decision_sha256: null,
      revision_count: 0, items: [],
    },
    ...overrides,
  };
}

export function reviewedEntryDocument(overrides = {}) {
  const parameters = structuredClone(suggestionDocument().payload);
  return entryDocument({
    status: "reviewed",
    history: {
      current_revision: 1, head_decision_sha256: DIGESTS.decision,
      revision_count: 1,
      items: [{
        revision: 1, decision_sha256: DIGESTS.decision,
        action: "adjust", probe_status: "pending_probe", parameters,
      }],
    },
    ...overrides,
  });
}

export function canvasAdjustmentDraftEntry() {
  const entry = reviewedEntryDocument();
  const fullSource = {
    idle_behavior_candidates_sha256: entry.candidate_sha256,
    idle_behavior_decision_sha256: entry.history.head_decision_sha256,
    ...structuredClone(entry.package.source),
  };
  const selection = {
    candidate_id: entry.candidate.features.find(
      (row) => row.feature_id === "body_sway",
    ).candidate_id,
    feature_id: "body_sway", action: "adjust", probe_status: "pending_probe",
    parameters: structuredClone(entry.history.items[0].parameters),
  };
  const canvasCheck = {
    check_id: "sampled_canvas_containment", status: "rejected",
    reason_code: "sampled_check_rejected", subject_count: 4,
    sample_count: 81, failure_count: 2, evidence_sha256: "4".repeat(64),
  };
  const pseudoProbeEntry = {
    package: entry.package, candidate_sha256: entry.candidate_sha256,
    history: {
      current_revision: 1, head_decision_sha256: DIGESTS.decision,
    },
    report_sha256: "c".repeat(64),
    result: { checks: [canvasCheck] },
    technical: { report: {
      source: fullSource, timing: structuredClone(entry.candidate.timing), selection,
    } },
  };
  const canvasAdjustment = canvasAdjustmentEnvelope(pseudoProbeEntry);
  return {
    format: "autospine-idle-behavior-canvas-adjustment-draft-entry",
    format_version: 1, status: "unvalidated_draft", entry,
    canvas_adjustment: canvasAdjustment,
    proposal: structuredClone(canvasAdjustment.document.adjustment_candidates[0]),
  };
}

export function receiptDocument(overrides = {}) {
  return {
    format: "autospine-idle-behavior-review-receipt",
    format_version: 1,
    status: "recorded",
    package_id: DIGESTS.package,
    candidate_sha256: DIGESTS.candidate,
    decision_sha256: DIGESTS.decision,
    revision: 1,
    action: "adjust",
    probe_status: "pending_probe",
    reused: false,
    history: { current_revision: 1, head_decision_sha256: DIGESTS.decision },
    ...overrides,
  };
}

export function jsonResponse(status, payload) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}
