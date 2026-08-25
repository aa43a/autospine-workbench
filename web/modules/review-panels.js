"use strict";

import { createIcon, numberOr } from "./ui-primitives.js";
import { compositeQaFlag, unresolvedJointIds } from "./workflow.js";


export function normalizeQaFlags(value) {
  const list = Array.isArray(value) ? value : value ? [value] : [];
  return list.map((flag, index) => {
    if (typeof flag === "string") return { code: flag, message: flag, severity: "warning" };
    return {
      ...flag,
      code: String(flag?.code || flag?.id || `QA-${index + 1}`),
      message: String(flag?.message || flag?.detail || flag?.label || flag?.code || "需要复核"),
      severity: String(flag?.severity || flag?.level || "warning").toLowerCase(),
    };
  });
}


export function layerQaFlags(layer) {
  const flags = normalizeQaFlags(layer.qa_flags);
  if (layer.empty && !flags.some((flag) => flag.code === "EMPTY_LAYER")) {
    flags.push({ code: "EMPTY_LAYER", message: "空图层需要排除或复核", severity: "warning" });
  }
  if (layer.disposition === "review" && !flags.some((flag) => flag.code === "LAYER_REVIEW")) {
    flags.push({ code: "LAYER_REVIEW", message: "图层语义或侧别需要人工复核", severity: "warning" });
  }
  return flags;
}


export function collectQaFlags({ project, layers, joints, resolveLayer }) {
  const items = normalizeQaFlags(project?.qa_flags).map((flag) => ({ ...flag, layerId: null }));
  for (const layer of layers) {
    layerQaFlags(resolveLayer(layer)).forEach((flag) => items.push({
      ...flag,
      layerId: String(layer.id),
      layerName: layer.name,
    }));
  }
  const auditWarnings = project?.workflow?.audit_warnings;
  const compositeFlag = compositeQaFlag(auditWarnings);
  if (compositeFlag) items.unshift(compositeFlag);
  if (numberOr(auditWarnings?.empty_layer_count) > 0) {
    items.unshift({
      code: "EMPTY_LAYERS",
      message: `${numberOr(auditWarnings.empty_layer_count)} 个空图层不会参与绑定`,
      severity: "warning",
      layerId: null,
    });
  }
  const unresolvedCount = unresolvedJointIds(project, joints).length;
  if (unresolvedCount) {
    items.push({
      code: "UNRESOLVED_JOINTS",
      message: `${unresolvedCount} 个启发式关节尚未复核，请在骨骼模式校正`,
      severity: "warning",
      layerId: null,
    });
  }
  return items;
}


export function renderQaPanel(elements, flags, onSelectLayer) {
  const doc = elements.qaList.ownerDocument;
  elements.qaCounter.textContent = String(flags.length);
  elements.qaList.replaceChildren();
  if (!flags.length) {
    const empty = doc.createElement("div");
    empty.className = "selection-empty";
    empty.textContent = "当前项目没有 QA 警告。";
    elements.qaList.append(empty);
    return;
  }

  flags.slice(0, 30).forEach((flag) => {
    const item = doc.createElement(flag.layerId ? "button" : "div");
    item.className = "qa-item";
    item.dataset.severity = flag.severity;
    if (flag.layerId) item.type = "button";
    item.append(createIcon("warning", doc));
    const content = doc.createElement("span");
    const title = doc.createElement("strong");
    title.textContent = flag.message;
    const meta = doc.createElement("small");
    meta.textContent = flag.layerId ? `${flag.code} · ${flag.layerName || flag.layerId}` : flag.code;
    content.append(title, meta);
    item.append(content);
    if (flag.layerId) item.addEventListener("click", () => onSelectLayer(flag.layerId));
    elements.qaList.append(item);
  });
}


export function flattenCapabilities(value, prefix = "", depth = 0) {
  if (depth > 4 || value == null) return [];
  if (typeof value !== "object" || Array.isArray(value)) {
    return [{ key: prefix || "value", value }];
  }
  if ("state" in value || "available" in value || "enabled" in value) {
    const stateValue = value.state ?? value.available ?? value.enabled;
    const confidence = Number(value.confidence);
    const display = Number.isFinite(confidence) ? `${stateValue} · ${Math.round(confidence * 100)}%` : stateValue;
    return [{ key: prefix || "capability", value: display, state: String(stateValue).toLowerCase() }];
  }
  return Object.entries(value).flatMap(([key, child]) => (
    flattenCapabilities(child, prefix ? `${prefix}.${key}` : key, depth + 1)
  ));
}


export function renderCapabilitiesPanel(elements, value) {
  const doc = elements.capabilityList.ownerDocument;
  const capabilities = flattenCapabilities(value).slice(0, 40);
  elements.capabilityList.replaceChildren();
  if (!capabilities.length) {
    const empty = doc.createElement("div");
    empty.className = "selection-empty";
    empty.textContent = "暂无能力数据。";
    elements.capabilityList.append(empty);
    return;
  }

  capabilities.forEach((capability) => {
    const row = doc.createElement("div");
    row.className = "capability-row";
    const key = doc.createElement("span");
    key.textContent = capability.key;
    key.title = capability.key;
    const state = doc.createElement("span");
    state.className = "capability-state";
    state.dataset.state = capability.state || String(capability.value).split(" · ")[0].toLowerCase();
    state.textContent = formatCapabilityValue(capability.value);
    row.append(key, state);
    elements.capabilityList.append(row);
  });
}


export function formatCapabilityValue(value) {
  if (typeof value === "boolean") return value ? "ready" : "missing";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "—");
}
