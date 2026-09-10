"use strict";

import { projectIdentity, ACTIVE_JOBS } from "./workbench-automation-contract.js";
import { animatedEndpoint } from "./workbench-animated-contract.js";
import { createPreparationView, preparationReason, preparationSuccess } from "./workbench-animated-preparation-view.js";
const STATES = new Set(["pending", "running", "needs_review", "succeeded", "blocked", "failed", "canceled"]);
const jointIds = value => Array.isArray(value) && value.every(id => typeof id === 'string' && id.length > 0)
  && new Set(value).size === value.length;
export function readPreparation(value, context, jobId = null) {
  const job = value?.schema === "autospine.input-preparation-job/v1";
  if ((!job && value?.schema !== "autospine.input-preparation-overview/v1") || value.authority !== "none"
    || value.project_id !== context.projectId || typeof value.source_registered !== "boolean"
    || (job ? value.expected_resolved_sha256 : value.resolved_project_sha256) !== context.resolvedSha) throw new Error("preparation_input_changed");
  if (job) {
    if (!/^job-[a-f0-9]{32}$/.test(value.job_id) || (jobId && jobId !== value.job_id) || !STATES.has(value.status)
      || !Array.isArray(value.progress) || value.progress.some((step) => typeof step.id !== "string" || !STATES.has(step.status))) throw new Error("invalid_preparation_job");
  } else if (!["ready", "runner_unavailable", "unsupported", "already_prepared"].includes(value.status) || typeof value.can_prepare !== "boolean") throw new Error("invalid_preparation_capability");
  if ((value.authored_joint_count !== undefined && (!Number.isSafeInteger(value.authored_joint_count) || value.authored_joint_count < 0))
    || (value.ignored_joint_ids !== undefined && !jointIds(value.ignored_joint_ids))
    || (value.unsupported_items !== undefined && !Array.isArray(value.unsupported_items))) throw new Error('invalid_preparation_migration');
  const result = value.result;
  if (result && ['imported_joint_ids', 'ignored_joint_ids'].some(key => result[key] !== undefined)
    && (!jointIds(result.imported_joint_ids) || !jointIds(result.ignored_joint_ids)
      || !Number.isSafeInteger(result.reviewed_joint_count) || result.reviewed_joint_count < 0 || result.reviewed_joint_count > 17
      || result.reviewed_joint_count !== result.imported_joint_ids.length
      || result.imported_joint_ids.some(id => result.ignored_joint_ids.includes(id)))) throw new Error('invalid_preparation_migration');
  return value;
}
export function createAnimatedPreparation(document, hooks, options = {}) {
  const schedule = options.schedule || setTimeout, unschedule = options.unschedule || clearTimeout;
  let identity = null, generation = 0, serial = 0, timer = null, capability = null, job = null;
  let visible = false, enabled = false, fetching = false, submitting = false, canceling = false, error = "", delivered = null, polls = 0;
  const view = options.view || createPreparationView(document, { start, refresh, cancel });
  const context = () => hooks.context();
  const current = (token) => token === generation && identity === projectIdentity(context());
  const editable = () => enabled && !context().dirty && !context().saving && !context().loading;
  const active = () => ACTIVE_JOBS.has(job?.status);
  const endpoint = () => `${animatedEndpoint(context().projectId)}/preparation`;
  const busy = () => fetching || submitting || active() || canceling;
  function stop() { if (timer !== null) unschedule(timer); timer = null; }
  function render() {
    let message = error || (fetching ? "正在检查来源准备条件…" : submitting ? "正在提交来源准备…" : active() ? "正在准备来源；进度查询不会重复运行模型。"
      : job?.source_registered ? preparationSuccess(job.result) : job?.status === "canceled" ? "来源准备已取消。"
      : job ? preparationReason(job.reason_code) : capability?.status === "ready"
        ? `可以准备来源。${capability.authored_joint_count ? `将保留 ${capability.authored_joint_count} 个已保存关节校正。` : ''}模型检测不会代替人工确认。`
      : preparationReason(capability?.reason_code || capability?.status));
    view.render({ visible, busy: busy(), canStart: visible && !job?.source_registered && editable() && capability?.can_prepare && capability.status === "ready" && !busy(),
      canCancel: active(), canceling: canceling || job?.cancel_requested, message, progress: job?.progress || [] });
  }
  function sync(model) {
    const next = projectIdentity(context());
    if (next !== identity) {
      generation++; serial++; stop(); identity = next; capability = job = delivered = null;
      fetching = submitting = canceling = false; error = ""; polls = 0;
    }
    visible = Boolean(identity && (model.sourceMissing || job?.source_registered)); enabled = Boolean(model.preparationEditable);
    if (!visible) { stop(); render(); return; }
    render(); if (!capability && !fetching && !error && editable()) void refresh();
  }
  async function refresh() {
    if (visible && active() && !fetching && !submitting && !canceling) { error = ""; stop(); await poll(generation, job.job_id); return; }
    if (!visible || !editable() || busy()) return;
    const token = generation, saved = { ...context() }; fetching = true; error = ""; render();
    try {
      const value = await hooks.apiRequest(endpoint(), { cache: "no-store" });
      if (current(token)) {
        capability = readPreparation(value, saved);
        if (capability.source_registered && capability.status === "already_prepared") await complete(token, "already_prepared");
      }
    } catch (failure) { if (current(token)) error = preparationReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { fetching = false; render(); } }
  }
  async function complete(token, id) {
    if (!current(token) || delivered === id) return;
    delivered = id; stop(); await hooks.completed();
  }
  async function apply(value, saved, token, id) {
    job = readPreparation(value, saved, id);
    if (active()) queue();
    else { stop(); if (job.status === "needs_review" && job.source_registered) await complete(token, job.job_id); }
    render();
  }
  async function start() {
    if (!visible || job?.source_registered || !editable() || busy() || !capability?.can_prepare || capability.status !== "ready") return;
    const token = generation, request = ++serial, saved = { ...context() }; submitting = true; error = ""; polls = 0; render();
    try {
      const value = await hooks.apiRequest(endpoint(), { method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha }) });
      if (current(token) && request === serial) await apply(value, saved, token);
    } catch (failure) { if (current(token)) error = preparationReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { submitting = false; render(); } }
  }
  function queue() {
    stop(); const token = generation, id = job.job_id;
    timer = schedule(() => { timer = null; void poll(token, id); }, ++polls > 10 ? 5000 : 1500);
  }
  async function poll(token, id) {
    if (!current(token) || !visible || job?.job_id !== id) return;
    const request = ++serial, saved = { ...context() };
    try {
      const value = await hooks.apiRequest(`${endpoint()}/jobs/${id}`, { cache: "no-store" });
      if (current(token) && request === serial) await apply(value, saved, token, id);
    } catch { if (current(token) && request === serial) { error = "暂时无法读取准备进度，请重试查询。"; render(); } }
  }
  async function cancel() {
    if (!active() || canceling || job.cancel_requested) return;
    const token = generation, request = ++serial, saved = { ...context() }, id = job.job_id;
    stop(); canceling = true; render();
    try {
      const value = await hooks.apiRequest(`${endpoint()}/jobs/${id}/cancel`, { method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" }, body: "{}" });
      if (current(token) && request === serial) await apply(value, saved, token, id);
    } catch { if (current(token)) { error = "取消请求未完成，请重试。"; if (active()) queue(); } }
    finally { if (current(token)) { canceling = false; render(); } }
  }
  return { element: view.element, sync, start, refresh, cancel, dispose() { generation++; stop(); } };
}
