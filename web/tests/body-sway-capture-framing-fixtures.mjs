function bounds(minX, minY, maxX, maxY) {
  return {
    min_xy: [minX, minY], max_xy: [maxX, maxY],
    size: [maxX - minX, maxY - minY],
    center_xy: [(minX + maxX) / 2, (minY + maxY) / 2],
  };
}

function witness(tick, attachmentId, vertexIndex, x, y) {
  return { tick, attachment_id: attachmentId, vertex_index: vertexIndex, point_xy: [x, y] };
}

function envelope(kind, canvas, runtime, tick, digit) {
  return {
    sample_count: kind === "setup" ? 1 : 81,
    attachment_sample_count: kind === "setup" ? 20 : 1620,
    point_count: kind === "setup" ? 80 : 6480,
    evidence_sha256: digit.repeat(64),
    bounds_canvas: canvas,
    bounds_runtime: runtime,
    extrema_witnesses: {
      left: witness(tick, `layer-${kind}-left`, 0, canvas.min_xy[0], canvas.center_xy[1]),
      right: witness(tick, `layer-${kind}-right`, 1, canvas.max_xy[0], canvas.center_xy[1]),
      top: witness(tick, `layer-${kind}-top`, 2, canvas.center_xy[0], canvas.min_xy[1]),
      bottom: witness(tick, `layer-${kind}-bottom`, 3, canvas.center_xy[0], canvas.max_xy[1]),
    },
  };
}

export function captureFramingEnvelope(entry) {
  const setup = envelope(
    "setup", bounds(100, 100, 900, 950), bounds(100, 74, 900, 924), 0, "1",
  );
  const base = envelope(
    "base", bounds(-100, -100, 1100, 1100), bounds(-100, -76, 1100, 1124),
    1_950_000, "2",
  );
  const combined = envelope(
    "combined", bounds(-120, -110, 1120, 1110), bounds(-120, -86, 1120, 1134),
    2_400_000, "3",
  );
  const union = Object.fromEntries(Object.entries(combined.extrema_witnesses).map(
    ([side, value]) => [side, { envelope_kind: "combined", ...value }],
  ));
  return {
    candidate_sha256: "8".repeat(64),
    document: {
      format: "autospine-capture-framing-candidate", format_version: 1,
      project_id: entry.package.project_id, clip_id: entry.package.clip_id,
      source: {
        package_id: entry.package.package_id,
        body_sway_probe_report_sha256: entry.report_sha256,
        dynamic_viewport_fit_sha256: entry.dynamic_viewport.candidate_sha256,
        tick_schedule_sha256: entry.result.schedule.tick_schedule_sha256,
        current_p10_1_head: {
          candidate_sha256: entry.candidate_sha256,
          decision_sha256: entry.history.head_decision_sha256,
          revision: entry.history.current_revision,
        },
        capture_framing_profile_sha256: "7".repeat(64),
        layer_manifest_sha256: entry.technical.report.source.layer_manifest_sha256,
        p3: structuredClone(entry.technical.report.source.p3),
        p5: structuredClone(entry.technical.report.source.p5),
        p9: structuredClone(entry.technical.report.source.p9),
      },
      timing: structuredClone(entry.technical.report.timing),
      coordinate_spaces: {
        envelope_space: "rig-canvas-top-left-y-down",
        world_viewport_space: "spine-world-bottom-left-y-up",
        canvas_height: entry.preview.canvas.height,
        transform_id: "rig-canvas-y-down-to-spine-world-y-up-v1",
      },
      envelopes: { setup, base, combined },
      union_envelope_canvas: structuredClone(combined.bounds_canvas),
      union_envelope_runtime: structuredClone(combined.bounds_runtime),
      union_extrema_witnesses: union,
      capture_viewport: {
        width: 640, height: 640, device_pixel_ratio: 1,
        margin_px: { left: 32, right: 32, top: 32, bottom: 32 },
      },
      proposed_world_viewport: {
        x: -188.888888889, y: -164.888888889,
        width: 1377.777777778, height: 1377.777777778,
      },
      coverage: { setup: true, base: true, combined: true },
      compiler: {
        id: "capture-framing-candidate-compiler", version: "1.0.0", config: {},
      },
      compiler_sha256: "6".repeat(64),
      semantics: {
        authority: "none", human_decision_emitted: false, release_authority: false,
      },
      status: "candidate_only",
      release_gate: { status: "blocked", reason_codes: ["human_review_required"] },
    },
    history: {
      current_revision: 0, head_decision_sha256: null, action: null, status: null,
    },
  };
}
