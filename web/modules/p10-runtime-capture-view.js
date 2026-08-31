"use strict";

import { runtimeCaptureReviewUrl } from "./p10-runtime-capture-contract.js";

const IDS = [
  "packageSelect", "reloadPackage", "entryStatus", "captureWorkspace",
  "packageTitle", "packageFacts", "readinessBadge", "runtimeFacts",
  "runtimeBadge", "browserFacts", "browserBadge", "licenseConfirmation",
  "startCapture", "startStatus", "jobPanel", "jobBadge", "captureProgress",
  "progressText", "eventTimeline", "resultPanel", "resultHeading",
  "resultSummary", "reviewNext", "newRun", "runDialog", "dialogProject",
  "dialogClip", "dialogCases", "cancelRun", "confirmRun", "liveRegion",
];

const STAGES = [
  ["queued", "排队", "任务已持久化"],
  ["exact_replay", "精确重放", "核对当前决定"],
  ["preview_compiled", "Preview v2", "编译固定画面"],
  ["runtime_verified", "执行环境", "校验 Runtime 与浏览器"],
  ["capturing", "逐帧采集", "隔离执行全部样本"],
  ["sealing", "密封凭据", "原子发布并读回"],
  ["completed", "待视觉复核", "进入 P10.3c"],
];

export function runtimeCaptureElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少 Runtime 采集界面元素：${id}`);
    return [id, element];
  }));
}

export function renderPackageOptions(elements, list, preferredId = null) {
  const rows = list.packages.filter((row) => row.status === "ready_for_candidate_replay");
  elements.packageSelect.replaceChildren(...rows.map((row) => {
    const option = elements.packageSelect.ownerDocument.createElement("option");
    option.value = row.package_id;
    option.textContent = `${row.project_id} · ${row.clip_id}`;
    return option;
  }));
  const available = new Set(rows.map((row) => row.package_id));
  const selected = available.has(preferredId) ? preferredId
    : available.has(list.recommended_package_id) ? list.recommended_package_id
    : rows[0]?.package_id || null;
  if (selected) elements.packageSelect.value = selected;
  elements.packageSelect.disabled = rows.length < 2;
  elements.reloadPackage.disabled = !selected;
  return selected;
}

export function renderPreflight(elements, preflight) {
  const capturePackage = preflight.package;
  const runtime = preflight.environment.runtime;
  const browser = preflight.environment.browser;
  elements.captureWorkspace.hidden = false;
  elements.packageTitle.textContent = `${capturePackage.project_id} · ${capturePackage.clip_id}`;
  elements.packageFacts.textContent = `${capturePackage.case_count} 个固定采样 · 当前 P10.1 与取景决定已自动绑定`;
  badge(elements.readinessBadge, preflight.status === "ready" ? "可执行" : "环境缺失",
    preflight.status === "ready" ? "success" : "error");
  elements.runtimeFacts.textContent = runtime.available
    ? `${runtime.package} ${runtime.version} · 固定完整性已通过`
    : "未找到固定 Spine Player 4.2.119";
  badge(elements.runtimeBadge, runtime.available ? "已校验" : "缺失",
    runtime.available ? "success" : "error");
  elements.browserFacts.textContent = browser.available
    ? `${browser.family} ${browser.reported_version} · 启动器身份已锁定`
    : "未找到受支持的本地 Chrome";
  badge(elements.browserBadge, browser.available ? "已校验" : "缺失",
    browser.available ? "success" : "error");
  elements.startStatus.textContent = preflight.environment.available
    ? "环境已就绪；阅读许可后可启动一次明确的采集。"
    : "执行环境不完整；系统不会尝试下载或替换 Runtime。";
  elements.startStatus.dataset.tone = preflight.environment.available ? "success" : "error";
  updateStartButton(elements, preflight.environment.available);
}

export function updateStartButton(elements, environmentReady, busy = false) {
  elements.startCapture.disabled = busy || !environmentReady
    || !elements.licenseConfirmation.checked;
}

export function renderJob(elements, job) {
  elements.jobPanel.hidden = false;
  const failed = job.status === "failed_terminal" || job.retryable;
  const statusLabel = STAGES.find(([status]) => status === job.status)?.[1]
    || (job.retryable ? "可重新开始" : "任务失败");
  badge(elements.jobBadge, statusLabel,
    job.status === "completed" ? "success" : failed ? "error" : "warning");
  const progress = job.progress;
  elements.captureProgress.max = progress?.total || 1;
  elements.captureProgress.value = progress?.current || (job.status === "completed" ? 1 : 0);
  elements.progressText.textContent = progress
    ? `${progress.current} / ${progress.total} 个样本`
    : job.status === "completed" ? "全部样本已密封" : statusCopy(job.status, job.failure_code);
  renderTimeline(elements, job.status);
  const stopped = job.terminal || job.retryable;
  elements.resultPanel.hidden = !stopped;
  if (job.status === "completed") {
    elements.resultHeading.textContent = "官方 Runtime 采集完成";
    elements.resultSummary.textContent =
      "全部官方 Runtime 回调、PNG 与执行身份已原子发布；这仍不是视觉通过结论。";
    elements.reviewNext.href = runtimeCaptureReviewUrl(job);
    elements.reviewNext.hidden = false;
    elements.newRun.textContent = "创建一次新的采集";
    queueMicrotask(() => elements.resultHeading.focus());
  } else if (stopped) {
    elements.resultHeading.textContent = "本次采集未完成";
    elements.resultSummary.textContent = statusCopy(job.status, job.failure_code);
    elements.reviewNext.hidden = true;
    elements.newRun.textContent = "重新校验并创建新采集";
    queueMicrotask(() => elements.resultHeading.focus());
  }
  return stopped;
}

export function showEntryStatus(elements, message, tone = "neutral") {
  elements.entryStatus.textContent = message;
  elements.entryStatus.dataset.tone = tone;
  elements.liveRegion.textContent = message;
}

export function setBusy(elements, busy) {
  elements.packageSelect.disabled = busy || elements.packageSelect.options.length < 2;
  elements.reloadPackage.disabled = busy || !elements.packageSelect.value;
  elements.captureWorkspace.toggleAttribute("aria-busy", busy);
}

export function resetRun(elements) {
  elements.jobPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.licenseConfirmation.checked = false;
  elements.eventTimeline.replaceChildren();
  elements.captureProgress.value = 0;
  elements.reviewNext.hidden = true;
}

function renderTimeline(elements, currentStatus) {
  const active = STAGES.findIndex(([status]) => status === currentStatus);
  const failed = currentStatus.startsWith("failed_") || currentStatus === "interrupted_retryable";
  elements.eventTimeline.replaceChildren(...STAGES.map(([status, title, detail], index) => {
    const item = elements.eventTimeline.ownerDocument.createElement("li");
    item.dataset.state = !failed && index < active ? "done"
      : !failed && index === active ? "active" : "pending";
    const strong = item.ownerDocument.createElement("strong");
    const small = item.ownerDocument.createElement("small");
    strong.textContent = title;
    small.textContent = detail;
    item.append(strong, small);
    return item;
  }));
}

function statusCopy(status, failureCode) {
  if (status === "failed_retryable" || status === "interrupted_retryable") {
    return `本次任务未完成（${failureCode || "retryable"}）；不会发布部分证据。`;
  }
  if (status === "failed_terminal") return `输入已失效（${failureCode || "terminal"}），请重新校验。`;
  return "正在准备执行…";
}

function badge(element, text, tone) {
  element.textContent = text;
  element.dataset.tone = tone;
}
