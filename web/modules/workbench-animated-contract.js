"use strict";

import { automationEndpoint } from "./workbench-automation-contract.js";

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const OPTION_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
const SHA = /^[0-9a-f]{64}$/;
const STATES = new Set(["pending", "running", "succeeded", "needs_review", "blocked", "failed", "canceled"]);
export const animatedEndpoint = (project) => `${automationEndpoint(project)}/animated`;
export function animatedJobEndpoint(project, job) {
  if (!/^job-[0-9a-f]{32}$/.test(job || "")) throw new Error("invalid_job");
  return `${animatedEndpoint(project)}/jobs/${job}`;
}
export function animatedLayerTarget(id, context) {
  if (context.layerIds?.includes(id)) return id;
  const source = /^(layer-\d{3})(?:--[A-Za-z0-9._-]+)?$/.exec(id || "")?.[1];
  if (!source) return null;
  const matches = (context.layerIds || []).filter((candidate) => candidate.startsWith(`${source}-`));
  return matches.length === 1 ? matches[0] : null;
}
function items(rows) {
  if (!Array.isArray(rows) || rows.some((row) => !row || typeof row.id !== "string"
    || typeof row.reason_code !== "string")) throw new Error("invalid_review_items");
}
export function readAnimatedOverview(value, context) {
  if (value?.schema !== "autospine.animated-overview/v1" || value.project_id !== context.projectId
    || value.resolved_project_sha256 !== context.resolvedSha) throw new Error("project_snapshot_stale");
  if (typeof value.can_build !== "boolean" || !Array.isArray(value.clips)
    || value.clips.some((clip) => !ID.test(clip.id) || typeof clip.label !== "string")
    || new Set(value.clips.map((clip) => clip.id)).size !== value.clips.length) throw new Error("invalid_overview");
  items(value.review_items);
  if (value.binding_review) {
    if (!SHA.test(value.input_identity_sha256 || "") || !Array.isArray(value.binding_review.bindings)
      || !Array.isArray(value.binding_review.records)) throw new Error("invalid_binding_review");
    for (const binding of value.binding_review.bindings) {
      if (!ID.test(binding.layer_id) || !Array.isArray(binding.options)
        || binding.options.some((option) => !OPTION_ID.test(option.id) || !Array.isArray(option.bone_ids))) {
        throw new Error("invalid_binding_review");
      }
    }
  }
  return value;
}
export function readAnimatedJob(value, context, expectedId = null) {
  animatedJobEndpoint(context.projectId, value?.job_id);
  if (value.schema !== "autospine.animated-web-job/v1" || value.authority !== "none"
    || value.project_id !== context.projectId || !STATES.has(value.status)
    || expectedId && value.job_id !== expectedId) throw new Error("invalid_job");
  if (value.progress !== undefined && (!Array.isArray(value.progress)
    || value.progress.some((step) => !step || !STATES.has(step.status)))) throw new Error("invalid_job_progress");
  if (value.run) {
    const run = value.run;
    if (run.schema !== "autospine.animated-pipeline-run/v1" || !STATES.has(run.status)
      || typeof run.run_id !== "string" || typeof run.preview_available !== "boolean"
      || !Array.isArray(run.steps) || run.steps.some((step) => !STATES.has(step.status))) throw new Error("invalid_run");
    const source = run.source_addresses?.resolved_project_sha256 ?? run.resolved_project_sha256;
    if (source !== context.resolvedSha || run.project_id !== context.projectId) throw new Error("project_snapshot_stale");
    if (run.authority && run.authority !== "none") throw new Error("invalid_authority");
    items(run.review_items);
  }
  return value;
}

const REASONS = {
  animated_binding_completion_invalid: "简单绑定候选升级未完成；请检查来源是否完整，原复核记录保持不变。",
  animated_binding_profile_unsupported: "当前绑定候选版本不支持此更新，请保留来源并检查版本。",
  animated_source_missing: "尚无可用的骨架与绑定源，请先完成关节和结构准备。",
  animated_source_ambiguous: "存在多个可用绑定源，需要明确当前采用的项目来源。",
  animated_source_stale: "主项目已有新校正，请在本区同步已保存校正，再构建动画候选。",
  animated_rebase_conflict: "同步期间项目来源已变化，请刷新后检查新的同步内容。",
  animated_review_conflict: "复核来源已变化，请刷新后检查当前校正，再重新提交。",
  animated_rebase_invalid: "无法验证当前校正与动画来源，请刷新并检查来源一致性。",
  animated_rebase_unsupported: "当前校正包含暂不支持同步的内容，请检查下方说明。",
  animated_source_mismatch: "已注册来源与当前项目图层不匹配，请重新检查项目来源。",
  animated_clip_unsupported: "当前结构不支持所选动作，请选择其他白名单动作。",
  animated_no_eligible_mesh: "尚无满足条件的加权网格，请复核图层绑定。",
  animated_geometry_failed: "网格几何检查未通过，请复核绑定和结构。",
  animated_review_required: "动画候选已生成，仍需处理以下复核项。",
  animated_input_changed: "项目输入已变化，请刷新后重新构建。",
  cross_layer_seam_review_required: "跨图层接缝尚需复核，请检查动作极值处是否开裂或重叠。",
  rigid_context_unreviewed: "此图层仅作为身体参照，尚未确认正式绑定。",
  binding_selection_required: "请为此图层选择合适的绑定方案并保存。",
  bilateral_mesh_pending: "此层含左右两侧区域，需要分区复核后生成网格。",
  project_snapshot_stale: "项目已变化，请刷新后重新构建。",
  animated_binding_review_required: "请检查图层绑定；未确认的图层保留为身体参照。",
  binding_review_required: "请检查图层绑定并保存复核。",
  joint_review_required: "请先复核关节并保存项目校正。",
  skeleton_review_required: "请先复核骨架与关节。",
  mesh_review_required: "网格需要复核，当前输出仍是候选。",
  motion_unsupported: "当前结构暂不支持这个动作。",
  pipeline_interrupted: "上次构建被中断，请重新构建以恢复。",
  pipeline_canceled: "构建已取消。",
};
export function animatedReason(code) {
  return REASONS[code] || "请查看待复核项或下载包中的 QA 报告。";
}
