"use strict";

import { projectIdentity } from "./workbench-automation-contract.js";
import { animatedEndpoint, animatedReason } from "./workbench-animated-contract.js";
import { createRigPlanView, RIG_STRATEGIES } from "./workbench-rig-plan-view.js";
import { readRigReadiness } from "./workbench-rig-readiness.js";
const SHA = /^[a-f0-9]{64}$/;
const FAILURES = {
  animated_source_changed: animatedReason('animated_source_changed'),
  animated_source_invalid: animatedReason('animated_source_invalid'),
  project_rig_plan_dependency_missing: "缺少图像分析依赖，请安装项目的可选分析环境后重试。",
  project_rig_plan_analysis_failed: "图层图像或骨骼证据无法完成分析，请检查输入素材。",
  animated_review_conflict: "来源已变化，请刷新后重新分析。",
  animated_source_stale: "请先同步已保存校正，再分析当前来源。",
};
export function readRigPlan(value, context, input) {
  if (value?.schema !== "autospine.project-rig-plan-status/v1" || value.project_id !== context.projectId
    || value.input_identity_sha256 !== input || !SHA.test(input) || value.authority !== "none"
    || !["missing", "ready"].includes(value.status)) throw new Error("规划来源已变化，请刷新后重新分析。");
  if (value.status === "missing") {
    if (value.plan || value.plan_sha256 || value.visual || value.readiness) throw new Error("规划响应不完整。");
    return value;
  }
  const plan = value.plan;
  if (!SHA.test(value.plan_sha256) || plan?.schema !== "autospine.rig-plan/v1" || plan.authority !== "none"
    || plan.production_authorized !== false || plan.status !== "needs_review" || !Array.isArray(plan.layers)
    || !Array.isArray(plan.scope) || plan.scope.length !== plan.layers.length
    || new Set(plan.scope).size !== plan.scope.length
    || plan.layers.some((r, i) => r.layer_id !== plan.scope[i] || typeof r.name !== "string" || !Object.hasOwn(RIG_STRATEGIES, r.strategy)
      || !Number.isInteger(r.evidence?.component_count) || r.evidence.component_count < 0 || !Array.isArray(r.evidence.bone_alpha_samples)
      || r.evidence.bone_alpha_samples.some((s) => typeof s.bone_id !== "string" || !Number.isInteger(s.samples) || s.samples < 1
        || !Number.isInteger(s.opaque_samples) || s.opaque_samples < 0 || s.opaque_samples > s.samples)
      || !Array.isArray(r.reason_codes) || r.reason_codes.some((s) => typeof s !== "string") || typeof r.next_action !== "string")) throw new Error("规划响应不完整。");
  if (value.visual) {
    const v = value.visual;
    if (!Array.isArray(v.canvas) || v.canvas.length !== 2 || v.canvas.some(n => !Number.isInteger(n) || n <= 0)
      || v.composite_url !== `/api/projects/${encodeURIComponent(context.projectId)}/composite?source=${input}`
      || !Array.isArray(v.layers) || v.layers.length !== plan.scope.length
      || v.layers.some((row, i) => row.layer_id !== plan.scope[i] || !Array.isArray(row.bbox) || row.bbox.length !== 4
        || row.bbox.some(n => !Number.isFinite(n)) || row.bbox[0] > row.bbox[2] || row.bbox[1] > row.bbox[3])) throw new Error("规划可视化来源无效。");
  }
  readRigReadiness(value.readiness, plan, input, value.plan_sha256);
  if (value.readiness?.schema === 'autospine.rig-plan-readiness/v2' && value.readiness.resolved_project_sha256 !== context.resolvedSha) throw Error('已保存语义来源已变化。');
  return value;
}
export function createWorkbenchRigPlan(document, hooks, options = {}) {
  let identity = null, input = null, generation = 0, model = {}, result = null, busy = false, error = "", loaded = false;
  let autoEnabled = options.autoAnalyze ?? true, autoAttempted = false;
  const view = options.view || createRigPlanView(document, { analyze, setAuto, locate: hooks.locate });
  const context = () => hooks.context();
  const editable = () => model.preparationEditable && !context().dirty && !context().saving && !context().loading;
  const current = (token) => token === generation && identity === projectIdentity(context());
  function render() {
    const show = Boolean(identity && input);
    view.render({ visible: show, busy, canAnalyze: show && editable() && !busy, canLocate: editable() && !busy,
      autoEnabled, visual: editable() && !busy ? result?.visual || null : null,
      readiness: editable() && !busy ? result?.readiness || null : null,
      layers: editable() && !busy ? result?.plan?.layers || [] : [],
      message: error || (busy ? "正在分析全角色图层，请稍候…" : !editable() ? "请先完成当前操作并保存或撤销编辑，再查看规划。"
        : result?.status === "ready" ? `已分析 ${result.plan.layers.length} 个源图层；规划未改变任何绑定决定。`
        : "尚未生成当前来源的规划。点击分析可检查全角色图层。") });
  }
  function sync(value) {
    model = value;
    const next = projectIdentity(context()), nextInput = SHA.test(value.inputIdentitySha || "") ? value.inputIdentitySha : null;
    if (next !== identity || nextInput !== input) {
      generation++; identity = next; input = nextInput;
      result = null; busy = false; loaded = false; autoAttempted = false; error = "";
    }
    render();
    if (identity && input && editable() && !loaded && !busy) void request(false);
    else maybeAuto();
  }
  function maybeAuto() {
    if (autoEnabled && !autoAttempted && !busy && editable() && result?.status === "missing" && !error) {
      autoAttempted = true; void request(true);
    }
  }
  function setAuto(enabled) { autoEnabled = Boolean(enabled); render(); maybeAuto(); }
  async function request(create) {
    if (!identity || !input || !editable() || busy) return;
    const token = generation, saved = { ...context() }, source = input;
    busy = true; loaded = true; error = ""; render();
    if (create) { autoAttempted = true; hooks.busyChanged?.(true); }
    try {
      const options = create ? { method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha, expected_input_sha256: source }) } : { cache: "no-store" };
      const value = await hooks.apiRequest(`${animatedEndpoint(saved.projectId)}/rig-plan`, options);
      if (current(token)) result = readRigPlan(value, saved, source);
    } catch (failure) { if (current(token)) { result = null; error = FAILURES[failure.payload?.reason_code] || failure.message || "规划分析失败，请重试。"; } }
    finally {
      if (current(token)) { busy = false; if (create) hooks.busyChanged?.(false); render(); maybeAuto(); }
    }
  }
  async function analyze() { await request(true); }
  return { element: view.element, sync, analyze, setAuto, dispose() { generation++; view.dispose?.(); } };
}
