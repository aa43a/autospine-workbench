export function dynamicViewportEnvelope(sampleCount = 81) {
  return {
    candidate_sha256: "a".repeat(64),
    document: {
      format: "autospine-dynamic-viewport-fit", format_version: 1,
      source: {
        kind: "sampled_attachment_geometry", evidence_sha256: "b".repeat(64),
        sample_count: sampleCount, geometry_item_count: sampleCount * 20,
        point_count: sampleCount * 80,
      },
      viewport: { width: 1024, height: 1024 },
      margin_px: { left: 32, right: 32, top: 32, bottom: 32 },
      motion_envelope: {
        min_xy: [-100, -100], max_xy: [1100, 1100], size: [1200, 1200],
        center_xy: [500, 500],
      },
      transform: {
        uniform_scale: 0.8, translation_xy: [112, 112],
        equation: "output_xy=source_xy*uniform_scale+translation_xy",
      },
      fitted_envelope: {
        min_xy: [32, 32], max_xy: [992, 992], size: [960, 960],
        center_xy: [512, 512],
      },
      fit_status: "fitted",
      profile: {
        id: "dynamic-viewport-fit", version: "1.0.0",
        config: {
          transform: "output_xy=source_xy*uniform_scale+translation_xy",
          scale_policy: "free-uniform-contain-and-center",
          numeric_precision_decimals: 12, fit_tolerance_px: 0.000001,
          max_sample_count: 65536, max_geometry_item_count: 262144,
          max_point_count: 2000000,
        },
      },
      semantics: {
        scope: "dynamic-viewport-fit-candidate-only", authority: "none",
        source_canvas_containment_required: false,
        source_canvas_overflow_is_rig_structural_failure: false,
        rig_binding_changed: false, human_decision_emitted: false,
        review_revision_written: false, visual_quality_claimed: false,
        continuous_time_safety_claimed: false,
        runtime_equivalence_claimed: false, release_authority_claimed: false,
      },
      status: "candidate_only",
      release_gate: {
        status: "blocked", reason_codes: [
          "candidate_has_no_review_authority",
          "sampled_envelope_is_not_continuous_time_proof",
          "runtime_visual_review_required",
        ],
      },
    },
  };
}

export function indeterminateDynamicViewportEnvelope(sampleCount = 81) {
  const envelope = dynamicViewportEnvelope(sampleCount);
  envelope.document.margin_px = { left: 0, right: 0, top: 0, bottom: 0 };
  envelope.document.motion_envelope = {
    min_xy: [-1_000_000_000, 1],
    max_xy: [-1_000_000_000, 1.000000001],
    size: [0, 0.000000001], center_xy: [-1_000_000_000, 1.0000000005],
  };
  envelope.document.transform = {
    uniform_scale: 1_023_999_999_999.9999,
    translation_xy: [1.0239999999999999e21, -1_023_999_999_999.9999],
    equation: "output_xy=source_xy*uniform_scale+translation_xy",
  };
  envelope.document.fitted_envelope = {
    min_xy: [0, 0], max_xy: [0, 1024.000122070312],
    size: [0, 1024.000122070312], center_xy: [0, 512.000061035156],
  };
  envelope.document.fit_status = "indeterminate";
  return envelope;
}

export function regionRebindEnvelope(entry) {
  const current = rebindRow("1", "forearm.left", "current", 0, 217, 157.3, 1);
  const proposed = rebindRow("2", "upper-arm.left", "parent", 1, 38, 25.5, 2);
  return {
    candidate_sha256: "f".repeat(64),
    document: {
      format: "autospine-region-rebind-candidates", format_version: 1,
      project_id: entry.package.project_id,
      source: {
        rig_sha256: entry.technical.report.source.p3.rig_sha256,
        motion_sha256: entry.technical.report.source.p9.motion_instance_v2_sha256,
        motion_samples_sha256: "7".repeat(64),
        motion_sample_count: entry.result.schedule.sample_count,
        attachment_id: "layer-007-handwear-l", slot_id: "slot-handwear-l",
        current_bone_id: "forearm.left", candidate_bone_ids_sha256: "8".repeat(64),
        analyzer_profile_sha256: "9".repeat(64),
      },
      analyzer: {
        id: "sampled-region-rebind-analyzer", version: "1.0.0",
        config: {
          geometry_source: "region-corner-envelope",
          default_candidate_scope: "current-direct-parent-and-children",
          explicit_candidate_scope: "one-hop-same-chain-only",
          sample_pose_space: "setup-local-bone-rotation-plus-root-translation",
          motion_metric: "root-compensated-corner-displacement",
          recommendation_ranking: [
            "setup-subtree-segment-coverage-descending",
            "root-compensated-centroid-rms",
            "root-compensated-maximum-vertex-motion",
            "viewport-overflow-sample-count-diagnostic",
            "viewport-maximum-overflow-diagnostic", "bone-id",
          ],
          minimum_relative_motion_improvement: 0.05,
          rank_tie_relative_tolerance: 0.01,
          setup_reconstruction_tolerance_px: 1e-7,
          numeric_precision_decimals: 9,
          viewport_policy: "diagnostic-only-free-camera-compatible",
          recommendation_gate: "one-hop-parent-with-increased-region-envelope-chain-coverage-and-motion-improvement",
        },
      },
      semantics: {
        scope: "sampled-region-rebind-candidate-only", authority: "none",
        human_decision_emitted: false, override_written: false,
        automatic_application_performed: false, setup_reconstruction_claimed: true,
        sampled_motion_evidence_claimed: true,
        geometry_basis: "region-corner-envelope-not-alpha-visible-pixels",
        viewport_overflow_is_correctness_gate: false,
        continuous_time_safety_claimed: false, visual_quality_claimed: false,
        seam_safety_claimed: false, release_authority: false,
      },
      candidates: [current, proposed],
      recommendation: {
        status: "recommended", candidate_id: proposed.candidate_id,
        from_bone_id: "forearm.left", to_bone_id: "upper-arm.left",
        relative_motion_improvement: 0.318095345,
        reason_codes: [
          "increased_setup_subtree_segment_coverage",
          "lower_root_compensated_motion_extent", "one_hop_same_chain",
          "reduced_viewport_overflow_diagnostic",
        ],
        authority: "none", requires_explicit_review: true,
      },
      status: "candidate_only",
    },
  };
}

function rebindRow(digit, boneId, relationship, hop, failures, maximum, coverage) {
  return {
    candidate_id: `region-rebind-${digit.repeat(64)}`,
    bone_id: boneId, relationship, hop_distance: hop,
    metrics: {
      sample_count: 81, fk_status: "passed",
      setup_reconstruction_max_error_px: 0,
      root_compensated_centroid_motion_rms_px: relationship === "current" ? 110 : 75,
      root_compensated_max_vertex_motion_px: relationship === "current" ? 190 : 130,
      normalized_centroid_motion_rms: relationship === "current" ? 0.4 : 0.2728,
      normalized_max_vertex_motion: relationship === "current" ? 0.7 : 0.48,
      setup_subtree_segment_coverage_count: coverage,
      setup_subtree_segment_ids_fully_inside_region: coverage === 1
        ? ["forearm.left"] : ["forearm.left", "upper-arm.left"],
      setup_pivot_distance_to_bone_origin_px: 12,
      setup_pivot_distance_to_bone_endpoint_px: 30,
      viewport_overflow_sample_count: failures,
      viewport_overflow_vertex_count: failures * 2,
      max_viewport_overflow_px: maximum,
      sampled_envelope_xyxy: [20, -maximum, 1050, 900],
    },
    evidence_sha256: digit.repeat(64),
  };
}
