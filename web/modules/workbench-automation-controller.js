"use strict";

import { ACTIVE_JOBS, automationEndpoint, jobEndpoint, projectIdentity, readJob, readOverview, reviewTarget } from "./workbench-automation-contract.js";
import { AUTOMATION_STATUS, automationReason, createAutomationView } from "./workbench-automation-view.js";

export function createWorkbenchAutomation(document, hooks, options = {}) {
  const schedule = options.schedule || ((callback) => setTimeout(callback, 1200));
  const unschedule = options.unschedule || clearTimeout;
  let identity = null, projectId = null, generation = 0, timer = null, requestVersion = 0;
  let overview = null, job = null, fetching = false, submitting = false, canceling = false;
  let error = null, waitingForReview = false, intent = false;
  const view = options.view || createAutomationView(document, {
    start, refresh, cancel, canDownload, locate,
    canLocate: (item) => Boolean(reviewTarget(item, hooks.context())),
  });

  function context() { return hooks.context(); }
  function editable(value = context()) { return !value.dirty && !value.saving && !value.loading; }
  function current(token) { return token === generation && identity === projectIdentity(context()); }
  function active() { return job && ACTIVE_JOBS.has(job.status); }
  function canDownload() {
    return editable() && !submitting && !error && identity === projectIdentity(context()) && job?.status === "succeeded"
      && job?.run?.status === "succeeded";
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
      message: message(), items: overview?.items || [], steps: job?.run?.steps || [],
    });
  }
  function sync() {
    const value = context();
    const next = projectIdentity(value);
    if (next !== identity) {
      const sameProject = projectId === value.projectId;
      const resume = sameProject && intent && (waitingForReview || job?.status === "needs_review" || job?.run?.status === "needs_review");
      generation += 1; stopTimer(); identity = next; projectId = value.projectId;
      overview = null; job = null; error = null; fetching = false; submitting = false; canceling = false;
      waitingForReview = Boolean(resume); intent = Boolean(resume);
      if (identity) void refresh();
    }
    render();
    maybeResume();
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
    job = readJob(payload, projectId, expectedId);
    if (job.status === "needs_review" || job.run?.status === "needs_review") waitingForReview = intent;
    if (job.status === "canceled") { intent = false; waitingForReview = false; }
    render();
    if (active()) queuePoll();
  }
  async function start() {
    sync();
    if (!identity || !overview || !editable() || fetching || submitting || active()) return;
    const token = generation, saved = { ...context() }, serial = ++requestVersion;
    submitting = true; error = null; intent = true; render();
    try {
      const payload = await hooks.apiRequest(`${automationEndpoint(saved.projectId)}/preview`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ profile: "production_review", expected_resolved_sha256: saved.resolvedSha, resume: true }),
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
    timer = schedule(() => { timer = null; void poll(token, id); });
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
  function dispose() { generation += 1; stopTimer(); }
  return { sync, refresh: async () => { await refresh(); if (active()) queuePoll(); }, start, cancel, locate, canDownload, dispose };
}
