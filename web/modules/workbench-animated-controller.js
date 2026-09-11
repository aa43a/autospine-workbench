"use strict";

import { ACTIVE_JOBS, projectIdentity } from "./workbench-automation-contract.js";
import { AUTOMATION_STATUS } from "./workbench-automation-view.js";
import { animatedEndpoint, animatedJobEndpoint, animatedLayerTarget, animatedReason, readAnimatedJob, readAnimatedOverview } from "./workbench-animated-contract.js";
import { createAnimatedView } from "./workbench-animated-view.js";
import { createAnimatedJoints } from "./workbench-animated-joints.js";
import { readAnimatedRebase } from "./workbench-animated-rebase.js";
import { createAnimatedPreparation } from "./workbench-animated-preparation.js";
import { createWorkbenchRigPlan } from "./workbench-rig-plan.js";
import { createWorkbenchSleeves } from "./workbench-sleeves.js";
import { createWorkbenchCharacter } from "./workbench-character.js";

export function createWorkbenchAnimated(document, hooks, options = {}) {
  const schedule = options.schedule || setTimeout, unschedule = options.unschedule || clearTimeout;
  const now = options.now || (() => performance.now());
  let identity = null, projectId = null, generation = 0, serial = 0, timer = null, started = 0;
  let overview = null, job = null, clip = null, fetching = false, submitting = false, canceling = false;
  let error = null, intent = false, waiting = false, savingReview = false, bindingDirty = false, jointDirty = false;
  let reviewNotice = "", rebasing = false, planning = false;
  const view = options.view || createAnimatedView(document, { start, refresh, cancel, setClip, canDownload,
    saveReview, completeBindings, rebase, bindingChanged: (dirty) => { bindingDirty = dirty; render(); }, locate });
  const joints = document ? createAnimatedJoints(document, { ...hooks,
    changed: (dirty) => { jointDirty = dirty; render(); }, saved: jointsSaved }) : null;
  if (joints) view.mountJoint(joints.element);
  const preparation = document ? createAnimatedPreparation(document, { ...hooks, completed: prepared }) : null;
  if (preparation) view.mountPreparation(preparation.element);
  const rigPlan = document ? createWorkbenchRigPlan(document, { ...hooks, locate,
    busyChanged: (busy) => { planning = busy; render(); } }) : null;
  if (rigPlan) (view.mountPlan || view.mountJoint)(rigPlan.element);
  const sleeves = document ? createWorkbenchSleeves(document, hooks) : null;
  if (sleeves) (view.mountSleeves || view.mountPlan || view.mountJoint)(sleeves.element);
  const character = document ? createWorkbenchCharacter(document, { ...hooks, locate }) : null;
  if (character) view.mountCharacter(character.element);
  const context = () => hooks.context();
  const current = (token) => token === generation && identity === projectIdentity(context());
  const editable = () => !context().dirty && !context().saving && !context().loading && !planning;
  const active = () => ACTIVE_JOBS.has(job?.status);
  function stop() { if (timer !== null) unschedule(timer); timer = null; }
  function canDownload() {
    return Boolean(identity && identity === projectIdentity(context()) && editable() && !error
      && !bindingDirty && !jointDirty && !fetching && !submitting && !savingReview && !rebasing && job?.run?.preview_available
      && ["succeeded", "needs_review"].includes(job.status) && ["succeeded", "needs_review"].includes(job.run.status));
  }
  function message() {
    if (!identity) return "请选择可用项目。";
    if (planning) return "正在分析全角色绑定规划…";
    if (!editable()) return "请等待项目加载并保存未提交的校正。";
    if (error) return error;
    if (rebasing) return "正在将已保存校正同步到动画来源…";
    if (savingReview) return "正在保存绑定复核…";
    if (jointDirty) return "关节修改尚未保存；请保存关节复核，或撤销本次修改。";
    if (bindingDirty) return "绑定选择尚未保存；请保存复核，或撤销本次修改。";
    if (submitting) return "正在提交动画候选构建…";
    if (active()) return `${job.cancel_requested ? "正在取消" : "正在构建动画候选"}，已等待 ${Math.max(0, Math.floor((now() - started) / 1000))} 秒。状态查询不会重复构建。`;
    if (job) return `${AUTOMATION_STATUS[job.run?.status || job.status]}${job.reason_code ? `：${animatedReason(job.reason_code)}` : ""}`;
    if (fetching) return "正在解析当前项目与动画能力…";
    return overview?.can_build ? "可以构建可变形动画候选；待复核内容会在结果中明确标出。" : animatedReason(overview?.reason_code);
  }
  function render() {
    const base = canDownload() ? animatedJobEndpoint(projectId, job.job_id) : null;
    const model = { hasProject: Boolean(identity), canStart: Boolean(overview?.can_build && editable()
      && !fetching && !submitting && !active() && !savingReview && !bindingDirty && !jointDirty && !rebasing),
    active: active() || submitting || rebasing || planning, fetching, canceling: canceling || Boolean(job?.cancel_requested),
    canCancel: active(), canReview: Boolean(overview?.binding_review && editable() && !active() && !submitting && !savingReview && !jointDirty && !rebasing),
    sourceRebase: overview?.source_rebase || null, rebasing,
    sourceMissing: overview?.reason_code === "animated_source_missing",
    preparationEditable: editable() && !fetching && !submitting && !active() && !savingReview && !bindingDirty && !jointDirty && !rebasing,
    canRebase: Boolean(overview?.source_rebase?.status === "ready" && editable() && !active() && !fetching && !submitting && !savingReview && !bindingDirty && !jointDirty && !rebasing),
    savingReview, bindingDirty, message: message(), reviewNotice, clips: overview?.clips || [], clip,
    bindingReview: overview?.binding_review || null, reviewIdentity: overview ? `${identity}:${overview.input_identity_sha256}` : null,
    inputIdentitySha: overview?.input_identity_sha256 || null,
    items: job?.run?.review_items || overview?.review_items || [], steps: job?.run?.steps || job?.progress || [], summary: job?.run?.summary,
    downloadUrl: base ? `${base}/download` : null, playbackUrl: base ? `${base}/files/playback.json` : null };
    view.render(model); joints?.render(model); preparation?.sync(model); rigPlan?.sync(model); sleeves?.sync(model); character?.sync(model);
  }
  function sync() {
    const next = projectIdentity(context());
    if (next !== identity) {
      const resume = projectId === context().projectId && intent && waiting;
      generation++; serial++; stop(); identity = next; projectId = context().projectId;
      overview = null; job = null; error = null; reviewNotice = ""; fetching = submitting = canceling = savingReview = bindingDirty = jointDirty = rebasing = planning = false;
      intent = waiting = Boolean(resume);
      if (identity) void refresh();
    }
    render(); maybeResume();
  }
  function maybeResume() {
    if (waiting && intent && overview?.can_build && editable() && !fetching && !submitting && !job && !bindingDirty && !jointDirty) {
      waiting = false; void start();
    }
  }
  async function refresh() {
    if (!identity || fetching || rebasing || planning) return;
    const token = generation, saved = { ...context() };
    fetching = true; error = null; render();
    try {
      const value = await hooks.apiRequest(animatedEndpoint(projectId), { cache: "no-store" });
      if (!current(token)) return;
      const updated = readAnimatedOverview(value, saved);
      readAnimatedRebase(updated.source_rebase, saved);
      if (overview && updated.input_identity_sha256 !== overview.input_identity_sha256) {
        serial++; stop(); job = null; bindingDirty = jointDirty = false;
      }
      overview = updated;
      if (!overview.clips.some((row) => row.id === clip)) clip = overview.clips[0]?.id || null;
    } catch (failure) { if (current(token)) error = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { fetching = false; render(); maybeResume(); if (active()) queuePoll(); } }
  }
  function apply(value, id) {
    const input = value?.run?.source_addresses?.input_identity_sha256;
    if (input && overview?.input_identity_sha256 && input !== overview.input_identity_sha256) throw new Error("animated_input_changed");
    job = readAnimatedJob(value, context(), id);
    waiting = intent && (job.status === "needs_review" || job.run?.status === "needs_review");
    if (job.status === "canceled") intent = waiting = false;
    if (active()) queuePoll(); else stop();
    render();
  }
  async function start() {
    sync();
    if (!overview?.can_build || !clip || !editable() || fetching || submitting || active() || bindingDirty || jointDirty || savingReview || rebasing) return;
    const token = generation, request = ++serial, saved = { ...context() };
    submitting = true; error = null; intent = true; started = now(); stop(); render();
    try {
      const value = await hooks.apiRequest(`${animatedEndpoint(projectId)}/preview`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha, clip, resume: true }),
      });
      if (current(token) && request === serial) apply(value);
    } catch (failure) { if (current(token)) error = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { submitting = false; render(); } }
  }
  function queuePoll() {
    stop(); const token = generation, id = job.job_id;
    const elapsed = now() - started;
    timer = schedule(() => { timer = null; void poll(token, id); }, elapsed >= 30000 ? 5000 : elapsed >= 10000 ? 2500 : 1200);
  }
  async function poll(token, id) {
    if (!current(token) || job?.job_id !== id) return;
    const request = ++serial;
    try {
      const value = await hooks.apiRequest(animatedJobEndpoint(projectId, id), { cache: "no-store" });
      if (current(token) && request === serial) apply(value, id);
    } catch { if (current(token) && request === serial) { error = "暂时无法读取动画进度，请点击刷新重试。"; render(); } }
  }
  async function cancel() {
    if (!active() || canceling || job.cancel_requested) return;
    const token = generation, id = job.job_id, request = ++serial;
    stop(); canceling = true; intent = waiting = false; render();
    try {
      const value = await hooks.apiRequest(`${animatedJobEndpoint(projectId, id)}/cancel`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" }, body: "{}",
      });
      if (current(token) && request === serial) apply(value, id);
    } catch { if (current(token)) error = "取消请求未完成，请重试。"; }
    finally { if (current(token)) { canceling = false; render(); } }
  }
  function setClip(value) {
    if (active() || submitting || !overview?.clips.some((row) => row.id === value) || clip === value) return;
    serial++; stop(); clip = value; job = null; error = null; intent = waiting = false; render();
  }
  async function saveReview(records) {
    if (!overview?.binding_review || !editable() || active() || submitting || savingReview || jointDirty || rebasing) return;
    const token = generation, saved = { ...context() };
    savingReview = true; error = null; render();
    let succeeded = false;
    try {
      await hooks.apiRequest(`${animatedEndpoint(projectId)}/review`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha,
          expected_input_sha256: overview.input_identity_sha256, records }),
      });
      if (!current(token)) return;
      bindingDirty = false; job = null; overview = null; intent = waiting = false;
      view.resetReview?.(); succeeded = true;
    } catch (failure) { if (current(token)) error = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { savingReview = false; render(); } }
    if (succeeded && current(token)) { await refresh(); if (current(token)) await start(); }
  }
  async function completeBindings() {
    if (!overview?.binding_review || !editable() || fetching || active() || submitting || savingReview || bindingDirty || jointDirty || rebasing) return;
    const token = generation, saved = { ...context() };
    savingReview = true; error = null; render();
    try {
      const value = await hooks.apiRequest(`${animatedEndpoint(projectId)}/complete-bindings`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha, expected_input_sha256: overview.input_identity_sha256 }),
      });
      if (!current(token)) return;
      overview = readAnimatedOverview(value, saved); job = null; intent = waiting = false;
      serial++; stop(); view.resetReview?.();
      reviewNotice = `简单绑定候选已准备，新增 ${value.binding_completion_result?.added_options || 0} 个选项。保留原决定，眼口和鞋类新选项仍需检查后保存。`;
    } catch (failure) { if (current(token)) error = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { savingReview = false; render(); } }
  }
  function locate(item) {
    const id = item.layer_id || item.entity_id;
    const layer = animatedLayerTarget(id, context());
    if (layer) { hooks.selectLayer(layer); if (item.type === "binding") view.focusBinding?.(id); }
    else if (item.type === "joint" && context().jointIds?.includes(item.entity_id)) hooks.selectJoint(item.entity_id);
  }
  async function jointsSaved(response) {
    serial++; stop(); job = null; overview = null; bindingDirty = jointDirty = false; intent = waiting = false;
    const count = response?.joint_review_result?.migration_suggestions?.length || 0;
    reviewNotice = count ? `关节复核已保存，${count} 个图层绑定因骨架变化退回待复核；请重新检查，候选构建不会自动确认绑定。`
      : "关节复核已保存，将基于当前骨架重新构建动画候选。";
    view.resetReview?.(); await refresh(); await start();
  }
  async function rebase() {
    const source = overview?.source_rebase;
    if (source?.status !== "ready" || !editable() || fetching || active() || submitting || savingReview || bindingDirty || jointDirty || rebasing) return;
    const token = generation, saved = { ...context() }, registration = source.expected_registration_sha256;
    serial++; stop(); rebasing = true; error = null; intent = waiting = false; render();
    let succeeded = false;
    try {
      await hooks.apiRequest(`${animatedEndpoint(saved.projectId)}/rebase`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: saved.resolvedSha, expected_registration_sha256: registration }),
      });
      if (!current(token)) return;
      overview = null; job = null; bindingDirty = jointDirty = false; view.resetReview?.();
      reviewNotice = "已保存校正已同步到动画链，主项目记录保持不变；受影响绑定需要重新复核。接下来使用本区动画候选入口。";
      succeeded = true;
    } catch (failure) { if (current(token)) error = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { rebasing = false; render(); } }
    if (succeeded && current(token)) {
      await refresh();
      if (current(token)) await joints?.reload();
      if (current(token)) await start();
    }
  }
  async function prepared() {
    const token = generation;
    serial++; stop(); job = null; overview = null; intent = waiting = false;
    reviewNotice = "真实姿态来源已准备。全部关节点已加载；模型辅助点仍待人工复核，不会自动确认或开始构建。";
    await refresh();
    if (current(token) && joints) { joints.element.open = true; await joints.reload(); }
  }
  function dispose() { generation++; stop(); view.dispose?.(); joints?.dispose(); preparation?.dispose(); rigPlan?.dispose(); sleeves?.dispose(); character?.dispose(); }
  return { sync, start, refresh, cancel, setClip, saveReview, completeBindings, rebase, locate, canDownload, dispose };
}
