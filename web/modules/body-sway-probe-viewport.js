"use strict";

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 8;

export function viewportElements(document = globalThis.document) {
  const ids = [
    "previewStage", "previewSvg", "viewportZoomOut", "viewportZoom",
    "viewportZoomValue", "viewportZoomIn", "viewportFitMotion",
    "viewportReset", "viewportStatus",
  ];
  return Object.fromEntries(ids.map((id) => {
    const element = document.getElementById(id);
    if (!element) throw new Error(`缺少动作视口元素：${id}`);
    return [id, element];
  }));
}

export function createBodySwayProbeViewport(elements, dependencies = {}) {
  const onViewChange = dependencies.onViewChange || (() => {});
  let canvas = null;
  let envelope = null;
  let view = null;
  let drag = null;

  elements.viewportZoomOut.addEventListener("click", () => zoomBy(1 / 1.2));
  elements.viewportZoomIn.addEventListener("click", () => zoomBy(1.2));
  elements.viewportZoom.addEventListener("input", () => {
    const target = clamp(Number(elements.viewportZoom.value) / 100, MIN_ZOOM, MAX_ZOOM);
    setZoom(target);
  });
  elements.viewportFitMotion.addEventListener("click", fitMotion);
  elements.viewportReset.addEventListener("click", resetSource);
  elements.previewStage.addEventListener("wheel", onWheel, { passive: false });
  elements.previewStage.addEventListener("pointerdown", startPan);
  elements.previewStage.addEventListener("pointermove", continuePan);
  elements.previewStage.addEventListener("pointerup", endPan);
  elements.previewStage.addEventListener("pointercancel", endPan);
  elements.previewStage.addEventListener("keydown", onKeyDown);

  reset();
  return Object.freeze({ load, reset, fitMotion, resetSource, currentView });

  function load(nextCanvas, viewportFit = null) {
    canvas = normalizeCanvas(nextCanvas);
    envelope = normalizeEnvelope(viewportFit?.document?.motion_envelope
      ?? viewportFit?.motion_envelope);
    elements.viewportZoom.disabled = false;
    elements.viewportZoomOut.disabled = false;
    elements.viewportZoomIn.disabled = false;
    elements.viewportReset.disabled = false;
    elements.viewportFitMotion.disabled = !envelope;
    if (envelope) fitMotion();
    else resetSource();
  }

  function reset() {
    canvas = null;
    envelope = null;
    view = null;
    drag = null;
    elements.previewStage.dataset.panning = "false";
    elements.viewportZoom.value = "100";
    elements.viewportZoomValue.textContent = "100%";
    for (const control of [
      elements.viewportZoom, elements.viewportZoomOut, elements.viewportZoomIn,
      elements.viewportFitMotion, elements.viewportReset,
    ]) control.disabled = true;
    elements.viewportStatus.textContent = "等待动作包络。";
    onViewChange(null);
  }

  function fitMotion() {
    if (!canvas || !envelope) return;
    const padded = padBounds(envelope, Math.max(envelope.width, envelope.height) * 0.04);
    view = coverAspect(padded, canvas.width / canvas.height);
    applyView("已自动适配完整动作包络；拖拽可平移，滚轮可缩放。");
  }

  function resetSource() {
    if (!canvas) return;
    view = { x: 0, y: 0, width: canvas.width, height: canvas.height };
    applyView("当前显示原始素材框；红色证据可能位于框外。", 1);
  }

  function zoomBy(factor, anchor = null) {
    if (!canvas || !view || !Number.isFinite(factor) || factor <= 0) return;
    const current = canvas.width / view.width;
    setZoom(clamp(current * factor, MIN_ZOOM, MAX_ZOOM), anchor);
  }

  function setZoom(nextZoom, anchor = null) {
    if (!canvas || !view) return;
    const oldWidth = view.width;
    const oldHeight = view.height;
    const width = canvas.width / nextZoom;
    const height = canvas.height / nextZoom;
    const fx = anchor?.x ?? 0.5;
    const fy = anchor?.y ?? 0.5;
    view = {
      x: view.x + (oldWidth - width) * fx,
      y: view.y + (oldHeight - height) * fy,
      width, height,
    };
    applyView("自定义视口只影响预览，不会改写素材坐标或绑定决定。", nextZoom);
  }

  function onWheel(event) {
    if (!canvas) return;
    event.preventDefault();
    const rect = elements.previewStage.getBoundingClientRect();
    const anchor = normalizedContentPoint(
      rect, canvas.width / canvas.height, event.clientX, event.clientY,
    );
    zoomBy(event.deltaY > 0 ? 1 / 1.12 : 1.12, anchor);
  }

  function startPan(event) {
    if (!view || event.button !== 0) return;
    drag = {
      pointerId: event.pointerId, x: event.clientX, y: event.clientY,
      view: { ...view },
    };
    elements.previewStage.dataset.panning = "true";
    elements.previewStage.setPointerCapture?.(event.pointerId);
  }

  function continuePan(event) {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const rect = meetContentRect(
      elements.previewStage.getBoundingClientRect(), canvas.width / canvas.height,
    );
    if (!(rect.width > 0 && rect.height > 0)) return;
    view = {
      ...drag.view,
      x: drag.view.x - (event.clientX - drag.x) * drag.view.width / rect.width,
      y: drag.view.y - (event.clientY - drag.y) * drag.view.height / rect.height,
    };
    applyView("已平移到自定义视口；选择“适配全部动作”可恢复自动建议。");
  }

  function endPan(event) {
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (elements.previewStage.hasPointerCapture?.(event.pointerId)) {
      elements.previewStage.releasePointerCapture(event.pointerId);
    }
    drag = null;
    elements.previewStage.dataset.panning = "false";
  }

  function onKeyDown(event) {
    if (!view) return;
    if (["+", "="].includes(event.key)) zoomBy(1.2);
    else if (["-", "_"].includes(event.key)) zoomBy(1 / 1.2);
    else if (event.key === "0") resetSource();
    else if (event.key.toLowerCase() === "f") fitMotion();
    else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      const dx = event.key === "ArrowLeft" ? -0.05 : event.key === "ArrowRight" ? 0.05 : 0;
      const dy = event.key === "ArrowUp" ? -0.05 : event.key === "ArrowDown" ? 0.05 : 0;
      view = { ...view, x: view.x + dx * view.width, y: view.y + dy * view.height };
      applyView("已用方向键平移自定义视口。");
    } else return;
    event.preventDefault();
  }

  function applyView(message, knownZoom = null) {
    if (!view || !canvas) return;
    elements.previewSvg.setAttribute("viewBox", [view.x, view.y, view.width, view.height].join(" "));
    const zoom = knownZoom ?? canvas.width / view.width;
    const percent = Math.round(clamp(zoom, MIN_ZOOM, MAX_ZOOM) * 100);
    elements.viewportZoom.value = String(percent);
    elements.viewportZoomValue.textContent = `${percent}%`;
    elements.viewportStatus.textContent = message;
    onViewChange({ ...view });
  }

  function currentView() {
    return view ? { ...view } : null;
  }
}

export function normalizedContentPoint(rect, aspect, clientX, clientY) {
  const content = meetContentRect(rect, aspect);
  if (!(content.width > 0 && content.height > 0)) return null;
  return {
    x: clamp((clientX - content.left) / content.width, 0, 1),
    y: clamp((clientY - content.top) / content.height, 0, 1),
  };
}

export function meetContentRect(rect, aspect) {
  if (!(rect?.width > 0 && rect?.height > 0 && aspect > 0)) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }
  const boxAspect = rect.width / rect.height;
  if (boxAspect > aspect) {
    const width = rect.height * aspect;
    return {
      left: rect.left + (rect.width - width) / 2,
      top: rect.top, width, height: rect.height,
    };
  }
  const height = rect.width / aspect;
  return {
    left: rect.left, top: rect.top + (rect.height - height) / 2,
    width: rect.width, height,
  };
}

export function coverAspect(bounds, aspect) {
  if (!(aspect > 0)) throw new Error("视口比例无效");
  let { x, y, width, height } = bounds;
  if (width / height > aspect) {
    const next = width / aspect;
    y -= (next - height) / 2;
    height = next;
  } else {
    const next = height * aspect;
    x -= (next - width) / 2;
    width = next;
  }
  return { x, y, width, height };
}

function normalizeCanvas(value) {
  const width = Number(value?.width);
  const height = Number(value?.height);
  if (!(width > 0 && height > 0)) throw new Error("素材画布尺寸无效");
  return { width, height };
}

function normalizeEnvelope(value) {
  const min = value?.min_xy;
  const max = value?.max_xy;
  if (!Array.isArray(min) || !Array.isArray(max)) return null;
  const [minX, minY, maxX, maxY] = [...min, ...max].map(Number);
  if (![minX, minY, maxX, maxY].every(Number.isFinite)
      || !(maxX > minX && maxY > minY)) return null;
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function padBounds(bounds, padding) {
  return {
    x: bounds.x - padding, y: bounds.y - padding,
    width: bounds.width + padding * 2, height: bounds.height + padding * 2,
  };
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}
