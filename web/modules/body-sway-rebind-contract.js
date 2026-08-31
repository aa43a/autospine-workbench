"use strict";

import {
  digestValue, exactCopy, exactFields, finiteNumber, integer, safeId, sameJson,
} from "./body-sway-probe-contract-utils.js";

const DOCUMENT_FIELDS = [
  "format", "format_version", "project_id", "source", "analyzer",
  "semantics", "candidates", "recommendation", "status",
];
const SOURCE_FIELDS = [
  "rig_sha256", "motion_sha256", "motion_samples_sha256",
  "motion_sample_count", "attachment_id", "slot_id", "current_bone_id",
  "candidate_bone_ids_sha256", "analyzer_profile_sha256",
];
const CANDIDATE_FIELDS = [
  "candidate_id", "bone_id", "relationship", "hop_distance", "metrics",
  "evidence_sha256",
];
const METRIC_FIELDS = [
  "sample_count", "fk_status", "setup_reconstruction_max_error_px",
  "root_compensated_centroid_motion_rms_px",
  "root_compensated_max_vertex_motion_px", "normalized_centroid_motion_rms",
  "normalized_max_vertex_motion", "setup_subtree_segment_coverage_count",
  "setup_subtree_segment_ids_fully_inside_region",
  "setup_pivot_distance_to_bone_origin_px",
  "setup_pivot_distance_to_bone_endpoint_px",
  "viewport_overflow_sample_count", "viewport_overflow_vertex_count",
  "max_viewport_overflow_px", "sampled_envelope_xyxy",
];
const SEMANTICS = Object.freeze({
  scope: "sampled-region-rebind-candidate-only", authority: "none",
  human_decision_emitted: false, override_written: false,
  automatic_application_performed: false, setup_reconstruction_claimed: true,
  sampled_motion_evidence_claimed: true,
  geometry_basis: "region-corner-envelope-not-alpha-visible-pixels",
  viewport_overflow_is_correctness_gate: false,
  continuous_time_safety_claimed: false, visual_quality_claimed: false,
  seam_safety_claimed: false, release_authority: false,
});

export function normalizeRegionRebindEnvelopes(value, context) {
  if (!Array.isArray(value) || value.length > 64) {
    throw new Error("动作换绑候选数量无效");
  }
  const attachments = new Set();
  return value.map((raw) => {
    exactFields(raw, ["candidate_sha256", "document"], "动作换绑候选");
    const candidateSha256 = digestValue(raw.candidate_sha256, "动作换绑候选 SHA");
    const document = normalizeDocument(raw.document, context);
    const attachmentId = document.source.attachment_id;
    if (attachments.has(attachmentId)) throw new Error("动作换绑候选图层重复");
    attachments.add(attachmentId);
    return {
      candidateSha256, document, attachmentId,
      recommendation: exactCopy(document.recommendation),
    };
  });
}

function normalizeDocument(value, context) {
  exactFields(value, DOCUMENT_FIELDS, "动作换绑候选文档");
  if (value.format !== "autospine-region-rebind-candidates"
      || value.format_version !== 1 || value.status !== "candidate_only"
      || value.project_id !== context.packageRow.project_id) {
    throw new Error("动作换绑候选与当前项目不一致");
  }
  const source = normalizeSource(value.source, context);
  normalizeAnalyzer(value.analyzer);
  if (!sameJson(value.semantics, SEMANTICS)) throw new Error("动作换绑候选越过权限边界");
  if (!Array.isArray(value.candidates) || !value.candidates.length
      || value.candidates.length > 16) throw new Error("动作换绑骨集合无效");
  const candidates = value.candidates.map((row) => normalizeCandidate(row, source));
  const boneIds = candidates.map((row) => row.bone_id);
  if (!boneIds.includes(source.current_bone_id)
      || new Set(boneIds).size !== boneIds.length) throw new Error("动作换绑缺少当前骨");
  normalizeRecommendation(value.recommendation, source, candidates);
  return exactCopy(value);
}

function normalizeSource(value, context) {
  exactFields(value, SOURCE_FIELDS, "动作换绑来源");
  for (const field of [
    "rig_sha256", "motion_sha256", "motion_samples_sha256",
    "candidate_bone_ids_sha256", "analyzer_profile_sha256",
  ]) digestValue(value[field], `动作换绑 ${field}`);
  for (const field of ["attachment_id", "slot_id", "current_bone_id"]) {
    safeId(value[field], `动作换绑 ${field}`);
  }
  integer(value.motion_sample_count, 2, "动作换绑采样数", 65536);
  const expectedRig = context.report?.source?.p3?.rig_sha256;
  const expectedMotion = context.report?.source?.p9?.motion_instance_v2_sha256;
  if ((expectedRig && value.rig_sha256 !== expectedRig)
      || (expectedMotion && value.motion_sha256 !== expectedMotion)
      || (context.result && value.motion_sample_count !== context.result.schedule.sample_count)) {
    throw new Error("动作换绑来源与 P10.2 精确链不一致");
  }
  return value;
}

function normalizeAnalyzer(value) {
  exactFields(value, ["id", "version", "config"], "动作换绑算法");
  const config = exactFields(value.config, [
    "geometry_source", "default_candidate_scope", "explicit_candidate_scope",
    "sample_pose_space", "motion_metric", "recommendation_ranking",
    "minimum_relative_motion_improvement", "rank_tie_relative_tolerance",
    "setup_reconstruction_tolerance_px", "numeric_precision_decimals",
    "viewport_policy", "recommendation_gate",
  ], "动作换绑算法参数");
  if (value.id !== "sampled-region-rebind-analyzer" || value.version !== "1.0.0"
      || config.geometry_source !== "region-corner-envelope"
      || config.default_candidate_scope !== "current-direct-parent-and-children"
      || config.explicit_candidate_scope !== "one-hop-same-chain-only"
      || config.viewport_policy !== "diagnostic-only-free-camera-compatible"
      || config.minimum_relative_motion_improvement !== 0.05
      || config.rank_tie_relative_tolerance !== 0.01
      || config.setup_reconstruction_tolerance_px !== 1e-7
      || config.numeric_precision_decimals !== 9
      || !Array.isArray(config.recommendation_ranking)) {
    throw new Error("动作换绑算法 profile 无效");
  }
}

function normalizeCandidate(value, source) {
  exactFields(value, CANDIDATE_FIELDS, "动作换绑骨候选");
  if (!/^region-rebind-[0-9a-f]{64}$/.test(value.candidate_id)) {
    throw new Error("动作换绑 candidate ID 无效");
  }
  safeId(value.bone_id, "动作换绑目标骨");
  digestValue(value.evidence_sha256, "动作换绑证据 SHA");
  if (!["current", "parent", "child"].includes(value.relationship)
      || value.hop_distance !== (value.relationship === "current" ? 0 : 1)
      || (value.bone_id === source.current_bone_id) !== (value.relationship === "current")) {
    throw new Error("动作换绑骨关系无效");
  }
  normalizeMetrics(value.metrics, source.motion_sample_count);
  return value;
}

function normalizeMetrics(value, sampleCount) {
  exactFields(value, METRIC_FIELDS, "动作换绑指标");
  if (value.sample_count !== sampleCount || value.fk_status !== "passed") {
    throw new Error("动作换绑采样/FK 指标无效");
  }
  for (const field of METRIC_FIELDS.filter((field) => ![
    "sample_count", "fk_status", "viewport_overflow_sample_count",
    "viewport_overflow_vertex_count", "setup_subtree_segment_coverage_count",
    "setup_subtree_segment_ids_fully_inside_region", "sampled_envelope_xyxy",
  ].includes(field))) nonnegative(value[field], `动作换绑 ${field}`);
  for (const field of [
    "viewport_overflow_sample_count", "viewport_overflow_vertex_count",
    "setup_subtree_segment_coverage_count",
  ]) integer(value[field], 0, `动作换绑 ${field}`);
  if (!Array.isArray(value.setup_subtree_segment_ids_fully_inside_region)
      || value.setup_subtree_segment_ids_fully_inside_region.length
        !== value.setup_subtree_segment_coverage_count
      || value.setup_subtree_segment_ids_fully_inside_region.some((id) => !safeId(id, "覆盖骨"))) {
    throw new Error("动作换绑 setup 覆盖指标无效");
  }
  if (!Array.isArray(value.sampled_envelope_xyxy)
      || value.sampled_envelope_xyxy.length !== 4
      || value.sampled_envelope_xyxy.some((item) => !Number.isFinite(item))) {
    throw new Error("动作换绑包络无效");
  }
}

function normalizeRecommendation(value, source, candidates) {
  exactFields(value, [
    "status", "candidate_id", "from_bone_id", "to_bone_id",
    "relative_motion_improvement", "reason_codes", "authority",
    "requires_explicit_review",
  ], "动作换绑建议");
  const selected = candidates.find((row) => row.candidate_id === value.candidate_id);
  if (!selected || !["recommended", "keep_current", "ambiguous"].includes(value.status)
      || value.from_bone_id !== source.current_bone_id
      || value.to_bone_id !== selected.bone_id || value.authority !== "none"
      || value.requires_explicit_review !== true
      || !Array.isArray(value.reason_codes) || !value.reason_codes.length) {
    throw new Error("动作换绑建议无效");
  }
  nonnegative(value.relative_motion_improvement, "动作换绑改善率");
}

function nonnegative(value, label) {
  finiteNumber(value, label);
  if (value < 0) throw new Error(`${label}无效`);
  return value;
}
