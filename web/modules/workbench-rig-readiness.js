"use strict";

export const READINESS_REASONS = {
  no_opaque_alpha_support: "缺少可见像素，先检查源素材。",
  garment_semantics_review_required: "服装或物件语义仍不明确，先复核归属和拆分需要。",
  reviewed_partition_artifact_required: "需要已复核的像素分区；仅有多个连通域不能直接生成 Mesh。",
  mesh_coverage_and_deformation_review_required: "已有一个可检查的骨链选项；下一步检查覆盖、权重和动作变形。",
  disconnected_alpha_ownership_review_required: "存在多个分离区域，先复核各区域的像素归属。",
  mesh_chain_ambiguous: "有多个骨链方案，需要选择与图层结构一致的方案。",
  supported_mesh_chain_evidence_missing: "缺少受支持的骨链及可见像素证据。",
};
const TYPES = new Set(["weighted_mesh", "partition_mesh", "semantic_review"]);
const ACTIONS = new Set(["review_semantics_and_split_need", "review_partition_ownership", "review_binding_and_geometry"]);
export function readRigReadiness(value, plan, input, planSha) {
  if (value === undefined) return null;
  const rows = plan.layers.filter(row => TYPES.has(row.strategy));
  if (!value || value.schema !== "autospine.rig-plan-readiness/v1" || value.profile !== "garment-partition-readiness-v1"
    || value.input_identity_sha256 !== input || value.source_plan_sha256 !== planSha
    || value.authority !== "none" || value.production_authorized !== false || !Array.isArray(value.layers)
    || value.layers.length !== rows.length || value.layers.some((row, i) => row.layer_id !== rows[i].layer_id
      || row.strategy !== rows[i].strategy || !["blocked", "needs_review"].includes(row.status)
      || !ACTIONS.has(row.next_action) || !Array.isArray(row.reason_codes) || !row.reason_codes.length
      || row.reason_codes.some(code => !Object.hasOwn(READINESS_REASONS, code))
      || !Array.isArray(row.mesh_option_ids) || new Set(row.mesh_option_ids).size !== row.mesh_option_ids.length
      || row.mesh_option_ids.some(id => typeof id !== "string" || !id))) throw Error("服装与分区检查来源无效。");
  return value;
}
