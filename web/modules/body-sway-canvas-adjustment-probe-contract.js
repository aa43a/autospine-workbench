"use strict";

import {
  digestValue, exactCopy, exactFields, finiteNumber, integer, safeId, sameJson,
} from "./body-sway-probe-contract-utils.js";

const BONES = ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"];
const PROBE_FIELDS = [
  "gain", "sample_count", "canvas_status", "sampled_geometry_status",
  "canvas_failure_tick_count", "canvas_failure_vertex_count",
  "geometry_rejection_tick_count", "first_failure_tick", "last_failure_tick",
  "affected_attachment_ids", "failure_sides", "max_overflow_px", "worst_failure",
  "sampled_body_sway_peak_abs_delta_deg", "evidence_sha256",
];

export function normalizeCanvasAdjustmentProbes(value, timing) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 9) {
    throw new Error("画布调整 gain 证据数量无效");
  }
  let previous = -1;
  const rows = value.map((raw) => {
    exactFields(raw, PROBE_FIELDS, "画布调整 gain 证据");
    const numerator = normalizeCanvasGain(raw.gain);
    if (numerator <= previous) throw new Error("画布调整 gain 顺序无效");
    previous = numerator;
    const sampleCount = integer(raw.sample_count, 2, "画布调整采样数");
    integer(raw.canvas_failure_tick_count, 0, "画布调整越界采样数", sampleCount);
    integer(raw.geometry_rejection_tick_count, raw.canvas_failure_tick_count,
      "画布调整几何拒绝数", sampleCount);
    integer(raw.canvas_failure_vertex_count, raw.canvas_failure_tick_count,
      "画布调整越界顶点数");
    if (!["passed", "rejected"].includes(raw.canvas_status)
        || !["passed", "rejected"].includes(raw.sampled_geometry_status)
        || (raw.canvas_status === "passed") !== (raw.canvas_failure_tick_count === 0)
        || (raw.sampled_geometry_status === "passed")
          !== (raw.geometry_rejection_tick_count === 0)) {
      throw new Error("画布调整 gain 状态无效");
    }
    normalizeFailureBounds(raw, timing.duration_ticks);
    digestValue(raw.evidence_sha256, "画布调整 gain 证据 SHA");
    normalizePeakRows(raw.sampled_body_sway_peak_abs_delta_deg);
    return exactCopy(raw);
  });
  if (rows.at(-1).gain.numerator !== 8) throw new Error("画布调整缺少原始 100% 档位");
  return rows;
}

export function normalizeCanvasGain(value) {
  exactFields(value, ["numerator", "denominator"], "画布调整 gain");
  integer(value.numerator, 0, "画布调整 gain numerator", 8);
  if (value.denominator !== 8) throw new Error("画布调整 gain denominator 无效");
  return value.numerator;
}

function normalizeFailureBounds(row, duration) {
  const failed = row.canvas_failure_tick_count > 0;
  if (failed) {
    integer(row.first_failure_tick, 0, "画布调整首次越界", duration);
    integer(row.last_failure_tick, row.first_failure_tick, "画布调整末次越界", duration);
  } else if (row.first_failure_tick !== null || row.last_failure_tick !== null) {
    throw new Error("画布调整无越界档位不能声明失败区间");
  }
  finiteNumber(row.max_overflow_px, "画布调整最大越界距离");
  if (row.max_overflow_px < 0 || failed === (row.max_overflow_px === 0)) {
    throw new Error("画布调整越界距离无效");
  }
  requireSortedUnique(row.affected_attachment_ids, "画布调整附件");
  row.affected_attachment_ids.forEach((value) => safeId(value, "画布调整附件"));
  requireSides(row.failure_sides, "画布调整越界方向", false);
  if (row.worst_failure !== null) {
    const worst = exactFields(row.worst_failure,
      ["tick", "attachment_id", "vertex_index", "point_xy", "sides", "overflow_px"],
      "画布调整最严重越界");
    integer(worst.tick, 0, "画布调整最严重越界 tick", duration);
    integer(worst.vertex_index, 0, "画布调整最严重越界顶点");
    finiteNumber(worst.overflow_px, "画布调整最严重越界距离");
    if (!Array.isArray(worst.point_xy) || worst.point_xy.length !== 2) {
      throw new Error("画布调整最严重越界坐标无效");
    }
    worst.point_xy.forEach((value) => finiteNumber(value, "画布调整越界坐标"));
    requireSides(worst.sides, "画布调整最严重越界方向", true);
    if (!failed || worst.overflow_px !== row.max_overflow_px
        || !row.affected_attachment_ids.includes(worst.attachment_id)
        || !worst.sides.every((side) => row.failure_sides.includes(side))) {
      throw new Error("画布调整最严重越界无效");
    }
  } else if (failed) throw new Error("画布调整缺少最严重越界");
}

function requireSortedUnique(value, label) {
  if (!Array.isArray(value) || !sameJson(value, [...new Set(value)].sort())
      || value.some((row) => typeof row !== "string")) throw new Error(`${label}无效`);
}

function requireSides(value, label, nonempty) {
  requireSortedUnique(value, label);
  const allowed = new Set(["bottom", "left", "right", "top"]);
  if ((nonempty && !value.length) || value.some((side) => !allowed.has(side))) {
    throw new Error(`${label}无效`);
  }
}

function normalizePeakRows(value) {
  if (!Array.isArray(value) || value.length !== BONES.length
      || value.some((row, index) => row?.bone_id !== BONES[index])) {
    throw new Error("画布调整逐骨峰值无效");
  }
  for (const row of value) {
    exactFields(row, ["bone_id", "value"], "画布调整逐骨峰值");
    finiteNumber(row.value, "画布调整逐骨峰值");
    if (row.value < 0) throw new Error("画布调整逐骨峰值不能为负数");
  }
}
