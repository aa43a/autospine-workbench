"use strict";

import {
  exactFields, finiteNumber, integer, safeId,
} from "./body-sway-probe-contract-utils.js";

const TOP_FIELDS = [
  "kind", "authority", "scope", "canonical_checks_are_authoritative",
  "witnesses_are_exhaustive", "timing", "representative_sample_count",
  "witness_count", "witnesses_truncated", "canvas_failure_marker_limit",
  "witnesses", "canvas", "composite_url",
];
const WITNESS_FIELDS = [
  "tick", "status", "target_bones", "canvas_failure_count",
  "canvas_failure_markers", "canvas_failure_markers_truncated",
];
const SIDES = new Set(["left", "right", "top", "bottom"]);

export function normalizeProbePreview(value, hasResult) {
  if (value === null && !hasResult) return null;
  exactFields(value, TOP_FIELDS, "结构探针预览");
  exactFields(value.canvas, ["width", "height"], "结构探针画布");
  exactFields(value.timing, ["ticks_per_second", "duration_ticks", "loop"],
    "结构探针时间基准");
  const width = integer(value.canvas.width, 1, "画布宽度");
  const height = integer(value.canvas.height, 1, "画布高度");
  const ticksPerSecond = integer(value.timing.ticks_per_second, 1, "每秒 tick");
  const durationTicks = integer(value.timing.duration_ticks, 1, "动作时长");
  if (typeof value.timing.loop !== "boolean"
      || value.kind !== "sampled-structural-witness-preview"
      || value.authority !== "none" || value.scope !== "sampled-diagnostic-only"
      || value.canonical_checks_are_authoritative !== true
      || value.witnesses_are_exhaustive !== false
      || value.canvas_failure_marker_limit !== 16
      || !Array.isArray(value.witnesses)
      || value.witnesses.length < 2 || value.witnesses.length > 9) {
    throw new Error("结构探针 witness 预览合同无效");
  }
  const representativeCount = integer(
    value.representative_sample_count, 2, "代表样本总数",
  );
  if (value.witness_count !== value.witnesses.length
      || value.witnesses_truncated !== (representativeCount > value.witnesses.length)) {
    throw new Error("结构探针 witness 计数不一致");
  }
  const canvas = { width, height };
  const samples = value.witnesses.map((row) => normalizeSample(row, canvas));
  if (samples[0].tick !== 0 || samples.at(-1).tick !== durationTicks
      || samples.some((row, index) => index > 0 && row.tick <= samples[index - 1].tick)) {
    throw new Error("结构探针 witness 时间顺序无效");
  }
  return {
    canvas,
    compositeUrl: localUrl(value.composite_url),
    ticksPerSecond,
    durationTicks,
    loop: value.timing.loop,
    representativeCount,
    setupBones: samples[0].bones,
    samples,
  };
}

function normalizeSample(value, canvas) {
  exactFields(value, WITNESS_FIELDS, "结构探针代表样本");
  const tick = integer(value.tick, 0, "代表样本 tick");
  const failureCount = integer(value.canvas_failure_count, 0, "越界顶点数");
  if (!["passed", "rejected"].includes(value.status)
      || !Array.isArray(value.canvas_failure_markers)
      || value.canvas_failure_markers.length !== Math.min(failureCount, 16)
      || value.canvas_failure_markers_truncated !== (failureCount > 16)) {
    throw new Error("结构探针 witness 状态无效");
  }
  const bones = normalizeBones(value.target_bones);
  const markers = value.canvas_failure_markers.map((row) => normalizeMarker(row, canvas));
  return { tick, bones, status: value.status, failureCount, markers };
}

function normalizeBones(rows) {
  if (!Array.isArray(rows) || rows.length !== 4) {
    throw new Error("四骨预览必须恰好包含四段骨骼");
  }
  return rows.map((row) => {
    exactFields(row, ["bone_id", "start_xy", "end_xy", "rotation_deg"], "预览骨骼");
    return {
      boneId: safeId(row.bone_id, "骨骼 ID"),
      start: point(row.start_xy, "骨骼起点"),
      end: point(row.end_xy, "骨骼终点"),
      rotationDeg: finiteNumber(row.rotation_deg, "骨骼旋转"),
    };
  });
}

function normalizeMarker(value, canvas) {
  exactFields(value, ["attachment_id", "vertex_index", "point_xy", "sides"], "越界标记");
  const pointValue = point(value.point_xy, "越界点");
  if (!Array.isArray(value.sides) || value.sides.length < 1
      || new Set(value.sides).size !== value.sides.length
      || value.sides.some((side) => !SIDES.has(side))) {
    throw new Error("越界方向无效");
  }
  const expectedSides = [
    pointValue.x < 0 ? "left" : null,
    pointValue.x > canvas.width ? "right" : null,
    pointValue.y < 0 ? "top" : null,
    pointValue.y > canvas.height ? "bottom" : null,
  ].filter(Boolean);
  if (JSON.stringify(value.sides) !== JSON.stringify(expectedSides)) {
    throw new Error("越界坐标与方向不一致");
  }
  return {
    attachmentId: safeId(value.attachment_id, "附件 ID"),
    vertexIndex: integer(value.vertex_index, 0, "顶点索引"),
    point: pointValue,
    sides: [...value.sides],
  };
}

function point(value, label) {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label}无效`);
  return { x: finiteNumber(value[0], label), y: finiteNumber(value[1], label) };
}

function localUrl(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    throw new Error("角色合成图地址必须是本地绝对路径");
  }
  return value;
}
