"use strict";

import { dynamicSeamV2Href } from "./body-sway-dynamic-seam-v2-contract.js";

const IDS = [
  "analysisBadge", "analysisStatus", "analysisProgress", "analysisProgressText",
  "analysisResult", "resultHeading", "analysisFacts", "amplitudeRail",
  "continuousRail", "visualEvidenceRail", "publishableRail", "releaseReasons",
  "amplitudeDigest", "continuousDigest", "technicalReceipts", "analysisFailure",
  "failureHeading", "failureMessage", "retryAnalysisBtn", "returnToAdmissionLink",
  "dynamicSeamLink",
];

const STATUS_LABELS = Object.freeze({
  indeterminate: "尚不能证明",
  sampled_structural_passed: "采样结构已通过",
  sampled_structural_rejected: "采样结构未通过",
  continuous_structural_certified: "连续结构已证明",
  official_runtime_sampled_cases_approved: "官方采样人工已通过",
  not_reviewed: "未做人审", unreviewed: "未做人审", unavailable: "不可用",
});
const MAX_SEGMENT_RUNS = 48;

export function safetyAnalysisV2Elements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少 P10.4b v2 界面元素：${id}`);
    return [id, element];
  }));
}

export function renderSafetyLoading(elements) {
  badge(elements.analysisBadge, "正在准备", "warning");
  status(elements, "正在读取当前 P10.4a v2 准入；无需选择文件或填写 SHA。", "warning");
  elements.analysisProgress.max = 1;
  elements.analysisProgress.value = 0;
  elements.analysisProgressText.textContent = "自动校验来源…";
  elements.analysisResult.hidden = true;
  elements.analysisFailure.hidden = true;
  elements.retryAnalysisBtn.hidden = true;
  disableDynamicSeam(elements.dynamicSeamLink);
}

export function renderSafetyRunState(elements, state) {
  if (state.status === "ready") {
    badge(elements.analysisBadge, "来源已就绪", "success");
    status(elements, "来源校验通过，正在自动启动幅度与连续结构分析。", "success");
    elements.analysisProgress.max = 1;
    elements.analysisProgress.value = 0;
    elements.analysisProgressText.textContent = "即将开始…";
    return;
  }
  const run = state.run;
  const running = state.status === "queued" || state.status === "running";
  badge(elements.analysisBadge, running ? "自动分析中" : "分析已停止",
    running ? "warning" : state.status === "completed" ? "success" : "error");
  elements.analysisProgress.max = run.progress.total;
  elements.analysisProgress.value = run.progress.current;
  elements.analysisProgressText.textContent =
    `${run.progress.current} / ${run.progress.total} · ${stageLabel(run.stage)}`;
  status(elements, running
    ? "系统正在后台证明九档结构点和相邻连续区间，可以留在本页等待。"
    : state.status === "completed" ? "结构分析完成，正在读取密封结果。"
      : "本次结构分析没有完成。", running ? "warning" : "");
}

export function renderSafetyFailure(elements, message, canStartNext = false) {
  badge(elements.analysisBadge, canStartNext ? "可创建新尝试" : "未形成结论", "error");
  status(elements, `P10.4b v2 未完成：${message}`, "error");
  elements.analysisResult.hidden = true;
  elements.analysisFailure.hidden = false;
  elements.failureHeading.textContent = canStartNext ? "本次尝试已安全封存" : "没有生成安全分析结论";
  elements.failureMessage.textContent = canStartNext
    ? "不会采用部分结果。新尝试会重新校验当前来源，不会覆盖本次回执。"
    : "系统没有猜测结果，也没有解除任何发布门禁；请返回 P10.4a 检查当前来源。";
  elements.retryAnalysisBtn.hidden = !canStartNext;
  disableDynamicSeam(elements.dynamicSeamLink);
}

export function renderSafetyResult(elements, value) {
  const tone = value.indeterminate ? "warning" : "success";
  badge(elements.analysisBadge,
    value.indeterminate ? "分析完成 · 有未定区间" : "结构证明完成", tone);
  status(elements, value.indeterminate
    ? "分析已正常完成；“尚不能证明”是有效结论，不是运行错误。"
    : "离散结构点与连续预览模型均已完成证明。", tone);
  elements.analysisProgress.max = value.run.progress.total;
  elements.analysisProgress.value = value.run.progress.total;
  elements.analysisProgressText.textContent = "分析结果已密封";
  elements.analysisFailure.hidden = true;
  elements.analysisResult.hidden = false;
  elements.resultHeading.textContent = value.indeterminate
    ? "该 run 锁定的 Preview v2 仍包含未定区间"
    : "结构证据已覆盖该 run 锁定的 Preview v2 范围";
  renderFacts(elements.analysisFacts, value);
  renderAmplitude(elements.amplitudeRail, value.amplitude.probes);
  renderSegments(elements.continuousRail, value.continuous.segments);
  renderVisual(elements.visualEvidenceRail, value.amplitude.probes);
  renderUnavailable(elements.publishableRail);
  renderReleaseReasons(elements.releaseReasons, value.releaseGate.reason_codes);
  elements.amplitudeDigest.textContent = value.amplitude.sha256;
  elements.continuousDigest.textContent = value.continuous.sha256;
  elements.technicalReceipts.textContent = JSON.stringify(value.receipts, null, 2);
  elements.dynamicSeamLink.setAttribute("href", dynamicSeamV2Href(
    value.jobId, value.run.runId,
  ));
  elements.dynamicSeamLink.setAttribute("aria-disabled", "false");
  elements.dynamicSeamLink.removeAttribute?.("tabindex");
  elements.dynamicSeamLink.textContent = "开始 P10.5d v2 动态接缝分析";
  queueMicrotask(() => elements.resultHeading.focus?.());
}

function disableDynamicSeam(link) {
  link.removeAttribute?.("href");
  link.setAttribute("aria-disabled", "true");
  link.setAttribute("tabindex", "-1");
  link.textContent = "等待 P10.4b v2 完成";
}

function renderFacts(container, value) {
  const summary = value.continuous.summary;
  const rows = [
    ["项目", value.projectId], ["动作", value.clipId],
    ["权威范围", value.authorityScope === "compile_time_snapshot"
      ? "本次编译时密封快照" : "未授予 current authority"],
    ["九档结构点", `${value.amplitude.probes.length} / 9 已分析`],
    ["相邻区间", `${summary.certifiedSegmentCount} 已证明 · ${summary.indeterminateSegmentCount} 未定`],
  ];
  container.replaceChildren(...rows.map(([term, description]) => {
    const wrapper = container.ownerDocument.createElement("div");
    const dt = container.ownerDocument.createElement("dt");
    const dd = container.ownerDocument.createElement("dd");
    dt.textContent = term;
    dd.textContent = description;
    wrapper.append(dt, dd);
    return wrapper;
  }));
}

function renderAmplitude(container, probes) {
  container.replaceChildren(...probes.map((probe) => {
    const percent = Math.round(100 * probe.gain.numerator / probe.gain.denominator);
    return railItem(container, `${percent}%`, label(probe.status), tone(probe.status),
      `${percent}% 幅度：${label(probe.status)}`);
  }));
}

function renderSegments(container, segments) {
  const compacted = compactContinuousSegments(segments);
  const items = compacted.runs.map((run) => {
    const reasons = run.reasonCodes.length ? `；${run.reasonCodes.join("、")}` : "";
    return railItem(container, `${run.leftTick} → ${run.rightTick}`,
      `${run.segmentCount} 段 · ${label(run.status)}`, tone(run.status),
      `tick ${run.leftTick} 到 ${run.rightTick}，共 ${run.segmentCount} 个相邻区间：`
        + `${label(run.status)}${reasons}`);
  });
  if (compacted.omittedRunCount) {
    items.push(railItem(container, "其余状态组",
      `${compacted.omittedSegmentCount} 段已折叠`, "blocked",
      `其余 ${compacted.omittedRunCount} 个状态组、共 ${compacted.omittedSegmentCount} 个区间已折叠；精确总数见上方摘要`));
  }
  container.replaceChildren(...items);
}

export function compactContinuousSegments(segments, limit = MAX_SEGMENT_RUNS) {
  const groups = [];
  for (const segment of segments) {
    const prior = groups.at(-1);
    const same = prior && prior.rightTick === segment.leftTick
      && prior.status === segment.status
      && prior.reasonCodes.join("\u0000") === segment.reasonCodes.join("\u0000");
    if (same) {
      prior.rightTick = segment.rightTick;
      prior.segmentCount += 1;
    } else {
      groups.push({ ...segment, reasonCodes: [...segment.reasonCodes], segmentCount: 1 });
    }
  }
  if (groups.length <= limit) return { runs: groups, omittedRunCount: 0, omittedSegmentCount: 0 };
  const shown = groups.slice(0, limit - 1);
  const omitted = groups.slice(limit - 1);
  return {
    runs: shown, omittedRunCount: omitted.length,
    omittedSegmentCount: omitted.reduce((total, run) => total + run.segmentCount, 0),
  };
}

function renderVisual(container, probes) {
  const full = probes.find(({ gain }) => gain.numerator === gain.denominator);
  const state = full?.visualReviewStatus || "unavailable";
  container.replaceChildren(railItem(
    container, "100%", label(state), tone(state),
    `只有 100% 幅度绑定人工视觉复核：${label(state)}`,
  ));
}

function renderUnavailable(container) {
  container.replaceChildren(railItem(
    container, "不可用", "仍需后续证据", "blocked",
    "发布级安全范围不可用；结构证明不会自动成为发布许可",
  ));
}

function renderReleaseReasons(container, reasons) {
  const rows = Array.isArray(reasons) && reasons.length
    ? reasons : ["publishable_safe_range_unavailable"];
  container.replaceChildren(...rows.map((reason) => {
    const item = container.ownerDocument.createElement("li");
    item.textContent = String(reason).replaceAll("_", " ");
    return item;
  }));
}

function railItem(container, title, detail, state, ariaLabel) {
  const item = container.ownerDocument.createElement("li");
  const strong = container.ownerDocument.createElement("strong");
  const small = container.ownerDocument.createElement("small");
  item.dataset.state = state;
  item.setAttribute("aria-label", ariaLabel);
  strong.textContent = title;
  small.textContent = detail;
  item.append(strong, small);
  return item;
}

export function safetyEvidenceTone(value) {
  if (value === "indeterminate") return "warning";
  if (value === "sampled_structural_rejected") return "error";
  if (["not_reviewed", "unavailable"].includes(value)) return "blocked";
  if (["sampled_structural_passed", "continuous_structural_certified",
    "official_runtime_sampled_cases_approved"].includes(value)) return "pass";
  return "blocked";
}

const tone = safetyEvidenceTone;

function label(value) {
  return STATUS_LABELS[value] || String(value).replaceAll("_", " ");
}

function stageLabel(value) {
  return {
    queued: "任务已排队", review_admission: "重放 P10.4a v2",
    exact_source: "校验精确来源",
    amplitude_probes: "分析九档结构点", continuous_segments: "证明连续区间",
    continuous_boxes: "区间盒证明心跳",
    continuous_validation: "校验连续证明",
    current_head_recheck: "复核 current head",
    sealing: "密封结果", completed: "分析完成",
  }[value] || String(value).replaceAll("_", " ");
}

function badge(node, text, toneValue) {
  node.textContent = text;
  node.dataset.tone = toneValue;
}

function status(elements, message, toneValue = "") {
  elements.analysisStatus.textContent = message;
  if (toneValue) elements.analysisStatus.dataset.tone = toneValue;
  else delete elements.analysisStatus.dataset.tone;
}
