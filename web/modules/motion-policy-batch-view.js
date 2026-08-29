import { validateDecision } from "./motion-policy-review-state.js";

export function renderReviewSegments(container, segments) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  const fragment = doc.createDocumentFragment();
  for (const segment of segments) fragment.append(segmentCard(doc, segment));
  container.append(fragment);
}

export function selectedSegmentIds(container) {
  return [...container.querySelectorAll("[data-segment-select]:checked")]
    .map((input) => input.dataset.segmentId);
}

export function setAllSegmentsSelected(container, selected) {
  container.querySelectorAll("[data-segment-select]:not(:disabled)")
    .forEach((input) => { input.checked = selected; });
}

export function updateSegmentProgress(container, segments, state) {
  for (const segment of segments) {
    const card = container.querySelector(`[data-segment-id="${cssEscape(segment.segmentId)}"]`);
    if (!card) continue;
    const completed = segment.candidateIds.filter((id) => {
      const candidate = state.inventory.candidates.find((row) => row.candidateId === id);
      return candidate && !validateDecision(candidate, state.decisions.get(id));
    }).length;
    const progress = card.querySelector("[data-segment-progress]");
    progress.textContent = segment.candidateIds.length
      ? `${completed} / ${segment.candidateIds.length} 已有有效决定`
      : "此段没有待裁决事件";
    card.dataset.complete = String(completed === segment.candidateIds.length);
  }
}

export function renderDecisionSummary(container, state) {
  const counts = { accept: 0, adjust: 0, reject: 0, unobservable: 0, pending: 0 };
  for (const candidate of state.inventory.candidates) {
    const decision = state.decisions.get(candidate.candidateId);
    if (!validateDecision(candidate, decision)) counts[decision.action] += 1;
    else counts.pending += 1;
  }
  container.replaceChildren();
  for (const [key, caption] of [
    ["accept", "Accept"], ["adjust", "Adjust"], ["reject", "Reject"],
    ["unobservable", "不可观测"], ["pending", "待处理"],
  ]) {
    const card = node(container.ownerDocument, "div");
    card.append(text(container.ownerDocument, "span", caption), text(container.ownerDocument, "strong", counts[key]));
    container.append(card);
  }
}

function segmentCard(doc, segment) {
  const card = node(doc, "article", "segment-card");
  card.dataset.segmentId = segment.segmentId;
  card.dataset.attention = String(segment.attention);
  const head = node(doc, "div", "segment-head");
  const title = node(doc, "label", "segment-title");
  const checkbox = node(doc, "input", "segment-select");
  checkbox.type = "checkbox";
  checkbox.dataset.segmentSelect = "true";
  checkbox.dataset.segmentId = segment.segmentId;
  checkbox.disabled = segment.candidateIds.length === 0;
  const copy = node(doc, "span");
  copy.append(
    text(doc, "strong", segmentName(segment)),
    text(doc, "small", `${segment.candidateIds.length} 项 · frame ${range(segment.startFrame, segment.endFrame)}`),
  );
  title.append(checkbox, copy);
  head.append(title, text(doc, "span", segment.attention ? "重点" : "连续段", "segment-tag"));
  const metrics = node(doc, "div", "segment-metrics");
  metrics.append(
    metric(doc, "校正峰值", maximum(segment.metrics?.correctionMagnitude), " px"),
    metric(doc, "残差峰值", maximum(segment.metrics?.maximumResidualPx), " px"),
    metric(doc, "ratio 峰值", maximum(segment.metrics?.correctionReferenceRatio), ""),
  );
  const signals = node(doc, "div", "segment-signals");
  for (const [caption, value, tone] of segmentSignals(segment)) {
    const row = node(doc, "p", `segment-signal ${tone}`);
    row.append(text(doc, "strong", caption), doc.createTextNode(value));
    signals.append(row);
  }
  const locate = text(doc, "button", "在时间轴定位", "segment-locate");
  locate.type = "button";
  locate.dataset.locateSegment = segment.segmentId;
  const progress = text(doc, "p", "尚未填写", "segment-progress");
  progress.dataset.segmentProgress = "true";
  card.append(head, signals, metrics, locate, progress);
  return card;
}

function segmentSignals(segment) {
  if (segment.kind === "depth_order") {
    const count = segment.metrics?.eventCount || 0;
    return [["层级证据：", count ? `${count} 个前后关系翻转事件` : "没有前后关系翻转事件", count ? "attention" : "normal"]];
  }
  const result = [];
  if (segment.attention) result.push(["为何重点：", humanReasons(segment.reasons), "attention"]);
  if (segment.supportStates?.length) {
    result.push(["脚部支撑：", segment.supportStates.map(humanSupport).join(" / "), "normal"]);
  }
  if (segment.states?.length) result.push(["算法状态：", segment.states.map(humanState).join(" / "), "normal"]);
  if (segment.rejectedCount) result.push(["禁止 Accept：", `${segment.rejectedCount} 项已被算法拒绝`, "danger"]);
  return result;
}

function humanReasons(reasons = []) {
  return reasons.map((reason) => {
    if (reason === "boundary") return "接触或支撑状态切换";
    if (reason === "jump:p95") return "校正突变";
    if (reason.startsWith("zero:")) return "校正方向翻转";
    if (reason.startsWith("p95:")) return "高值区间";
    if (reason.startsWith("extreme:")) return "极值帧";
    if (reason.startsWith("rejected_")) return "算法拒绝";
    return reason.replaceAll("_", " ");
  }).filter((value, index, all) => all.indexOf(value) === index).join("、") || "人工指定";
}
function humanSupport(value) {
  return ({ dual_support: "双脚支撑", single_support: "单脚支撑", none: "无支撑" })[value] || value;
}
function humanState(value) {
  if (String(value).startsWith("rejected_")) return "已拒绝";
  return ({ candidate: "可裁决", unconstrained: "未约束" })[value] || value;
}

function segmentName(segment) {
  if (segment.kind === "depth_order") return `深度配对 · ${segment.pairId || segment.segmentId}`;
  return `${segment.attention ? "重点窗口" : "普通连续段"} · ${range(segment.startFrame, segment.endFrame)}`;
}
function metric(doc, caption, value, suffix) {
  return text(doc, "span", `${caption} ${format(value)}${value == null ? "" : suffix}`);
}
function maximum(summary) { return Number.isFinite(summary?.maximum) ? summary.maximum : null; }
function format(value) { return value == null ? "—" : Number(value).toFixed(3); }
function range(start, end) { return start === end ? String(start ?? "—") : `${start ?? "—"}–${end ?? "—"}`; }
function node(doc, tag, className = "") {
  const result = doc.createElement(tag);
  if (className) result.className = className;
  return result;
}
function text(doc, tag, value, className = "") {
  const result = node(doc, tag, className);
  result.textContent = String(value);
  return result;
}
function cssEscape(value) {
  return globalThis.CSS?.escape ? CSS.escape(value) : value.replace(/[^A-Za-z0-9_-]/g, "\\$&");
}
