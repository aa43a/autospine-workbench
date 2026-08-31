"use strict";

const FAILURE_STATUSES = new Set([
  "failed_retryable", "interrupted_retryable", "failed_terminal",
]);
const STAGES = new Set([
  "input_replay", "preview_compilation", "environment_verification",
  "runtime_launch", "case_capture", "capture_compilation",
  "evidence_publication", "unknown",
]);
const CATEGORIES = new Set([
  "input_identity", "runtime_environment", "orchestration",
  "browser_identity", "browser_execution", "capture_transport",
  "capture_evidence", "evidence_validation", "evidence_publication",
  "runtime_execution", "unclassified",
]);
const CATEGORY_BY_CODE = {
  input_head_changed: "input_identity", input_replay_failed: "input_identity",
  runtime_environment_unavailable: "runtime_environment",
  process_restart: "orchestration", manager_closed: "orchestration",
  runtime_browser_identity_changed: "browser_identity",
  runtime_browser_case_failed: "browser_execution",
  runtime_browser_exited_without_capture: "browser_execution",
  runtime_browser_launch_failed: "browser_execution",
  runtime_browser_nonzero_exit: "browser_execution",
  runtime_browser_output_failed: "browser_execution",
  runtime_browser_output_limit: "browser_execution",
  runtime_browser_process_control_failed: "browser_execution",
  runtime_browser_profile_cleanup_failed: "browser_execution",
  runtime_browser_timeout: "browser_execution",
  runtime_page_reported_error: "browser_execution",
  runtime_capture_server_failed: "capture_transport",
  runtime_case_evidence_failed: "capture_evidence",
  runtime_evidence_validation_failed: "evidence_validation",
  runtime_evidence_publication_failed: "evidence_publication",
  runtime_package_changed: "runtime_environment",
  runtime_progress_invalid: "orchestration",
  runtime_execution_io_failed: "runtime_execution",
  runtime_capture_failed: "runtime_execution",
};

export function normalizeRuntimeCaptureFailure(value, status, events) {
  if (!FAILURE_STATUSES.has(status)) {
    if (value !== null) throw new Error("非失败任务包含失败诊断");
    return null;
  }
  const row = object(value);
  exact(row, [
    "format", "format_version", "stage", "category",
    "completed_case_count", "total_case_count",
    "next_incomplete_case_ordinal",
  ]);
  if (row.format !== "autospine-p10-capture-failure-diagnostic"
      || row.format_version !== 1 || !STAGES.has(row.stage)
      || !CATEGORIES.has(row.category)) {
    throw new Error("失败诊断分类无效");
  }
  const progress = [...events].reverse().find((event) => event.progress)?.progress || null;
  const predecessor = events.at(-2)?.status || null;
  const category = CATEGORY_BY_CODE[events.at(-1).failure_code] || "unclassified";
  if (row.stage !== failureStage(predecessor, progress) || row.category !== category) {
    throw new Error("失败诊断与不可变事件链不一致");
  }
  requireCounts(row, progress);
  return row;
}

function requireCounts(row, progress) {
  if (progress === null) {
    if (row.completed_case_count !== null || row.total_case_count !== null
        || row.next_incomplete_case_ordinal !== null) {
      throw new Error("失败诊断虚构了采集进度");
    }
    return;
  }
  integer(row.completed_case_count, 0, progress.total);
  integer(row.total_case_count, 1, 512);
  const next = progress.current < progress.total ? progress.current + 1 : null;
  if (row.completed_case_count !== progress.current
      || row.total_case_count !== progress.total
      || row.next_incomplete_case_ordinal !== next) {
    throw new Error("失败诊断进度与事件链不一致");
  }
}

function failureStage(status, progress) {
  const fixed = {
    queued: "input_replay", exact_replay: "preview_compilation",
    preview_compiled: "environment_verification", runtime_verified: "runtime_launch",
    sealing: "evidence_publication",
  };
  if (status === "capturing") {
    return progress?.current === progress?.total
      ? "capture_compilation" : "case_capture";
  }
  return fixed[status] || "unknown";
}

function object(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("失败诊断必须是对象");
  }
  return value;
}

function exact(value, fields) {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error("失败诊断字段集合无效");
  }
}

function integer(value, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error("失败诊断采集计数无效");
  }
}
