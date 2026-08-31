"use strict";

const SHA = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const JOB_STATUSES = new Set([
  "queued", "exact_replay", "preview_compiled", "runtime_verified",
  "capturing", "sealing", "completed", "failed_retryable",
  "interrupted_retryable", "failed_terminal",
]);
const RETRYABLE = new Set(["failed_retryable", "interrupted_retryable"]);
const TERMINAL = new Set(["completed", "failed_terminal"]);

export function normalizeRuntimeCapturePreflight(value, expectedPackageId) {
  const root = object(value, "Runtime 采集预检");
  exact(root, ["format", "format_version", "status", "package", "expected", "environment"]);
  constant(root.format, "autospine-p10-runtime-capture-preflight", "预检格式");
  constant(root.format_version, 1, "预检版本");
  if (!["ready", "runtime_unavailable"].includes(root.status)) {
    throw new Error("Runtime 采集预检状态无效");
  }
  const capturePackage = object(root.package, "采集包");
  exact(capturePackage, ["package_id", "project_id", "clip_id", "case_count"]);
  digest(capturePackage.package_id, "package_id");
  identifier(capturePackage.project_id, "project_id");
  identifier(capturePackage.clip_id, "clip_id");
  integer(capturePackage.case_count, "case_count", 1, 512);
  if (capturePackage.package_id !== expectedPackageId) throw new Error("采集包身份改变");
  const expected = object(root.expected, "当前决定");
  exact(expected, ["p10_1", "framing"]);
  expectedHead(expected.p10_1, "P10.1");
  expectedHead(expected.framing, "取景");
  const environment = normalizeEnvironment(root.environment);
  if ((root.status === "ready") !== environment.available) {
    throw new Error("预检状态与执行环境不一致");
  }
  rejectPrivateKeys(root);
  return { ...root, package: capturePackage, expected, environment };
}

export function normalizeRuntimeCaptureJob(value, expectedJobId = null) {
  const root = object(value, "Runtime 采集任务");
  exact(root, [
    "job_id", "request", "status", "event_count", "head_event_sha",
    "retryable", "terminal", "progress", "addresses", "failure_code", "events",
  ]);
  digest(root.job_id, "job_id");
  if (expectedJobId !== null && root.job_id !== expectedJobId) {
    throw new Error("Runtime 采集任务身份改变");
  }
  if (!JOB_STATUSES.has(root.status)) throw new Error("Runtime 采集任务状态无效");
  integer(root.event_count, "event_count", 1, 10000);
  digest(root.head_event_sha, "head_event_sha");
  if (typeof root.retryable !== "boolean" || typeof root.terminal !== "boolean") {
    throw new Error("Runtime 采集任务门禁无效");
  }
  if (root.retryable !== RETRYABLE.has(root.status)
      || root.terminal !== TERMINAL.has(root.status)) {
    throw new Error("Runtime 采集任务门禁与状态不一致");
  }
  const request = normalizeRequest(root.request, root.job_id);
  const events = array(root.events, "任务事件").map((event, index, rows) =>
    normalizeEvent(event, root.job_id, index, rows[index - 1]));
  if (events.length !== root.event_count) throw new Error("任务事件数量不一致");
  const last = events.at(-1);
  if (last.event_sha !== root.head_event_sha || last.status !== root.status) {
    throw new Error("Runtime 采集任务 head 不一致");
  }
  const progress = root.progress === null ? null : normalizeProgress(root.progress);
  const addresses = root.addresses === null ? null : normalizeAddresses(root.addresses);
  if ((root.status === "completed") !== (addresses !== null)) {
    throw new Error("任务完成状态与凭据地址不一致");
  }
  if (root.status === "capturing" && progress === null) throw new Error("采集进度缺失");
  if (!sameProgress(progress, last.progress)
      || !sameAddresses(addresses, last.addresses)
      || root.failure_code !== last.failure_code) {
    throw new Error("Runtime 采集任务摘要与事件 head 不一致");
  }
  rejectPrivateKeys(root);
  return { ...root, request, progress, addresses, events };
}

export function runtimeCaptureRequest(preflight, clientRequestId) {
  if (!preflight?.environment?.available) throw new Error("官方 Runtime 环境尚不可用");
  identifier(clientRequestId, "client_request_id");
  return {
    package_id: preflight.package.package_id,
    client_request_id: clientRequestId,
    expected_p10_1: preflight.expected.p10_1,
    expected_framing: preflight.expected.framing,
    explicit_runtime_license_confirmation: true,
    explicit_run_confirmation: true,
  };
}

export function runtimeCaptureReviewUrl(job) {
  if (job?.status !== "completed" || !job.addresses) return null;
  const query = new URLSearchParams({ job_id: job.job_id });
  return `./body-sway-review-v2.html?${query}`;
}

function normalizeEnvironment(value) {
  const row = object(value, "Runtime 环境");
  exact(row, ["format", "format_version", "available", "runtime", "browser"]);
  constant(row.format, "autospine-p10-runtime-environment", "环境格式");
  constant(row.format_version, 1, "环境版本");
  if (typeof row.available !== "boolean") throw new Error("环境 available 无效");
  const runtime = object(row.runtime, "Runtime");
  exact(runtime, [
    "available", "package", "version", "javascript_sha256", "stylesheet_sha256",
    "package_json_sha256", "license_sha256", "license_acknowledged",
    "license_file_presence_is_authorization",
  ]);
  const browser = object(row.browser, "浏览器");
  exact(browser, ["available", "family", "reported_version", "executable_sha256", "size_bytes"]);
  if (runtime.available) {
    for (const key of ["javascript_sha256", "stylesheet_sha256", "package_json_sha256", "license_sha256"]) {
      digest(runtime[key], key);
    }
  }
  if (browser.available) digest(browser.executable_sha256, "browser executable");
  if (runtime.license_acknowledged !== false
      || runtime.license_file_presence_is_authorization !== false) {
    throw new Error("环境检测越过了 Runtime 许可确认");
  }
  return { ...row, runtime, browser };
}

function expectedHead(value, label) {
  const row = object(value, `${label} head`);
  exact(row, ["candidate_sha256", "decision_sha256", "revision"]);
  digest(row.candidate_sha256, `${label} candidate`);
  digest(row.decision_sha256, `${label} decision`);
  integer(row.revision, `${label} revision`, 1, 1_000_000_000);
}

function normalizeRequest(value, jobId) {
  const row = object(value, "采集请求");
  exact(row, [
    "job_id", "format", "format_version", "package_id", "client_request_id",
    "expected_p10_1", "expected_framing",
    "explicit_runtime_license_confirmation", "explicit_run_confirmation",
  ]);
  if (row.job_id !== jobId) throw new Error("采集请求任务身份不一致");
  constant(row.format, "autospine-p10-capture-job-request", "请求格式");
  constant(row.format_version, 1, "请求版本");
  digest(row.package_id, "request package_id");
  identifier(row.client_request_id, "client_request_id");
  expectedHead(row.expected_p10_1, "request P10.1");
  expectedHead(row.expected_framing, "request 取景");
  if (row.explicit_runtime_license_confirmation !== true
      || row.explicit_run_confirmation !== true) {
    throw new Error("采集请求缺少明确确认");
  }
  return row;
}

function normalizeEvent(value, jobId, index, previous) {
  const row = object(value, "任务事件");
  exact(row, [
    "event_sha", "format", "format_version", "job_id", "sequence", "status",
    "previous_event_sha", "progress", "addresses", "failure_code",
  ]);
  digest(row.event_sha, "event_sha");
  if (row.job_id !== jobId || row.sequence !== index + 1) {
    throw new Error("任务事件身份或顺序无效");
  }
  constant(row.format, "autospine-p10-capture-job-event", "事件格式");
  constant(row.format_version, 1, "事件版本");
  if (!JOB_STATUSES.has(row.status)) throw new Error("任务事件状态无效");
  const expectedPrevious = previous?.event_sha || null;
  if (row.previous_event_sha !== expectedPrevious) throw new Error("任务事件链断裂");
  if (row.status === "capturing") normalizeProgress(row.progress);
  else if (row.progress !== null) throw new Error("非采集事件包含进度");
  if (row.status === "completed") normalizeAddresses(row.addresses);
  else if (row.addresses !== null) throw new Error("非完成事件包含凭据地址");
  const failed = RETRYABLE.has(row.status) || row.status === "failed_terminal";
  if (failed) identifier(row.failure_code, "failure_code");
  else if (row.failure_code !== null) throw new Error("非失败事件包含失败码");
  return row;
}

function normalizeProgress(value) {
  const row = object(value, "采集进度");
  exact(row, ["current", "total"]);
  integer(row.total, "progress total", 1, 512);
  integer(row.current, "progress current", 0, row.total);
  return row;
}

function normalizeAddresses(value) {
  const row = object(value, "执行凭据地址");
  exact(row, ["project", "preview", "execution_bundle", "artifact"]);
  identifier(row.project, "project address");
  for (const key of ["preview", "execution_bundle", "artifact"]) digest(row[key], key);
  return row;
}

function sameProgress(left, right) {
  return left === null ? right === null
    : right !== null && left.current === right.current && left.total === right.total;
}

function sameAddresses(left, right) {
  if (left === null) return right === null;
  return right !== null && ["project", "preview", "execution_bundle", "artifact"]
    .every((key) => left[key] === right[key]);
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 必须是对象`);
  }
  return value;
}

function array(value, label) {
  if (!Array.isArray(value)) throw new Error(`${label} 必须是数组`);
  return value;
}

function exact(value, fields) {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, i) => key !== expected[i])) {
    throw new Error("Runtime 采集字段集合无效");
  }
}

function constant(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}无效`);
}

function digest(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 不是 SHA-256`);
}

function identifier(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) throw new Error(`${label} 无效`);
}

function integer(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) throw new Error(`${label} 无效`);
}

function rejectPrivateKeys(value) {
  const pending = [value];
  while (pending.length) {
    const row = pending.pop();
    for (const [key, item] of Object.entries(row)) {
      if (key.toLowerCase().includes("path")) throw new Error("Runtime 采集响应泄漏本地路径");
      if (item && typeof item === "object") pending.push(item);
    }
  }
}
