"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const CHART = { width: 1000, left: 76, right: 976, correctionTop: 28, correctionBottom: 132, usageTop: 166, usageBottom: 232 };

export function createMotionPolicyEvidenceView(elements, { onFrameCandidate = () => {} } = {}) {
  const doc = elements.metricChart.ownerDocument;
  let model = null;
  let selectedIndex = 0;
  let imageReady = false;
  elements.frameScrubber.addEventListener("input", () => chooseFrame(Number(elements.frameScrubber.value), true));
  elements.metricChart.addEventListener("click", (event) => {
    if (!model?.samples.length) return;
    const rect = elements.metricChart.getBoundingClientRect?.();
    if (!rect?.width) return;
    const viewX = clamp((event.clientX - rect.left) / rect.width, 0, 1) * CHART.width;
    const plotRatio = clamp((viewX - CHART.left) / (CHART.right - CHART.left), 0, 1);
    chooseFrame(Math.round(plotRatio * (model.samples.length - 1)), true);
  });
  elements.characterComposite.addEventListener("load", () => {
    imageReady = true;
    const width = elements.characterComposite.naturalWidth;
    const height = elements.characterComposite.naturalHeight;
    if (width && height) elements.footOverlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
    if (model) renderFrame(model.samples[selectedIndex]);
  });
  elements.characterComposite.addEventListener("error", () => {
    imageReady = false;
    showOverlayMessage("角色合成图加载失败；数值证据仍可复核。");
  });

  function load(nextModel) {
    model = nextModel;
    selectedIndex = 0;
    imageReady = false;
    renderSummary(doc, elements.evidenceSummary, model);
    renderMetricTable(doc, elements.metricTableBody, model);
    renderAttention(doc, elements.attentionList, model.attentionWindows || [], (index) => chooseFrame(index, true));
    elements.frameScrubber.min = "0";
    elements.frameScrubber.max = String(Math.max(0, model.samples.length - 1));
    elements.frameScrubber.value = "0";
    elements.frameScrubber.disabled = model.samples.length === 0;
    elements.characterComposite.src = `/api/projects/${encodeURIComponent(model.projectId || "")}/composite`;
    renderChart(doc, elements.metricChart, model, selectedIndex);
    if (model.samples.length) renderFrame(model.samples[0]);
    else showEmptyFrame("没有 Foot 时间样本。");
  }

  function clear() {
    model = null;
    selectedIndex = 0;
    imageReady = false;
    for (const element of [elements.evidenceSummary, elements.attentionList, elements.metricTableBody,
      elements.metricChart, elements.footOverlay, elements.frameFacts, elements.observationBody]) element.replaceChildren();
    elements.frameLabel.textContent = "frame —";
    elements.frameState.textContent = "等待帧";
    elements.frameScrubber.value = "0";
    elements.frameScrubber.max = "0";
    elements.frameScrubber.disabled = true;
    elements.characterComposite.removeAttribute?.("src");
    showOverlayMessage("等待角色图与候选帧。");
  }

  function selectFrame(index) { chooseFrame(index, false); }
  function chooseFrame(index, notify) {
    if (!model?.samples.length) return;
    selectedIndex = clamp(Math.round(index), 0, model.samples.length - 1);
    elements.frameScrubber.value = String(selectedIndex);
    renderChart(doc, elements.metricChart, model, selectedIndex);
    const sample = model.samples[selectedIndex];
    renderFrame(sample);
    if (notify && sample.candidateId) onFrameCandidate(sample.candidateId, sample);
  }
  function renderFrame(sample) {
    elements.frameLabel.textContent = `frame ${sample.sourceFrameIndex} · tick ${sample.tick}`;
    elements.frameState.textContent = `${humanState(sample.state)} · ${humanSupport(sample.supportState)}`;
    renderFacts(doc, elements.frameFacts, sample);
    const observations = normalizeObservations(sample);
    renderObservationTable(doc, elements.observationBody, observations);
    renderFootOverlay(doc, elements.footOverlay, observations);
    if (!observations.length) showOverlayMessage("当前帧没有可绘制的足点观察（不可约束或不可观测）。");
    else if (!imageReady) showOverlayMessage("正在加载角色合成图…");
    else elements.overlayEmpty.hidden = true;
  }
  function showEmptyFrame(message) {
    elements.frameLabel.textContent = "frame —";
    elements.frameState.textContent = "无样本";
    elements.frameFacts.replaceChildren();
    elements.observationBody.replaceChildren(tableCell(doc, message, 5));
    elements.footOverlay.replaceChildren();
    showOverlayMessage(message);
  }
  function showOverlayMessage(message) { elements.overlayEmpty.textContent = message; elements.overlayEmpty.hidden = false; }
  return { load, clear, selectFrame };
}

export function buildSeriesPath(values, xAt, yAt) {
  let drawing = false;
  return values.map((value, index) => {
    if (!Number.isFinite(value)) { drawing = false; return ""; }
    const command = drawing ? "L" : "M";
    drawing = true;
    return `${command}${round(xAt(index))},${round(yAt(value))}`;
  }).filter(Boolean).join(" ");
}

function renderChart(doc, svg, model, selectedIndex) {
  svg.replaceChildren();
  const samples = model.samples;
  if (!samples.length) return;
  const xAt = (index) => CHART.left + (CHART.right - CHART.left) * index / Math.max(1, samples.length - 1);
  for (const window of model.attentionWindows || []) {
    const start = xAt(window.startSampleIndex); const end = xAt(window.endSampleIndex);
    svg.append(svgNode(doc, "rect", "chart-window", { x: start, y: 18, width: Math.max(3, end - start), height: 222 }));
  }
  const correctionMax = Math.max(1, ...samples.flatMap((row) => [Math.abs(row.correctionX ?? 0), Math.abs(row.correctionY ?? 0)]));
  const correctionY = (value) => (CHART.correctionTop + CHART.correctionBottom) / 2 -
    value / correctionMax * (CHART.correctionBottom - CHART.correctionTop) / 2;
  const residualLimit = model.contractLimits.maximumResidualPx;
  const ratioLimit = model.contractLimits.correctionReferenceRatio;
  const residual = samples.map((row) => divide(row.maximumResidualPx, residualLimit));
  const ratio = samples.map((row) => divide(row.correctionReferenceRatio, ratioLimit));
  const usageMax = Math.max(1, ...residual.filter(Number.isFinite), ...ratio.filter(Number.isFinite));
  const usageY = (value) => CHART.usageBottom - value / usageMax * (CHART.usageBottom - CHART.usageTop);
  svg.append(
    svgNode(doc, "line", "chart-baseline", { x1: CHART.left, y1: correctionY(0), x2: CHART.right, y2: correctionY(0) }),
    svgNode(doc, "line", "chart-baseline", { x1: CHART.left, y1: usageY(1), x2: CHART.right, y2: usageY(1) }),
    label(doc, 8, 42, "校正 px"), label(doc, 8, 181, "上限利用"), label(doc, 8, usageY(1) + 4, "100%"),
    path(doc, "chart-series chart-x", buildSeriesPath(samples.map((row) => row.correctionX), xAt, correctionY)),
    path(doc, "chart-series chart-y", buildSeriesPath(samples.map((row) => row.correctionY), xAt, correctionY)),
    path(doc, "chart-series chart-residual", buildSeriesPath(residual, xAt, usageY)),
    path(doc, "chart-series chart-ratio", buildSeriesPath(ratio, xAt, usageY)),
    svgNode(doc, "line", "chart-cursor", { x1: xAt(selectedIndex), y1: 14, x2: xAt(selectedIndex), y2: 242 }),
    label(doc, 758, 258, "X", "chart-label chart-x-label"),
    label(doc, 790, 258, "Y", "chart-label chart-y-label"),
    label(doc, 822, 258, "residual", "chart-label chart-residual-label"),
    label(doc, 900, 258, "ratio", "chart-label chart-ratio-label"),
  );
}

function renderSummary(doc, container, model) {
  container.replaceChildren();
  const candidates = model.samples.filter((row) => row.candidateId).length;
  const highestResidual = model.metrics?.maximumResidualPx?.maximum;
  const highestRatio = model.metrics?.correctionReferenceRatio?.maximum;
  for (const [caption, value, warning] of [
    ["时间样本", model.samples.length], ["待裁决 Foot", candidates], ["重点窗口", model.attentionWindows?.length || 0],
    ["残差峰值", format(highestResidual, " px"), utilization(highestResidual, model.contractLimits.maximumResidualPx) > 1],
    ["校正比例峰值", format(highestRatio), utilization(highestRatio, model.contractLimits.correctionReferenceRatio) > 1],
  ]) {
    const card = node(doc, "div", "summary-card");
    if (warning) card.dataset.tone = "warning";
    card.append(text(doc, "span", caption), text(doc, "strong", value));
    container.append(card);
  }
}

function renderMetricTable(doc, body, model) {
  body.replaceChildren();
  for (const [caption, field, limit] of [
    ["Correction X (px)", "correctionX", null], ["Correction Y (px)", "correctionY", null],
    ["Maximum residual (px)", "maximumResidualPx", model.contractLimits.maximumResidualPx],
    ["Correction / reference", "correctionReferenceRatio", model.contractLimits.correctionReferenceRatio],
  ]) {
    const summary = model.metrics?.[field] || {};
    const row = node(doc, "tr");
    row.append(text(doc, "th", caption), text(doc, "td", format(summary.minimum)), text(doc, "td", format(summary.maximum)),
      text(doc, "td", Number.isFinite(limit) ? percent(utilization(summary.maximum, limit)) : "—"));
    row.children[0]?.setAttribute?.("scope", "row");
    body.append(row);
  }
}

function renderAttention(doc, container, windows, choose) {
  container.replaceChildren();
  if (!windows.length) { container.append(text(doc, "p", "没有算法标出的重点窗口；仍需按片段人工复核。")); return; }
  windows.forEach((window, index) => {
    const button = text(doc, "button", `重点 ${index + 1} · frame ${range(window.startFrame, window.endFrame)}`, "attention-button");
    button.type = "button";
    button.title = (window.reasons || []).join("、");
    button.addEventListener("click", () => choose(window.startSampleIndex));
    container.append(button);
  });
}

function renderFacts(doc, list, sample) {
  list.replaceChildren();
  for (const [caption, value] of [["状态", humanState(sample.state)], ["支撑", humanSupport(sample.supportState)],
    ["接触", sample.activeContactIds?.join("、") || "无"], ["校正 X / Y", `${format(sample.correctionX)} / ${format(sample.correctionY)} px`],
    ["最大残差", format(sample.maximumResidualPx, " px")], ["reference ratio", format(sample.correctionReferenceRatio)]]) {
    const item = node(doc, "div"); item.append(text(doc, "dt", caption), text(doc, "dd", value)); list.append(item);
  }
}

function normalizeObservations(sample) {
  const correction = vector([sample.correctionX, sample.correctionY]);
  return (sample.observations || []).map((raw) => {
    const current = vector(raw.currentEndpointPx ?? raw.current_endpoint_px);
    const desired = vector(raw.desiredCorrectionPx ?? raw.desired_correction_px);
    return { limb: raw.limb || raw.contactId || raw.contact_id || "足点", current,
      corrected: add(current, correction), target: add(current, desired),
      residual: finite(raw.residualMagnitudePx ?? raw.residual_magnitude_px) };
  });
}

function renderObservationTable(doc, body, observations) {
  body.replaceChildren();
  if (!observations.length) { body.append(tableCell(doc, "当前帧没有足点观察。", 5)); return; }
  for (const item of observations) {
    const row = node(doc, "tr");
    row.append(text(doc, "th", item.limb), text(doc, "td", point(item.current)), text(doc, "td", point(item.corrected)),
      text(doc, "td", point(item.target)), text(doc, "td", format(item.residual, " px")));
    row.children[0]?.setAttribute?.("scope", "row"); body.append(row);
  }
}

function renderFootOverlay(doc, svg, observations) {
  svg.replaceChildren();
  observations.forEach((item, index) => {
    if (!item.current) return;
    if (item.corrected) svg.append(svgNode(doc, "line", "foot-correction-line", line(item.current, item.corrected)));
    if (item.corrected && item.target) svg.append(svgNode(doc, "line", "foot-residual-line", line(item.corrected, item.target)));
    const offset = index % 2 ? -14 : 14;
    const caption = label(doc, item.current[0] + offset, item.current[1] - 14,
      item.limb || `foot ${index + 1}`, "foot-label");
    if (index % 2) caption.setAttribute("text-anchor", "end");
    svg.append(circle(doc, "foot-current", item.current), ...(item.corrected ? [circle(doc, "foot-corrected", item.corrected)] : []),
      ...(item.target ? [circle(doc, "foot-target", item.target, 10)] : []), caption);
  });
}

function svgNode(doc, tag, className, attrs = {}) { const item = doc.createElementNS(SVG_NS, tag); item.setAttribute("class", className); for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, round(value)); return item; }
function path(doc, className, d) { return svgNode(doc, "path", className, { d }); }
function label(doc, x, y, value, className = "chart-label") { const item = svgNode(doc, "text", className, { x, y }); item.textContent = value; return item; }
function circle(doc, className, xy, radius = 8) { return svgNode(doc, "circle", className, { cx: xy[0], cy: xy[1], r: radius }); }
function line(start, end) { return { x1: start[0], y1: start[1], x2: end[0], y2: end[1] }; }
function node(doc, tag, className = "") { const item = doc.createElement(tag); if (className) item.className = className; return item; }
function text(doc, tag, value, className = "") { const item = node(doc, tag, className); item.textContent = String(value ?? "—"); return item; }
function tableCell(doc, message, span) { const row = node(doc, "tr"); const cell = text(doc, "td", message); cell.setAttribute("colspan", span); row.append(cell); return row; }
function finite(value) { return Number.isFinite(value) ? value : null; }
function vector(value) { return Array.isArray(value) && value.length === 2 && value.every(Number.isFinite) ? value : null; }
function add(left, right) { return left && right ? [left[0] + right[0], left[1] + right[1]] : null; }
function divide(value, limit) { return Number.isFinite(value) && Number.isFinite(limit) && limit > 0 ? value / limit : null; }
function utilization(value, limit) { return divide(value, limit); }
function format(value, suffix = "") { return Number.isFinite(value) ? `${Number(value).toFixed(3)}${suffix}` : "—"; }
function percent(value) { return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—"; }
function point(value) { return value ? `${format(value[0])}, ${format(value[1])}` : "—"; }
function range(start, end) { return start === end ? String(start ?? "—") : `${start ?? "—"}–${end ?? "—"}`; }
function humanState(value) { return value === "candidate" ? "候选" : value === "unconstrained" ? "不可约束" : String(value || "未知"); }
function humanSupport(value) { return value === "dual_support" ? "双脚支撑" : value === "single_support" ? "单脚支撑" : value === "none" ? "无支撑" : String(value || "未知"); }
function clamp(value, minimum, maximum) { return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum)); }
function round(value) { return typeof value === "number" ? String(Math.round(value * 100) / 100) : String(value); }
