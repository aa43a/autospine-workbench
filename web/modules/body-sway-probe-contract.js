"use strict";

import {
  digestValue, exactCopy, exactFields, safeId,
} from "./body-sway-probe-contract-utils.js";
import {
  FORMAT_VERSION, LIST_FORMAT, normalizeProbeInventoryDocument,
} from "./body-sway-probe-inventory-contract.js";
import { normalizeProbePreview } from "./body-sway-probe-preview-contract.js";
import {
  CHECK_IDS, normalizeProbeResult, normalizeProbeTechnical,
} from "./body-sway-probe-result-contract.js";
import {
  normalizeCanvasAdjustmentEnvelope,
} from "./body-sway-canvas-adjustment-contract.js";

export { CHECK_IDS, FORMAT_VERSION, LIST_FORMAT };
export const ENTRY_FORMAT = "autospine-body-sway-probe-entry";
export const ENTRY_FORMAT_VERSION = 2;

const TOP_FIELDS = [
  "format", "format_version", "status", "probeability", "package",
  "candidate_sha256", "history", "report_sha256", "result", "preview", "technical",
  "canvas_adjustment",
];
const PACKAGE_FIELDS = [
  "package_id", "motion_policy_package_id", "project_id", "motion_id", "clip_id",
  "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256", "p9_decision_sha256",
];
const ENTRY_STATUSES = new Set([
  "p10_1_review_required", "not_applicable",
  "manual_visual_required", "structural_rejected",
]);
const PROBEABILITIES = new Set([
  "probe_ready", "p10_1_review_required", "not_applicable",
]);

export const CHECK_COPY = Object.freeze({
  loop_closure: ["循环首尾闭合", "确认片段首尾姿势能稳定衔接。"],
  fk_finite: ["骨骼计算稳定", "检查所有采样点的骨骼坐标都是有效有限值。"],
  sampled_mesh_deformation: ["网格变形稳定", "检查代表姿势中的网格翻转和过度拉伸。"],
  sampled_canvas_containment: ["画布范围完整", "检查动作采样没有把附件异常甩出画布。"],
  shared_index_internal_continuity: ["网格内部连续", "检查共享顶点在变形后仍保持连接。"],
  inter_attachment_seams: ["图层接缝", "本项需要后续接缝锚点与动态范围证据。"],
  visual_quality: ["视觉质量", "本项需要 P10.3 官方 Runtime 采样画面复核。"],
});

export function normalizeProbeInventory(value) {
  return normalizeProbeInventoryDocument(value);
}

export function normalizeProbeEntry(value, expectedPackageId) {
  exactFields(value, TOP_FIELDS, "结构探针结果");
  if (value.format !== ENTRY_FORMAT || value.format_version !== ENTRY_FORMAT_VERSION
      || !ENTRY_STATUSES.has(value.status) || !PROBEABILITIES.has(value.probeability)) {
    throw new Error("结构探针结果合同无效");
  }
  const packageRow = normalizeDetailPackage(value.package, value.probeability);
  if (packageRow.package_id !== expectedPackageId) {
    throw new Error("结构探针结果与所选项目不一致");
  }
  const candidateSha = digestValue(value.candidate_sha256, "结构探针 candidate SHA");
  const head = normalizeHead(value.history);
  const sourceReview = head.current_revision === 0 ? null : {
    revision: head.current_revision,
    decision_sha256: head.decision_sha256,
    action: head.action,
    probe_status: head.probe_status,
  };
  const result = normalizeProbeResult(value.result, value.status, value.report_sha256);
  const preview = normalizeProbePreview(value.preview, Boolean(result));
  requireEntryState(value.status, value.probeability, head, result, preview);
  const technical = normalizeProbeTechnical(value.technical, {
    result, preview, packageRow, sourceReview, candidateSha,
  });
  const canvasAdjustment = value.canvas_adjustment === null ? null
    : normalizeCanvasAdjustmentEnvelope(value.canvas_adjustment, {
      packageRow, candidateSha, sourceReview,
      report: technical.report, reportSha256: result?.reportSha256, result,
    });
  if (!result && canvasAdjustment !== null) {
    throw new Error("无结构探针结果时不能携带画布调整诊断");
  }
  return {
    raw: exactCopy(value), status: value.status, package: packageRow,
    candidateSha, head, sourceReview, preview, result, technical, canvasAdjustment,
  };
}

export function requireInventoryEntryMatch(row, entry) {
  if (!row || row.current_revision === undefined) return entry;
  const pairs = [
    [row.package_id, entry.package.package_id],
    [row.project_id, entry.package.project_id],
    [row.motion_id, entry.package.motion_id],
    [row.clip_id, entry.package.clip_id],
    [row.p9_decision_sha256, entry.package.p9_decision_sha256],
    [row.candidate_sha256, entry.candidateSha],
    [row.current_revision, entry.head.current_revision],
    [row.decision_sha256, entry.head.decision_sha256],
    [row.action, entry.head.action],
    [row.probe_status, entry.head.probe_status],
    [row.status, entry.package.status],
  ];
  if (pairs.some(([left, right]) => left !== right)) {
    throw new Error("项目列表与 P10.1 current head 已变化，请重新读取");
  }
  return entry;
}

export function deriveProbeOutcome(entry) {
  if (!entry.result) {
    const kind = entry.status === "not_applicable" ? "not_applicable" : "p10_1_required";
    return { kind, canEnterVisual: false, shouldReturnToP10: true };
  }
  if (entry.result.status === "structural_rejected") {
    return { kind: "rejected", canEnterVisual: false, shouldReturnToP10: true };
  }
  return { kind: "visual_required", canEnterVisual: true, shouldReturnToP10: false };
}

export function reportDownload(entry) {
  const digest = entry?.result?.reportSha256;
  if (!digest) return null;
  const project = fileToken(entry.package.project_id);
  const clip = fileToken(entry.package.clip_id);
  return {
    filename: `${project}.${clip}.p10-2.${digest.slice(0, 12)}.json`,
    document: exactCopy(entry.technical.report),
  };
}

function normalizeDetailPackage(value, probeability) {
  exactFields(value, PACKAGE_FIELDS, "结构探针项目");
  for (const field of ["project_id", "motion_id", "clip_id"]) safeId(value[field], field);
  for (const field of ["package_id", "motion_policy_package_id", "motion_instance_v2_sha256",
    "reviewed_motion_bundle_sha256", "p9_decision_sha256"]) {
    digestValue(value[field], field);
  }
  return { ...exactCopy(value), status: probeability };
}

function normalizeHead(value) {
  exactFields(value, ["current_revision", "head_decision_sha256", "action", "probe_status"],
    "P10.1 来源决定");
  if (!Number.isInteger(value.current_revision) || value.current_revision < 0) {
    throw new Error("P10.1 revision 无效");
  }
  if (value.current_revision === 0) {
    if (value.head_decision_sha256 !== null || value.action !== null
        || value.probe_status !== null) throw new Error("P10.1 空历史无效");
  } else {
    digestValue(value.head_decision_sha256, "P10.1 decision SHA");
    if (!["adjust", "reject", "unobservable"].includes(value.action)
        || !["pending_probe", "not_applicable"].includes(value.probe_status)) {
      throw new Error("P10.1 决定身份无效");
    }
  }
  return {
    current_revision: value.current_revision,
    decision_sha256: value.head_decision_sha256,
    action: value.action,
    probe_status: value.probe_status,
  };
}

function requireEntryState(status, probeability, head, result, preview) {
  const headState = `${head.action}/${head.probe_status}`;
  if (result) {
    if (probeability !== "probe_ready" || head.current_revision < 1
        || headState !== "adjust/pending_probe" || !preview) {
      throw new Error("结构探针结果与 P10.1 current head 不一致");
    }
    if (result.schedule.last_tick !== preview.durationTicks
        || result.summary.representative_sample_count < preview.samples.length) {
      throw new Error("结构探针结果与 witness 预览不一致");
    }
    return;
  }
  if (preview !== null || status !== probeability
      || (probeability === "p10_1_review_required" && head.current_revision !== 0)
      || (probeability === "not_applicable" && head.current_revision > 0
        && !["reject/not_applicable", "unobservable/not_applicable"].includes(headState))) {
    throw new Error("无探针结果的 P10.1 状态不一致");
  }
}

function fileToken(value) {
  return String(value).replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 80) || "project";
}
