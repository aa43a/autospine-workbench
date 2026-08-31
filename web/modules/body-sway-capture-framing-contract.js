"use strict";

import {
  digestValue, exactCopy, exactFields, finiteNumber, integer, safeId, sameJson,
} from "./body-sway-probe-contract-utils.js";

const ENVELOPE_KINDS = ["setup", "base", "combined"];
const SIDES = ["left", "right", "top", "bottom"];
const REASONS = Object.freeze({
  accept: "human-approved-automatic-capture-framing-v1",
  reject: "human-rejected-capture-framing-v1",
  unobservable: "human-marked-capture-framing-unobservable-v1",
});

export function normalizeCaptureFramingEnvelope(value, context) {
  if (value === null) return null;
  exactFields(value, ["candidate_sha256", "document", "history"], "自动取景候选");
  const candidateSha256 = digestValue(value.candidate_sha256, "自动取景候选 SHA");
  const document = normalizeDocument(value.document, context);
  const history = normalizeHistory(value.history);
  return { candidateSha256, document, history };
}

export function captureFramingSubmission(entry, action) {
  const framing = entry?.captureFraming;
  if (!framing || !Object.hasOwn(REASONS, action)) {
    throw new Error("当前没有可提交的自动取景决定");
  }
  const sourceHead = framing.document.source.current_p10_1_head;
  return {
    format: "autospine-capture-framing-submission",
    format_version: 1,
    intent: "capture-framing-human-review-v1",
    explicit_confirmation: true,
    package_id: entry.package.package_id,
    candidate_sha256: framing.candidateSha256,
    p10_1_head: exactCopy(sourceHead),
    base_revision: framing.history.currentRevision,
    previous_decision_sha256: framing.history.headDecisionSha256,
    action,
    reason_code: REASONS[action],
    world_viewport: action === "accept"
      ? exactCopy(framing.document.proposed_world_viewport) : null,
  };
}

function normalizeDocument(value, context) {
  exactFields(value, [
    "format", "format_version", "project_id", "clip_id", "source", "timing",
    "coordinate_spaces", "envelopes", "union_envelope_canvas",
    "union_envelope_runtime", "union_extrema_witnesses", "capture_viewport",
    "proposed_world_viewport", "coverage", "compiler", "compiler_sha256",
    "semantics", "status", "release_gate",
  ], "自动取景候选文档");
  if (value.format !== "autospine-capture-framing-candidate"
      || value.format_version !== 1 || value.status !== "candidate_only"
      || value.project_id !== context.packageRow.project_id
      || value.clip_id !== context.packageRow.clip_id) {
    throw new Error("自动取景候选身份无效");
  }
  normalizeSource(value.source, context);
  normalizeTiming(value.timing, context.report.timing);
  normalizeCoordinateSpaces(value.coordinate_spaces, context.preview.canvas.height);
  const captureViewport = normalizeCaptureViewport(value.capture_viewport);
  exactFields(value.envelopes, ENVELOPE_KINDS, "自动取景三域包络");
  for (const kind of ENVELOPE_KINDS) normalizeEnvelope(value.envelopes[kind], kind);
  normalizeBounds(value.union_envelope_canvas, "取景画布联合包络");
  normalizeBounds(value.union_envelope_runtime, "取景 Runtime 联合包络");
  normalizeUnionWitnesses(value.union_extrema_witnesses, value.timing.duration_ticks);
  const world = normalizeWorldViewport(value.proposed_world_viewport, captureViewport);
  exactFields(value.coverage, ENVELOPE_KINDS, "自动取景覆盖结果");
  if (ENVELOPE_KINDS.some((kind) => value.coverage[kind] !== true)) {
    throw new Error("自动取景没有覆盖完整三域动作");
  }
  digestValue(value.compiler_sha256, "自动取景算法 SHA");
  exactFields(value.compiler, ["id", "version", "config"], "自动取景算法");
  if (value.compiler.id !== "capture-framing-candidate-compiler") {
    throw new Error("自动取景算法身份无效");
  }
  if (value.semantics?.authority !== "none"
      || value.semantics?.human_decision_emitted !== false
      || value.semantics?.release_authority !== false
      || value.release_gate?.status !== "blocked") {
    throw new Error("自动取景候选越过人工复核边界");
  }
  return { ...exactCopy(value), proposed_world_viewport: world };
}

function normalizeSource(value, context) {
  exactFields(value, [
    "package_id", "body_sway_probe_report_sha256", "dynamic_viewport_fit_sha256",
    "tick_schedule_sha256", "current_p10_1_head", "capture_framing_profile_sha256",
    "layer_manifest_sha256", "p3", "p5", "p9",
  ], "自动取景来源");
  for (const field of [
    "package_id", "body_sway_probe_report_sha256", "dynamic_viewport_fit_sha256",
    "tick_schedule_sha256", "capture_framing_profile_sha256", "layer_manifest_sha256",
  ]) digestValue(value[field], `自动取景 ${field}`);
  exactFields(value.current_p10_1_head,
    ["candidate_sha256", "decision_sha256", "revision"], "自动取景 P10.1 来源");
  digestValue(value.current_p10_1_head.candidate_sha256, "P10.0 candidate SHA");
  digestValue(value.current_p10_1_head.decision_sha256, "P10.1 decision SHA");
  integer(value.current_p10_1_head.revision, 1, "P10.1 revision", 10000);
  const expectedHead = {
    candidate_sha256: context.candidateSha,
    decision_sha256: context.sourceReview.decision_sha256,
    revision: context.sourceReview.revision,
  };
  if (value.package_id !== context.packageRow.package_id
      || value.body_sway_probe_report_sha256 !== context.reportSha256
      || value.dynamic_viewport_fit_sha256 !== context.viewportFit.candidateSha256
      || value.tick_schedule_sha256 !== context.result.schedule.tick_schedule_sha256
      || !sameJson(value.current_p10_1_head, expectedHead)
      || value.layer_manifest_sha256 !== context.report.source.layer_manifest_sha256
      || !sameJson(value.p3, context.report.source.p3)
      || !sameJson(value.p5, context.report.source.p5)
      || !sameJson(value.p9, context.report.source.p9)) {
    throw new Error("自动取景候选与当前 P10.2 精确来源不一致");
  }
}

function normalizeTiming(value, expected) {
  exactFields(value, ["ticks_per_second", "duration_ticks", "loop"], "自动取景时序");
  if (!sameJson(value, expected)) throw new Error("自动取景时序与 P10.2 不一致");
}

function normalizeCoordinateSpaces(value, canvasHeight) {
  exactFields(value, [
    "envelope_space", "world_viewport_space", "canvas_height", "transform_id",
  ], "自动取景坐标系");
  if (value.envelope_space !== "rig-canvas-top-left-y-down"
      || value.world_viewport_space !== "spine-world-bottom-left-y-up"
      || value.transform_id !== "rig-canvas-y-down-to-spine-world-y-up-v1"
      || value.canvas_height !== canvasHeight) throw new Error("自动取景坐标系无效");
}

function normalizeCaptureViewport(value) {
  exactFields(value, ["width", "height", "device_pixel_ratio", "margin_px"], "采集画面");
  exactFields(value.margin_px, SIDES, "采集画面安全边距");
  if (value.width !== 640 || value.height !== 640 || value.device_pixel_ratio !== 1
      || SIDES.some((side) => value.margin_px[side] !== 32)) {
    throw new Error("自动取景采集规格无效");
  }
  return value;
}

function normalizeEnvelope(value, label) {
  exactFields(value, [
    "sample_count", "attachment_sample_count", "point_count", "evidence_sha256",
    "bounds_canvas", "bounds_runtime", "extrema_witnesses",
  ], `${label} 动作包络`);
  integer(value.sample_count, 1, `${label} 采样数`);
  integer(value.attachment_sample_count, 1, `${label} 附件采样数`);
  integer(value.point_count, 1, `${label} 顶点数`);
  digestValue(value.evidence_sha256, `${label} 证据 SHA`);
  normalizeBounds(value.bounds_canvas, `${label} 画布包络`);
  normalizeBounds(value.bounds_runtime, `${label} Runtime 包络`);
  exactFields(value.extrema_witnesses, SIDES, `${label} 责任点`);
  for (const side of SIDES) normalizeWitness(value.extrema_witnesses[side], false);
}

function normalizeUnionWitnesses(value, durationTicks) {
  exactFields(value, SIDES, "联合包络责任点");
  for (const side of SIDES) {
    const witness = normalizeWitness(value[side], true);
    if (witness.tick > durationTicks) throw new Error("自动取景责任点时刻超出动作");
  }
}

function normalizeWitness(value, union) {
  exactFields(value, union
    ? ["envelope_kind", "tick", "attachment_id", "vertex_index", "point_xy"]
    : ["tick", "attachment_id", "vertex_index", "point_xy"], "自动取景责任点");
  if (union && !ENVELOPE_KINDS.includes(value.envelope_kind)) {
    throw new Error("自动取景责任点域无效");
  }
  integer(value.tick, 0, "自动取景责任点时刻");
  safeId(value.attachment_id, "自动取景责任附件");
  integer(value.vertex_index, 0, "自动取景责任顶点");
  if (!Array.isArray(value.point_xy) || value.point_xy.length !== 2) {
    throw new Error("自动取景责任点坐标无效");
  }
  value.point_xy.forEach((item) => finiteNumber(item, "自动取景责任点坐标"));
  return value;
}

function normalizeBounds(value, label) {
  exactFields(value, ["min_xy", "max_xy", "size", "center_xy"], label);
  for (const field of ["min_xy", "max_xy", "size", "center_xy"]) {
    if (!Array.isArray(value[field]) || value[field].length !== 2) throw new Error(`${label}无效`);
    value[field].forEach((item) => finiteNumber(item, label));
  }
  const [minX, minY] = value.min_xy;
  const [maxX, maxY] = value.max_xy;
  if (minX > maxX || minY > maxY
      || !near(value.size[0], maxX - minX) || !near(value.size[1], maxY - minY)
      || !near(value.center_xy[0], (minX + maxX) / 2)
      || !near(value.center_xy[1], (minY + maxY) / 2)) throw new Error(`${label}几何无效`);
}

function normalizeWorldViewport(value, capture) {
  exactFields(value, ["x", "y", "width", "height"], "自动取景范围");
  const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key, finiteNumber(item, `自动取景 ${key}`),
  ]));
  if (result.width <= 0 || result.height <= 0
      || !near(result.width / result.height, capture.width / capture.height)) {
    throw new Error("自动取景范围无效");
  }
  return result;
}

function normalizeHistory(value) {
  exactFields(value, [
    "current_revision", "head_decision_sha256", "action", "status",
  ], "自动取景决定历史");
  integer(value.current_revision, 0, "自动取景 revision", 64);
  if (value.current_revision === 0) {
    if (value.head_decision_sha256 !== null || value.action !== null || value.status !== null) {
      throw new Error("自动取景空历史无效");
    }
  } else {
    digestValue(value.head_decision_sha256, "自动取景决定 SHA");
    if (!["accept", "adjust", "reject", "unobservable"].includes(value.action)
        || !["ready_for_temporary_preview_v2", "capture_framing_not_approved"]
          .includes(value.status)) throw new Error("自动取景决定历史无效");
  }
  return {
    currentRevision: value.current_revision,
    headDecisionSha256: value.head_decision_sha256,
    action: value.action,
    status: value.status,
  };
}

function near(left, right) {
  return Math.abs(left - right) <= 1e-7 * Math.max(1, Math.abs(left), Math.abs(right));
}
