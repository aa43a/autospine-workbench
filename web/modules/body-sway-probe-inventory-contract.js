"use strict";

import {
  digestValue, exactFields, integer, safeId,
} from "./body-sway-probe-contract-utils.js";

export const LIST_FORMAT = "autospine-body-sway-probe-package-list";
export const PACKAGE_FORMAT = "autospine-body-sway-probe-package";
export const FORMAT_VERSION = 1;

const TOP_FIELDS = [
  "format", "format_version", "count", "ready_count",
  "not_applicable_count", "review_required_count", "skipped_count",
  "recommended_package_id", "packages",
];
const ROW_FIELDS = [
  "format", "format_version", "package_id", "project_id", "motion_id",
  "clip_id", "p9_decision_sha256", "candidate_sha256", "current_revision",
  "decision_sha256", "action", "probe_status", "status",
];
const STATUSES = new Set([
  "probe_ready", "p10_1_review_required", "not_applicable",
]);

export function normalizeProbeInventoryDocument(value) {
  exactFields(value, TOP_FIELDS, "结构探针项目列表");
  if (value.format !== LIST_FORMAT || value.format_version !== FORMAT_VERSION
      || !Array.isArray(value.packages)) {
    throw new Error("结构探针项目列表合同无效");
  }
  const packages = value.packages.map(normalizeRow);
  const counts = {
    probe_ready: packages.filter((row) => row.status === "probe_ready").length,
    not_applicable: packages.filter((row) => row.status === "not_applicable").length,
    p10_1_review_required: packages.filter(
      (row) => row.status === "p10_1_review_required",
    ).length,
  };
  const claimed = [
    integer(value.count, 0, "结构探针项目总数"),
    integer(value.ready_count, 0, "可检查项目数"),
    integer(value.not_applicable_count, 0, "不适用项目数"),
    integer(value.review_required_count, 0, "待设置项目数"),
  ];
  const expected = [
    packages.length, counts.probe_ready, counts.not_applicable,
    counts.p10_1_review_required,
  ];
  if (claimed.some((count, index) => count !== expected[index])) {
    throw new Error("结构探针项目列表计数不一致");
  }
  const skippedCount = integer(value.skipped_count, 0, "结构探针跳过项目计数");
  const ids = packages.map((row) => row.package_id);
  if (new Set(ids).size !== ids.length) throw new Error("结构探针项目 ID 重复");
  const expectedRecommendation = counts.probe_ready === 1 && skippedCount === 0
    ? packages.find((row) => row.status === "probe_ready").package_id : null;
  if (value.recommended_package_id !== expectedRecommendation) {
    throw new Error("结构探针推荐项目与完整列表不一致");
  }
  return {
    format: value.format,
    formatVersion: value.format_version,
    packages,
    recommendedPackageId: value.recommended_package_id,
    skippedCount,
  };
}

function normalizeRow(value) {
  exactFields(value, ROW_FIELDS, "结构探针项目");
  if (value.format !== PACKAGE_FORMAT || value.format_version !== FORMAT_VERSION
      || !STATUSES.has(value.status)) {
    throw new Error("结构探针项目合同无效");
  }
  for (const field of ["project_id", "motion_id", "clip_id"]) safeId(value[field], field);
  for (const field of ["package_id", "p9_decision_sha256", "candidate_sha256"]) {
    digestValue(value[field], field);
  }
  const revision = integer(value.current_revision, 0, "P10.1 revision");
  requireHeadState(value, revision);
  return {
    package_id: value.package_id,
    project_id: value.project_id,
    motion_id: value.motion_id,
    clip_id: value.clip_id,
    p9_decision_sha256: value.p9_decision_sha256,
    candidate_sha256: value.candidate_sha256,
    current_revision: revision,
    decision_sha256: value.decision_sha256,
    action: value.action,
    probe_status: value.probe_status,
    status: value.status,
  };
}

function requireHeadState(value, revision) {
  if (revision === 0) {
    if (value.decision_sha256 !== null || value.action !== null
        || value.probe_status !== null || value.status === "probe_ready") {
      throw new Error("结构探针空 P10.1 head 无效");
    }
    return;
  }
  digestValue(value.decision_sha256, "P10.1 decision SHA");
  const state = `${value.action}/${value.probe_status}/${value.status}`;
  if (!["adjust/pending_probe/probe_ready", "reject/not_applicable/not_applicable",
    "unobservable/not_applicable/not_applicable"].includes(state)) {
    throw new Error("结构探针 P10.1 head 状态不一致");
  }
}
