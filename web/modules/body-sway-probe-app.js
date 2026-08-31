"use strict";

import { createBodySwayProbeApi } from "./body-sway-probe-api.js";
import {
  normalizeProbeEntry, reportDownload, requireInventoryEntryMatch,
} from "./body-sway-probe-contract.js";
import { createBodySwayProbeLoader } from "./body-sway-probe-loader.js";
import { createBodySwayProbePreview } from "./body-sway-probe-preview.js";
import {
  createBodySwayProbeViewport, viewportElements,
} from "./body-sway-probe-viewport.js";
import {
  canvasAdjustmentElements, renderCanvasAdjustment, resetCanvasAdjustmentView,
} from "./body-sway-canvas-adjustment-view.js";
import { createCaptureFramingApi } from "./body-sway-capture-framing-api.js";
import {
  captureFramingConfirmationElements, createCaptureFramingConfirmation,
} from "./body-sway-capture-framing-confirmation.js";
import {
  createCaptureFramingController,
} from "./body-sway-capture-framing-controller.js";
import { captureFramingElements } from "./body-sway-capture-framing-view.js";
import {
  probeElements, renderProbeEntry, resetProbeView, setStatus,
} from "./body-sway-probe-view.js";

const elements = probeElements();
const canvasElements = canvasAdjustmentElements();
const framingElements = captureFramingElements();
const viewportControls = viewportElements();
const api = createBodySwayProbeApi();
const framingApi = createCaptureFramingApi();
const framingConfirmation = createCaptureFramingConfirmation({
  elements: captureFramingConfirmationElements(),
});
const preview = createBodySwayProbePreview({
  svg: elements.previewSvg,
  fallback: elements.previewFallback,
  playButton: elements.playPreview,
  timeline: elements.sampleTimeline,
  timeOutput: elements.sampleTime,
  position: elements.samplePosition,
});
const viewport = createBodySwayProbeViewport(viewportControls, {
  onViewChange: preview.setView,
});
let currentEntry = null;
let currentDownload = null;
let loader = null;
const framingController = createCaptureFramingController({
  elements: framingElements,
  api: framingApi,
  confirmation: framingConfirmation,
  onReload: (prefix) => loader?.reload(prefix),
});

loader = createBodySwayProbeLoader({
  panel: elements.autoEntryPanel,
  projectSelect: elements.projectSelect,
  reloadButton: elements.reloadProject,
  status: elements.autoLoadStatus,
}, {
  api,
  onReset: reset,
  onLoad: loadEntry,
});

elements.downloadReport.addEventListener("click", downloadReport);
loader.start();

function reset() {
  currentEntry = null;
  currentDownload = null;
  preview.reset();
  viewport.reset();
  resetProbeView(elements);
  resetCanvasAdjustmentView(canvasElements);
  framingController.reset();
}

async function loadEntry(payload, context) {
  if (!context.isCurrent()) return;
  const entry = normalizeProbeEntry(payload, context.packageRow.package_id);
  requireInventoryEntryMatch(context.packageRow, entry);
  if (!context.isCurrent()) return;
  currentEntry = entry;
  currentDownload = reportDownload(entry);
  renderProbeEntry(elements, entry);
  renderCanvasAdjustment(canvasElements, entry);
  framingController.load(entry);
  preview.load(entry.preview, entry.viewportFit);
  if (entry.preview) viewport.load(entry.preview.canvas, entry.viewportFit);
  return entry;
}

function downloadReport() {
  if (!currentEntry || !currentDownload) {
    setStatus(elements.nextHint, "当前没有可下载的结构探针报告。", "warning");
    return;
  }
  try {
    const raw = `${JSON.stringify(currentDownload.document, null, 2)}\n`;
    const blob = new Blob([raw], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = currentDownload.filename;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    globalThis.setTimeout(() => URL.revokeObjectURL(url), 0);
    setStatus(elements.nextHint,
      `已下载 ${currentDownload.filename}；正常流程仍使用服务端精确结果。`, "success");
  } catch (error) {
    setStatus(elements.nextHint,
      `报告下载失败：${error instanceof Error ? error.message : "未知错误"}`, "error");
  }
}
