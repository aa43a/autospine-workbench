"use strict";

import {
  digestValue, exactCopy, exactFields, finiteNumber, integer, sameJson,
} from "./body-sway-probe-contract-utils.js";

const DOCUMENT_FIELDS = [
  "format", "format_version", "source", "viewport", "margin_px",
  "motion_envelope", "transform", "fitted_envelope", "fit_status",
  "profile", "semantics", "status", "release_gate",
];
const SEMANTICS = Object.freeze({
  scope: "dynamic-viewport-fit-candidate-only", authority: "none",
  source_canvas_containment_required: false,
  source_canvas_overflow_is_rig_structural_failure: false,
  rig_binding_changed: false, human_decision_emitted: false,
  review_revision_written: false, visual_quality_claimed: false,
  continuous_time_safety_claimed: false, runtime_equivalence_claimed: false,
  release_authority_claimed: false,
});
const GATE = Object.freeze({
  status: "blocked",
  reason_codes: [
    "candidate_has_no_review_authority",
    "sampled_envelope_is_not_continuous_time_proof",
    "runtime_visual_review_required",
  ],
});
const FIT_STATUSES = new Set(["fitted", "indeterminate"]);
const FIT_TOLERANCE_PX = 1e-6;

export function normalizeDynamicViewportEnvelope(value, context) {
  if (value === null) return null;
  exactFields(value, ["candidate_sha256", "document"], "动态视口候选");
  const candidateSha256 = digestValue(value.candidate_sha256, "动态视口候选 SHA");
  const document = normalizeDocument(value.document, context);
  return { candidateSha256, document };
}

function normalizeDocument(value, context) {
  exactFields(value, DOCUMENT_FIELDS, "动态视口候选文档");
  if (value.format !== "autospine-dynamic-viewport-fit"
      || value.format_version !== 1 || value.status !== "candidate_only"
      || !FIT_STATUSES.has(value.fit_status)) throw new Error("动态视口候选合同无效");
  normalizeSource(value.source, context);
  const viewport = normalizeViewport(value.viewport);
  const margins = normalizeMargins(value.margin_px, viewport);
  const motion = normalizeEnvelope(value.motion_envelope, "动作包络");
  const fitted = normalizeEnvelope(value.fitted_envelope, "适配后包络");
  const transform = normalizeTransform(value.transform);
  normalizeProfile(value.profile);
  if (!sameJson(value.semantics, SEMANTICS) || !sameJson(value.release_gate, GATE)) {
    throw new Error("动态视口候选越过无权威边界");
  }
  requireFit(motion, fitted, transform, viewport, margins, value.fit_status);
  return exactCopy(value);
}

function normalizeSource(value, context) {
  exactFields(value, [
    "kind", "evidence_sha256", "sample_count", "geometry_item_count",
    "point_count",
  ], "动态视口来源");
  if (value.kind !== "sampled_attachment_geometry") {
    throw new Error("P10.2 动态视口必须来自采样附件几何");
  }
  digestValue(value.evidence_sha256, "动态视口证据 SHA");
  integer(value.sample_count, 1, "动态视口采样数", 65536);
  integer(value.geometry_item_count, 1, "动态视口几何项", 262144);
  integer(value.point_count, 1, "动态视口点数", 2000000);
  if (context?.result && value.sample_count !== context.result.schedule.sample_count) {
    throw new Error("动态视口采样计划与 P10.2 不一致");
  }
}

function normalizeViewport(value) {
  exactFields(value, ["width", "height"], "动态视口输出尺寸");
  const width = bounded(value.width, 1, 1e6, "动态视口宽度");
  const height = bounded(value.height, 1, 1e6, "动态视口高度");
  return { width, height };
}

function normalizeMargins(value, viewport) {
  exactFields(value, ["left", "right", "top", "bottom"], "动态视口边距");
  const result = Object.fromEntries(Object.keys(value).map((field) => [
    field, bounded(value[field], 0, 1e6, `动态视口 ${field} 边距`),
  ]));
  if (result.left + result.right >= viewport.width
      || result.top + result.bottom >= viewport.height) {
    throw new Error("动态视口边距没有留下有效区域");
  }
  return result;
}

function normalizeEnvelope(value, label) {
  exactFields(value, ["min_xy", "max_xy", "size", "center_xy"], label);
  const minimum = point(value.min_xy, `${label}最小值`);
  const maximum = point(value.max_xy, `${label}最大值`);
  const size = point(value.size, `${label}尺寸`, 0);
  const center = point(value.center_xy, `${label}中心`);
  if (minimum[0] > maximum[0] || minimum[1] > maximum[1]
      || !near(size[0], maximum[0] - minimum[0])
      || !near(size[1], maximum[1] - minimum[1])
      || !near(center[0], (minimum[0] + maximum[0]) / 2)
      || !near(center[1], (minimum[1] + maximum[1]) / 2)) {
    throw new Error(`${label}几何关系无效`);
  }
  return { minimum, maximum, size, center };
}

function normalizeTransform(value) {
  exactFields(value, ["uniform_scale", "translation_xy", "equation"], "动态视口变换");
  const scale = bounded(value.uniform_scale, Number.MIN_VALUE, 1e15, "动态视口缩放");
  const translation = point(value.translation_xy, "动态视口平移", -1e24, 1e24);
  if (value.equation !== "output_xy=source_xy*uniform_scale+translation_xy") {
    throw new Error("动态视口变换方程无效");
  }
  return { scale, translation };
}

function normalizeProfile(value) {
  exactFields(value, ["id", "version", "config"], "动态视口算法");
  const config = exactFields(value.config, [
    "transform", "scale_policy", "numeric_precision_decimals",
    "fit_tolerance_px", "max_sample_count", "max_geometry_item_count",
    "max_point_count",
  ], "动态视口算法参数");
  if (value.id !== "dynamic-viewport-fit" || value.version !== "1.0.0"
      || config.transform !== "output_xy=source_xy*uniform_scale+translation_xy"
      || config.scale_policy !== "free-uniform-contain-and-center"
      || config.numeric_precision_decimals !== 12 || config.fit_tolerance_px !== 1e-6
      || config.max_sample_count !== 65536 || config.max_geometry_item_count !== 262144
      || config.max_point_count !== 2000000) throw new Error("动态视口算法 profile 无效");
}

function requireFit(motion, fitted, transform, viewport, margin, fitStatus) {
  for (const axis of [0, 1]) {
    const expectedMin = motion.minimum[axis] * transform.scale + transform.translation[axis];
    const expectedMax = motion.maximum[axis] * transform.scale + transform.translation[axis];
    if (!near(fitted.minimum[axis], expectedMin, 1e-5)
        || !near(fitted.maximum[axis], expectedMax, 1e-5)) {
      throw new Error("动态视口候选与变换不一致");
    }
  }
  const contained = fitted.minimum[0] >= margin.left - FIT_TOLERANCE_PX
    && fitted.minimum[1] >= margin.top - FIT_TOLERANCE_PX
    && fitted.maximum[0] <= viewport.width - margin.right + FIT_TOLERANCE_PX
    && fitted.maximum[1] <= viewport.height - margin.bottom + FIT_TOLERANCE_PX;
  if ((fitStatus === "fitted") !== contained) {
    throw new Error("动态视口适配状态与动作包络不一致");
  }
}

function point(value, label, minimum = -1e9, maximum = 2e9) {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label}无效`);
  return value.map((item) => bounded(item, minimum, maximum, label));
}

function bounded(value, minimum, maximum, label) {
  finiteNumber(value, label);
  if (value < minimum || value > maximum) throw new Error(`${label}超出范围`);
  return value;
}

function near(left, right, tolerance = 1e-8) {
  return Math.abs(left - right) <= tolerance * Math.max(1, Math.abs(left), Math.abs(right));
}
