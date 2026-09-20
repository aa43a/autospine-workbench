"use strict";

import { ACTIVE_JOBS, DEFAULT_TARGET_VERSION, TARGET_VERSIONS, automationEndpoint, jobEndpoint, projectIdentity, readJob, readOverview, reviewTarget } from "./workbench-automation-contract.js";
import { AUTOMATION_STATUS, automationReason, createAutomationView } from "./workbench-automation-view.js";
import { createWorkbenchAnimated } from "./workbench-animated-controller.js";
import { workbenchLayout } from "./workbench-layout.js";
import { createWorkSessions } from "./workbench-work-sessions.js";

export function createWorkbenchAutomation(document, hooks, options = {}) {
  const layout = workbenchLayout(document), originalHooks = hooks;
  hooks = { ...hooks,
    selectLayer: (...args) => { layout?.show("asset"); originalHooks.selectLayer(...args); },
    selectJoint: (...args) => { layout?.show("asset"); originalHooks.selectJoint(...args); } };
  const schedule = options.schedule || ((callback, delay) => setTimeout(callback, delay));
  const now = options.now || (() => performance.now());
  const unschedule = options.unschedule || clearTimeout;
  let identity = null, projectId = null, generation = 0, timer = null, requestVersion = 0;
  let overview = null, job = null, fetching = false, submitting = false, canceling = false;
  let error = null, waitingForReview = false, intent = false;
  let targetVersion = DEFAULT_TARGET_VERSION;
  let startedAt = null;
  const view = options.view || createAutomationView(document, {
    start, refresh, cancel, canDownload, locate, setTarget,
    canLocate: (item) => Boolean(reviewTarget(item, hooks.context())),
  });
  const animated = document ? createWorkbenchAnimated(document, hooks) : null;
  const workSessions=layout?createWorkSessions(document,hooks):null; if(workSessions)layout.mountStatus(workSessions.element);

  function context() { return hooks.context(); }
  function selectedIdentity(value = context()) {
    const project = projectIdentity(value);
    return project ? `${project}:${targetVersion}` : null;
  }
  function editable(value = context()) { return !value.dirty && !value.saving && !value.loading; }
  function current(token) { return token === generation && identity === selectedIdentity(); }
  function active() { return job && ACTIVE_JOBS.has(job.status); }
  function canDownload() {
    return editable() && !submitting && !error && identity === selectedIdentity() && job?.status === "succeeded"
      && job?.run?.status === "succeeded" && (job.target_version ?? "4.2") === targetVersion;
  }
  function stopTimer() { if (timer !== null) unschedule(timer); timer = null; }
  function message() {
    const value = context();
    if (!identity) return "请选择可用项目。";
    if (value.saving) return "正在保存校正；保存完成后才能构建。";
    if (value.dirty) return "存在未保存校正，请先保存再构建或下载。";
    if (value.loading) return "正在加载项目…";
    if (error) return error;
    if (submitting) return "正在提交构建请求…";
    if (job?.cancel_requested && active()) return "已请求取消，正在等待构建停止…";
    if (active()) {
      const seconds = Math.max(0, Math.floor((now() - startedAt) / 1000));
      const state = job.status === "pending" ? "正在排队" : "正在构建并校验预览";
      return `${state}，已等待 ${seconds} 秒。${seconds >= 30
        ? "大图处理可能需要几分钟；状态查询不会重复构建，完成后会自动停止查询。"
        : "完成后会自动显示下载入口。"}`;
    }
    if (job) {
      const state = job.run?.status || job.status;
      const reason = job.reason_code || job.run?.steps?.find((row) => row.reason_code)?.reason_code;
      return `${AUTOMATION_STATUS[state] || "等待开始"}${reason ? `：${automationReason(reason)}` : ""}`;
    }
    if (fetching) return "正在读取项目能力与复核队列…";
    return overview?.capabilities.can_build_spine_preview
      ? "项目已就绪，可以构建静态预览。" : "请先处理待复核项；构建会保留当前进度。";
  }
  function render() {
    view.render({
      hasProject: Boolean(identity), canStart: Boolean(identity && overview && editable() && !fetching && !submitting && !active()),
      fetching, active: Boolean(active() || submitting), canCancel: Boolean(active()), canceling: canceling || Boolean(job?.cancel_requested),
      downloadUrl: canDownload() ? `${jobEndpoint(projectId, job.job_id)}/download` : null,
      targetVersion, message: message(), items: overview?.items || [], steps: job?.run?.steps || [],
    });
  }
  function sync() {
    workSessions?.sync();
    animated?.sync();
    const value = context();
    const next = selectedIdentity(value);
    if (next !== identity) {
      const sameProject = projectId === value.projectId;
      const resume = sameProject && intent && (waitingForReview || job?.status === "needs_review" || job?.run?.status === "needs_review");
      generation += 1; stopTimer(); identity = next; projectId = value.projectId;
      overview = null; job = null; error = null; fetching = false; submitting = false; canceling = false;
      startedAt = null;
      waitingForReview = Boolean(resume); intent = Boolean(resume);
      if (identity) void refresh();
    }
    render();
    maybeResume();
  }
  function setTarget(value) {
    if (!TARGET_VERSIONS.includes(value)) throw new Error("target_version_unsupported");
    if (value === targetVersion) return;
    targetVersion = value; intent = false; waitingForReview = false;
    sync();
  }
  async function refresh() {
    if (!identity || fetching) return;
    const token = generation;
    const saved = { ...context() };
    fetching = true; error = null; render();
    try {
      const payload = await hooks.apiRequest(automationEndpoint(saved.projectId), { cache: "no-store" });
      if (!current(token)) return;
      overview = readOverview(payload, saved);
    } catch (failure) {
      if (current(token)) error = automationReason(failure.message === "project_snapshot_stale" ? failure.message : null);
    } finally {
      if (current(token)) { fetching = false; render(); maybeResume(); if (active()) queuePoll(); }
    }
  }
  function maybeResume() {
    if (waitingForReview && intent && overview?.capabilities.can_build_spine_preview && editable()
      && !fetching && !submitting && !job) {
      waitingForReview = false;
      void start();
    }
  }
  function applyJob(payload, expectedId) {
    if (payload?.run?.source_addresses?.resolved_project_sha256
      && payload.run.source_addresses.resolved_project_sha256 !== context().resolvedSha) throw new Error("project_snapshot_stale");
    job = readJob(payload, projectId, expectedId, targetVersion);
    if (job.status === "needs_review" || job.run?.status === "needs_review") waitingForReview = intent;
    if (job.status === "canceled") { intent = false; waitingForReview = false; }
    render();
    if (active()) queuePoll();
    else stopTimer();
  }
  async function start() {
    sync();
    if (!identity || !overview || !editable() || fetching || submitting || active()) return;
    const token = generation, saved = { ...context() }, serial = ++requestVersion;
    submitting = true; error = null; intent = true; startedAt = now(); render();
    try {
      const payload = await hooks.apiRequest(`${automationEndpoint(saved.projectId)}/preview`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ profile: "production_review", expected_resolved_sha256: saved.resolvedSha, resume: true, target_version: targetVersion }),
      });
      if (current(token) && serial === requestVersion) applyJob(payload);
    } catch (failure) {
      if (current(token)) error = automationReason(failure.payload?.reason_code);
    } finally {
      if (current(token)) { submitting = false; render(); }
    }
  }
  function queuePoll() {
    stopTimer();
    const token = generation, id = job.job_id;
    const elapsed = Math.max(0, now() - startedAt);
    const delay = elapsed >= 30000 ? 5000 : elapsed >= 10000 ? 2500 : 1200;
    timer = schedule(() => { timer = null; void poll(token, id); }, delay);
  }
  async function poll(token, id) {
    if (!current(token) || job?.job_id !== id) return;
    const serial = ++requestVersion;
    try {
      const payload = await hooks.apiRequest(jobEndpoint(projectId, id), { cache: "no-store" });
      if (current(token) && job?.job_id === id && serial === requestVersion) applyJob(payload, id);
    } catch {
      if (current(token) && serial === requestVersion) { error = "暂时无法读取构建进度，点击刷新重试。"; render(); }
    }
  }
  async function cancel() {
    if (!active() || canceling || job?.cancel_requested) return;
    const token = generation, id = job.job_id, serial = ++requestVersion;
    stopTimer();
    canceling = true; error = null; intent = false; waitingForReview = false; render();
    try {
      const payload = await hooks.apiRequest(`${jobEndpoint(projectId, id)}/cancel`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" }, body: "{}",
      });
      if (current(token) && job?.job_id === id && serial === requestVersion) applyJob(payload, id);
    } catch {
      if (current(token)) error = "取消请求未完成，请重试。";
    } finally {
      if (current(token)) { canceling = false; render(); }
    }
  }
  function locate(item) {
    const target = reviewTarget(item, context());
    if (!target) return;
    if (target.type === "joint") hooks.selectJoint(target.id);
    else hooks.selectLayer(target.id);
    const inspector = document?.getElementById(target.type === "joint" ? "jointInspector" : "layerInspector");
    inspector?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    inspector?.querySelector?.("input:not([disabled]), select:not([disabled]), button:not([disabled])")?.focus?.({ preventScroll: true });
  }
  function dispose() { generation += 1; stopTimer(); animated?.dispose(); workSessions?.dispose(); }
  return { sync, refresh: async () => { await refresh(); if (active()) queuePoll(); }, start, cancel, locate, canDownload, setTarget, dispose };
}
