"use strict";

const DISPOSITIONS = new Set([
  "single_option", "compare_options", "blocked_unobservable", "manual_required",
]);
const BASES = new Set([
  "only_complete_overlap_option",
  "largest_minimum_overlap_ratio_highlight_only",
  "source_evidence_unobservable",
  "manual_visual_comparison_required",
]);

function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}

function requireMetrics(value) {
  if (value === null) return null;
  if (!exactKeys(value, [
    "minimum_overlap_ratio_q1000000", "area_px", "error_radius_q1000_px",
  ]) || Object.values(value).some((row) => !Number.isInteger(row) || row < 0)) {
    throw new Error("自动建议指标无效");
  }
  return { ...value };
}

function normalizeSuggestion(raw, relationship) {
  const fields = [
    "relationship_id", "action", "option_id", "option_evidence_sha256",
    "highlight_option_id", "batch_eligible", "disposition", "selection_basis",
    "reason_codes", "metrics",
  ];
  if (!exactKeys(raw, fields) || raw.relationship_id !== relationship.relationship_id
      || !DISPOSITIONS.has(raw.disposition) || !BASES.has(raw.selection_basis)
      || typeof raw.batch_eligible !== "boolean" || !Array.isArray(raw.reason_codes)) {
    throw new Error("自动建议与 relationship 不一致");
  }
  const options = relationship.options.filter((row) => row.status === "candidate");
  const option = raw.option_id === null ? null
    : options.find((row) => row.option_id === raw.option_id);
  const highlighted = raw.highlight_option_id === null ? null
    : options.find((row) => row.option_id === raw.highlight_option_id);
  if (raw.disposition === "single_option"
      && (!option || raw.action !== null || !raw.batch_eligible
        || raw.option_evidence_sha256 !== option.evidence_sha256)
      || raw.disposition === "compare_options"
      && (raw.action !== null || raw.option_id !== null || !highlighted
        || raw.option_evidence_sha256 !== null || raw.batch_eligible)
      || raw.disposition === "blocked_unobservable"
      && (raw.action !== "unobservable" || raw.option_id !== null
        || raw.option_evidence_sha256 !== null || highlighted !== null)
      || raw.disposition === "manual_required"
      && (raw.action !== null || raw.option_id !== null || highlighted !== null)) {
    throw new Error("自动建议越过人工决定边界");
  }
  return { ...raw, reason_codes: [...raw.reason_codes], metrics: requireMetrics(raw.metrics) };
}

export function normalizeSeamReviewAssist(raw, candidateSha256, candidate) {
  const fields = [
    "format", "format_version", "profile_id", "candidate_sha256",
    "human_confirmation_required", "auto_fill_count", "manual_required_count",
    "suggestions",
  ];
  if (!exactKeys(raw, fields)
      || raw.format !== "autospine-seam-anchor-review-assist"
      || raw.format_version !== 1 || raw.profile_id !== "contact-overlap-strength-v1"
      || raw.candidate_sha256 !== candidateSha256
      || raw.human_confirmation_required !== true
      || !Number.isInteger(raw.auto_fill_count) || raw.auto_fill_count < 0
      || !Number.isInteger(raw.manual_required_count) || raw.manual_required_count < 0
      || !Array.isArray(raw.suggestions)
      || raw.suggestions.length !== candidate.relationships.length) {
    throw new Error("自动建议合同无效");
  }
  const suggestions = raw.suggestions.map((row, index) =>
    normalizeSuggestion(row, candidate.relationships[index]));
  const autoFill = suggestions.filter(
    (row) => row.action !== null || row.option_id !== null,
  ).length;
  const manual = suggestions.filter(
    (row) => ["compare_options", "manual_required"].includes(row.disposition),
  ).length;
  if (autoFill !== raw.auto_fill_count || manual !== raw.manual_required_count) {
    throw new Error("自动建议摘要无效");
  }
  return Object.freeze({ ...raw, suggestions });
}
