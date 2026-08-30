import { REPORT_SHA } from "./body-sway-probe-fixtures.mjs";

export const ADJUSTMENT_SHA = "f".repeat(64);
const BONES = ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"];

export function canvasAdjustmentEnvelope(entry, options = {}) {
  const classification = options.classification
    ?? "sampled_adjustment_candidate_available";
  const reviewedCheck = entry.result.checks.find(
    (row) => row.check_id === "sampled_canvas_containment",
  );
  const reviewedCanvasCheck = Object.fromEntries([
    "status", "sample_count", "failure_count", "evidence_sha256",
  ].map((field) => [field, reviewedCheck[field]]));
  const reviewedRejected = reviewedCheck.status === "rejected";
  const probeOptions = classification === "sampled_adjustment_candidate_available"
    ? [probe(0, false), probe(4, false), ...[5, 6, 7].map((gain) => probe(gain, true)),
      probe(8, reviewedRejected, reviewedCheck)]
    : classification === "upstream_base_motion_canvas_overflow"
      ? [probe(0, true), probe(8, true, reviewedCheck)]
      : classification === "reviewed_canvas_passed"
        ? [probe(8, false, reviewedCheck)]
        : [probe(0, false), ...Array.from({ length: 8 }, (_, gain) =>
          probe(gain + 1, true, gain === 7 ? reviewedCheck : null))];
  const proposal = classification === "sampled_adjustment_candidate_available"
    ? candidate(entry.technical.report.selection.parameters, probeOptions[1]) : null;
  const zero = probeOptions.find((row) => row.gain.numerator === 0);
  const reasons = ({
    reviewed_canvas_passed: ["reviewed_canvas_containment_passed"],
    upstream_base_motion_canvas_overflow: [
      "body_sway_zero_gain_did_not_remove_canvas_overflow",
      "upstream_base_motion_canvas_overflow",
    ],
    sampled_adjustment_candidate_available: [
      "lower_uniform_gain_sampled_canvas_and_geometry_passed",
      "requires_explicit_p10_1_revision",
    ],
    no_nonzero_sampled_adjustment_candidate: [
      "fixed_gain_grid_found_no_nonzero_sampled_pass",
    ],
  })[classification];
  const document = {
    format: "autospine-body-sway-canvas-adjustment-candidates",
    format_version: 1,
    project_id: entry.package.project_id,
    clip_id: entry.package.clip_id,
    source: {
      probe_inputs: structuredClone(entry.technical.report.source),
      current_p10_1_head: {
        candidate_sha256: entry.candidate_sha256,
        decision_sha256: entry.history.head_decision_sha256,
        revision: entry.history.current_revision,
      },
      body_sway_probe_report_sha256: entry.report_sha256 ?? REPORT_SHA,
    },
    timing: structuredClone(entry.technical.report.timing),
    reviewed_selection: structuredClone(entry.technical.report.selection),
    analyzer: {
      id: "body-sway-canvas-adjustment-analyzer", version: "1.0.0",
      config: {
        parameterization: "uniform-amplitude-gain", gain_denominator: 8,
        reviewed_gain_numerator: 8, search_order: [7, 6, 5, 4, 3, 2, 1],
        search_stop: "first-sampled-structural-pass",
        zero_gain_probe_required_after_reviewed_failure: true,
        sample_schedule: "exact-p10.2-probe-schedule",
      },
    },
    semantics: {
      scope: "sampled-canvas-adjustment-candidate-only", authority: "none",
      human_decision_emitted: false, review_revision_written: false,
      temporary_preview_emitted: false, sampled_canvas_observation_claimed: true,
      discrete_gain_samples_are_safe_interval: false, safe_parameters_claimed: false,
      continuous_time_safety_claimed: false, visual_quality_claimed: false,
      runtime_equivalence_claimed: false, inter_attachment_seam_safety_claimed: false,
    },
    diagnosis: {
      classification, reason_codes: reasons,
      reviewed_canvas_check: reviewedCanvasCheck,
      zero_gain_canvas_status: zero?.canvas_status ?? "not_evaluated",
      other_rejected_check_ids: entry.result.checks.filter((row) =>
        row.check_id !== "sampled_canvas_containment" && row.status === "rejected")
        .map((row) => row.check_id).sort(),
    },
    probes: probeOptions,
    adjustment_candidates: proposal ? [proposal] : [],
    status: "candidate_only",
    release_gate: {
      status: "blocked",
      reason_codes: [
        "candidate_requires_explicit_p10_1_review",
        "continuous_time_safety_unproven",
        "manual_runtime_preview_required",
        "reviewed_seam_anchors_missing",
        "safe_parameters_unproven",
      ],
    },
    summary: {
      classification, tested_gain_count: probeOptions.length,
      adjustment_candidate_count: proposal ? 1 : 0,
      reviewed_canvas_failure_tick_count: probeOptions.at(-1).canvas_failure_tick_count,
      zero_gain_canvas_failure_tick_count: zero?.canvas_failure_tick_count ?? null,
    },
  };
  return { candidate_sha256: ADJUSTMENT_SHA, document };
}

function candidate(parameters, evidence) {
  return {
    candidate_id: `body-sway-canvas-adjustment-${"a".repeat(64)}`,
    kind: "uniform_amplitude_gain", status: "unvalidated_draft", authority: "none",
    gain: { numerator: 4, denominator: 8 },
    parameters: {
      cycles: parameters.cycles,
      per_bone_amplitude_deg: parameters.per_bone_amplitude_deg.map((row) => ({
        bone_id: row.bone_id, value: row.value / 2,
      })),
      per_bone_phase_fraction: structuredClone(parameters.per_bone_phase_fraction),
    },
    probe_evidence_sha256: evidence.evidence_sha256,
    requires_explicit_p10_1_revision: true,
    claims: {
      sampled_canvas_passed: true, sampled_geometry_passed: true,
      safe_parameters: false, continuous_time: false, visual_quality: false,
      release_authority: false,
    },
  };
}

function probe(gain, rejected, reviewed = null) {
  const failureCount = reviewed?.failure_count ?? (rejected ? 2 : 0);
  const sampleCount = reviewed?.sample_count ?? 81;
  return {
    gain: { numerator: gain, denominator: 8 }, sample_count: sampleCount,
    canvas_status: rejected ? "rejected" : "passed",
    sampled_geometry_status: rejected ? "rejected" : "passed",
    canvas_failure_tick_count: failureCount,
    canvas_failure_vertex_count: failureCount ? failureCount * 4 : 0,
    geometry_rejection_tick_count: failureCount,
    first_failure_tick: failureCount ? 1_950_000 : null,
    last_failure_tick: failureCount ? 1_950_000 : null,
    affected_attachment_ids: failureCount ? ["layer-007"] : [],
    failure_sides: failureCount ? ["right"] : [],
    max_overflow_px: failureCount ? 16 : 0,
    worst_failure: failureCount ? {
      tick: 1_950_000, attachment_id: "layer-007", vertex_index: 12,
      point_xy: [1040, 488], sides: ["right"], overflow_px: 16,
    } : null,
    sampled_body_sway_peak_abs_delta_deg: BONES.map((bone_id, index) => ({
      bone_id, value: [8, 7, 4, 2][index] * gain / 8,
    })),
    evidence_sha256: String(gain).repeat(64),
  };
}
