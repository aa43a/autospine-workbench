"use strict";

import { createP10RuntimeCaptureApi } from "./p10-runtime-capture-api.js";
import { runtimeCaptureRequest } from "./p10-runtime-capture-contract.js";
import {
  renderJob, renderPackageOptions, renderPreflight, resetRun,
  runtimeCaptureElements, setBusy, showEntryStatus, updateStartButton,
} from "./p10-runtime-capture-view.js";

const api = createP10RuntimeCaptureApi();
const elements = runtimeCaptureElements();
let preflight = null;
let currentJob = null;
let pollTimer = 0;
let loadGeneration = 0;
let clientRequestId = null;

elements.packageSelect.addEventListener("change", () => loadPreflight(
  elements.packageSelect.value,
));
elements.reloadPackage.addEventListener("click", () => loadPreflight(
  elements.packageSelect.value,
));
elements.licenseConfirmation.addEventListener("change", () => {
  updateStartButton(elements, Boolean(preflight?.environment.available), Boolean(currentJob));
});
elements.startCapture.addEventListener("click", () => openConfirmation());
elements.cancelRun.addEventListener("click", () => elements.runDialog.close("cancel"));
elements.confirmRun.addEventListener("click", () => {
  elements.runDialog.close("confirm");
  submitRun();
});
elements.runDialog.addEventListener("cancel", () => elements.runDialog.close("cancel"));
elements.runDialog.addEventListener("click", (event) => {
  if (event.target === elements.runDialog) elements.runDialog.close("cancel");
});
elements.newRun.addEventListener("click", () => {
  const packageId = preflight?.package.package_id || elements.packageSelect.value;
  stopPolling();
  currentJob = null;
  clientRequestId = null;
  loadPreflight(packageId);
});

boot();

async function boot() {
  try {
    showEntryStatus(elements, "正在读取可用项目…");
    const query = new URLSearchParams(location.search);
    const list = await api.listPackages();
    const jobId = query.get("job_id");
    if (jobId) {
      const job = await api.job(jobId);
      renderPackageOptions(elements, list, job.request.package_id);
      await loadPreflight(job.request.package_id);
      await resumeJob(jobId, job);
      return;
    }
    const packageId = renderPackageOptions(
      elements, list, query.get("package_id"),
    );
    if (!packageId) throw new Error("没有可进入 P10.3 的当前项目");
    await loadPreflight(packageId);
  } catch (error) {
    showEntryStatus(elements, publicMessage(error), "error");
  }
}

async function loadPreflight(packageId) {
  const generation = ++loadGeneration;
  stopPolling();
  currentJob = null;
  preflight = null;
  resetRun(elements);
  setBusy(elements, true);
  showEntryStatus(elements, "正在精确重放当前 P10.1 与取景决定…");
  try {
    const value = await api.preflight(packageId);
    if (generation !== loadGeneration) return;
    preflight = value;
    renderPreflight(elements, value);
    showEntryStatus(
      elements,
      value.status === "ready" ? "已自动校验，可确认启动。" : "执行环境不完整。",
      value.status === "ready" ? "success" : "error",
    );
    replaceQuery({ package_id: packageId });
  } catch (error) {
    if (generation === loadGeneration) showEntryStatus(elements, publicMessage(error), "error");
  } finally {
    if (generation === loadGeneration) setBusy(elements, false);
  }
}

function openConfirmation() {
  if (!preflight?.environment.available || !elements.licenseConfirmation.checked) return;
  elements.dialogProject.textContent = preflight.package.project_id;
  elements.dialogClip.textContent = preflight.package.clip_id;
  elements.dialogCases.textContent = `${preflight.package.case_count} 个固定样本`;
  elements.runDialog.showModal();
}

async function submitRun() {
  if (!preflight || currentJob) return;
  clientRequestId ||= createClientRequestId();
  updateStartButton(elements, true, true);
  elements.startStatus.textContent = "正在创建不可变采集任务…";
  try {
    const body = runtimeCaptureRequest(preflight, clientRequestId);
    currentJob = await api.submit(body);
    renderJob(elements, currentJob);
    replaceQuery({ package_id: preflight.package.package_id, job_id: currentJob.job_id });
    if (!currentJob.terminal && !currentJob.retryable) schedulePoll();
  } catch (error) {
    elements.startStatus.textContent = publicMessage(error);
    elements.startStatus.dataset.tone = "error";
    updateStartButton(elements, true, false);
  }
}

async function resumeJob(jobId, loadedJob = null) {
  try {
    currentJob = loadedJob || await api.job(jobId);
    if (preflight && currentJob.request.package_id !== preflight.package.package_id) {
      throw new Error("任务与当前项目不匹配，请重新选择项目");
    }
    if (!preflight || !sameExpectedHeads(currentJob.request, preflight.expected)) {
      renderHistoricalPackage(currentJob);
    }
    const stopped = renderJob(elements, currentJob);
    replaceQuery({ package_id: currentJob.request.package_id, job_id });
    updateStartButton(elements, true, true);
    if (!stopped) schedulePoll();
  } catch (error) {
    showEntryStatus(elements, `无法恢复采集任务：${publicMessage(error)}`, "error");
  }
}

function renderHistoricalPackage(job) {
  elements.captureWorkspace.hidden = false;
  elements.packageTitle.textContent = `不可变任务 · ${job.job_id.slice(0, 12)}…`;
  elements.packageFacts.textContent = "当前项目无法重新预检，但已保存的任务状态仍可安全回看。";
  elements.readinessBadge.textContent = "历史任务";
  elements.readinessBadge.dataset.tone = "warning";
  elements.startStatus.textContent = "历史任务为只读；创建新采集前需重新校验当前项目。";
}

function sameExpectedHeads(request, expected) {
  return ["candidate_sha256", "decision_sha256", "revision"].every((key) =>
    request.expected_p10_1[key] === expected.p10_1[key]
    && request.expected_framing[key] === expected.framing[key]);
}

function schedulePoll() {
  stopPolling();
  pollTimer = setTimeout(pollJob, 1000);
}

async function pollJob() {
  if (!currentJob) return;
  try {
    currentJob = await api.job(currentJob.job_id);
    const stopped = renderJob(elements, currentJob);
    if (!stopped) schedulePoll();
  } catch (error) {
    elements.progressText.textContent = `暂时无法读取进度：${publicMessage(error)}`;
    pollTimer = setTimeout(pollJob, 2500);
  }
}

function stopPolling() {
  clearTimeout(pollTimer);
  pollTimer = 0;
}

function replaceQuery(values) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) query.set(key, value);
  history.replaceState(null, "", `${location.pathname}?${query}`);
}

function createClientRequestId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function publicMessage(error) {
  return error instanceof Error && error.message ? error.message : "Runtime 采集失败";
}
