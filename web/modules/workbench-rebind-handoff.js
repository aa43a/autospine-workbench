"use strict";

import { normalizeProbeEntry } from "./body-sway-probe-contract.js";
import { SAFE_ID, SHA256 } from "./body-sway-probe-contract-utils.js";

const ENDPOINT = "/api/idle-behavior/structural-probes";

export async function loadRegionRebindHandoff(
  search, projectId, apiRequest, currentResolvedSha256,
) {
  const request = parseRegionRebindHandoff(search);
  if (!request) return null;
  if (request.projectId !== projectId) throw new Error("换绑建议与当前项目不一致");
  const payload = await apiRequest(`${ENDPOINT}/${encodeURIComponent(request.packageId)}`);
  const entry = normalizeProbeEntry(payload, request.packageId);
  if (entry.package.project_id !== projectId) throw new Error("换绑建议项目身份已变化");
  if (!SHA256.test(currentResolvedSha256 || "")) {
    throw new Error("当前项目缺少可核验的 Resolved Project 身份");
  }
  const evidenceResolved = entry.technical.report?.source?.p3?.resolved_project_sha256;
  if (evidenceResolved !== currentResolvedSha256) {
    throw new Error("换绑建议来自历史项目快照，请重新运行 P10.2");
  }
  const envelope = entry.rebindCandidates.find((row) =>
    row.candidateSha256 === request.candidateSha256
    && row.attachmentId === request.layerId);
  if (!envelope) throw new Error("换绑建议已过期或不属于所选图层");
  const recommendation = envelope.recommendation;
  if (recommendation.status !== "recommended"
      || recommendation.from_bone_id === recommendation.to_bone_id) {
    throw new Error("当前证据没有可自动预选的换绑建议");
  }
  const selected = envelope.document.candidates.find((row) =>
    row.candidate_id === recommendation.candidate_id);
  const current = envelope.document.candidates.find((row) =>
    row.bone_id === recommendation.from_bone_id);
  if (!selected || !current) throw new Error("换绑候选证据不完整");
  return Object.freeze({
    ...request, entryStatus: entry.status,
    fromBoneId: recommendation.from_bone_id,
    toBoneId: recommendation.to_bone_id,
    improvement: recommendation.relative_motion_improvement,
    currentMetrics: current.metrics,
    proposedMetrics: selected.metrics,
  });
}

export function parseRegionRebindHandoff(search) {
  const params = new URLSearchParams(search || "");
  const names = ["project", "layer", "rebind_package", "rebind_candidate"];
  const present = names.filter((name) => params.has(name));
  if (!present.some((name) => name.startsWith("rebind_"))) return null;
  if (names.some((name) => params.getAll(name).length !== 1)) {
    throw new Error("换绑交接参数不完整或重复");
  }
  const [projectId, layerId, packageId, candidateSha256] = names.map((name) =>
    params.get(name));
  if (!SAFE_ID.test(projectId) || !SAFE_ID.test(layerId)
      || !SHA256.test(packageId) || !SHA256.test(candidateSha256)) {
    throw new Error("换绑交接参数无效");
  }
  return { projectId, layerId, packageId, candidateSha256 };
}

export function createRegionRebindHandoffView(document, callbacks = {}) {
  const mount = document.getElementById("layerFields");
  if (!mount) throw new Error("缺少图层属性面板");
  const panel = document.createElement("section");
  panel.className = "rebind-handoff";
  panel.hidden = true;
  panel.setAttribute("aria-labelledby", "rebindHandoffHeading");
  const eyebrow = textNode(document, "p", "MOTION EVIDENCE", "eyebrow");
  const heading = textNode(document, "h4", "自动换绑建议");
  heading.id = "rebindHandoffHeading";
  const summary = textNode(document, "p", "—", "rebind-summary");
  const metrics = document.createElement("dl");
  metrics.className = "rebind-metrics";
  const notice = textNode(document, "p",
    "建议保持为独立预览；确认后才会写入新的 override revision。", "rebind-notice");
  const actions = document.createElement("div");
  actions.className = "rebind-actions";
  const adopt = button(document, "确认换绑并保存 revision", "button button-primary");
  const dismiss = button(document, "暂不采用", "button button-secondary");
  actions.append(adopt, dismiss);
  panel.append(eyebrow, heading, summary, metrics, notice, actions);
  mount.prepend(panel);
  let current = null;
  adopt.addEventListener("click", () => current && callbacks.onAdopt?.(current));
  dismiss.addEventListener("click", () => current && callbacks.onDismiss?.(current));

  return Object.freeze({ render, clear });

  function render(suggestion, layer, candidateBoneSelect) {
    current = suggestion?.layerId === String(layer?.id) ? suggestion : null;
    panel.hidden = !current;
    if (!current) return;
    const sourceMatches = String(layer?.candidate_bone ?? "") === current.fromBoneId;
    const targetExists = [...candidateBoneSelect.options].some((option) =>
      option.value === current.toBoneId);
    summary.textContent = sourceMatches
      ? `${current.layerId}：${current.fromBoneId} → ${current.toBoneId}（待确认预览）`
      : `候选来源骨是 ${current.fromBoneId}，当前已是 ${layer?.candidate_bone || "未绑定"}。`;
    metrics.replaceChildren(
      metric(document, "动作范围改善", `${(current.improvement * 100).toFixed(1)}%`),
      metric(document, "包络内骨段覆盖", `${current.currentMetrics.setup_subtree_segment_coverage_count} → ${current.proposedMetrics.setup_subtree_segment_coverage_count}`),
      metric(document, "质心相对动作", `${current.currentMetrics.root_compensated_centroid_motion_rms_px.toFixed(1)} → ${current.proposedMetrics.root_compensated_centroid_motion_rms_px.toFixed(1)} px`),
      metric(document, "最大相对动作", `${current.currentMetrics.root_compensated_max_vertex_motion_px.toFixed(1)} → ${current.proposedMetrics.root_compensated_max_vertex_motion_px.toFixed(1)} px`),
      metric(document, "素材框超出（仅诊断）", `${current.currentMetrics.max_viewport_overflow_px.toFixed(1)} → ${current.proposedMetrics.max_viewport_overflow_px.toFixed(1)} px`),
    );
    adopt.disabled = !sourceMatches || !targetExists;
    notice.textContent = sourceMatches
      ? "建议不会填入上方 Rig 表单；只有下方专用确认会通过 provenance 绑定的 adoption 保存。"
      : "当前绑定已变化，旧候选不会重复应用；请重新运行动作结构检查。";
  }

  function clear() {
    current = null;
    panel.hidden = true;
    metrics.replaceChildren();
  }
}

export function createRegionRebindHandoffController(document, dependencies) {
  let suggestion = null;
  const view = createRegionRebindHandoffView(document, {
    onAdopt: adopt,
    onDismiss: dismiss,
  });
  return Object.freeze({ blockGeneralMutation, isActive, load, render, reset });

  function isActive() {
    return Boolean(suggestion);
  }

  function blockGeneralMutation(action) {
    if (!suggestion) return false;
    dependencies.showAlert(
      `自动换绑建议仍待处理；${action}不能采用该建议。请使用专用确认，或先点“暂不采用”。`,
    );
    dependencies.announce("已阻止绕过 provenance 的普通写入");
    return true;
  }

  function load(search, projectId, isCurrent = () => true) {
    void loadExact(search, projectId, isCurrent).catch((error) => {
      if (!isCurrent()) return;
      const message = error instanceof Error ? error.message : "未知错误";
      dependencies.showAlert(`自动换绑建议不可用：${message}`);
      dependencies.announce("自动换绑建议已失效，项目仍可正常编辑");
    });
  }

  async function loadExact(search, projectId, isCurrent) {
    if (!isCurrent()) return;
    const expectedResolvedSha256 = dependencies.currentResolvedSha256();
    const next = await loadRegionRebindHandoff(
      search, projectId, dependencies.apiRequest,
      expectedResolvedSha256,
    );
    if (!isCurrent()) return;
    if (dependencies.currentResolvedSha256() !== expectedResolvedSha256) {
      throw new Error("项目快照已在核验期间变化，请重新运行 P10.2");
    }
    if (!next) {
      const requested = new URLSearchParams(search || "").get("layer");
      if (requested && dependencies.layers().some((row) => String(row.id) === requested)) {
        dependencies.selectLayer(requested);
      }
      return;
    }
    const layer = dependencies.layers().find((row) => String(row.id) === next.layerId);
    if (!layer || dependencies.effectiveLayer(layer).candidate_bone !== next.fromBoneId) {
      throw new Error("换绑建议的来源骨已变化，请重新运行 P10.2");
    }
    suggestion = next;
    dependencies.selectLayer(next.layerId);
    dependencies.announce(`已自动选择 ${next.layerId}；${next.toBoneId} 仅作为待确认预览`);
  }

  function render(layer, candidateBoneSelect) {
    view.render(suggestion, layer, candidateBoneSelect);
  }

  function reset() {
    suggestion = null;
    view.clear();
  }

  async function adopt(next) {
    const layer = dependencies.selectedLayer();
    if (!layer || String(layer.id) !== next.layerId
        || layer.candidate_bone !== next.fromBoneId) {
      dependencies.showAlert("换绑建议已过期；请重新运行 P10.2 后再操作。");
      return;
    }
    const pending = dependencies.isDirty()
      ? "当前其他未保存校正也会一起写入。\n\n" : "";
    if (!globalThis.confirm(
      `${pending}确认把 ${next.layerId} 从 ${next.fromBoneId} 换绑到 ${next.toBoneId}，并保存为新的 override revision？`,
    )) return;
    if (!await dependencies.save(next)) return;
    const savedLayer = dependencies.selectedLayer();
    if (!savedLayer || String(savedLayer.id) !== next.layerId
        || savedLayer.candidate_bone !== next.toBoneId) {
      dependencies.showAlert(
        "保存后的权威项目快照未确认目标骨；建议地址已保留，请刷新项目后复核。",
      );
      dependencies.announce("换绑提交结果不确定；建议地址仍保留");
      return;
    }
    reset();
    consumeAddress();
    dependencies.announce(`换绑已保存：${next.fromBoneId} → ${next.toBoneId}`);
  }

  function dismiss() {
    reset();
    consumeAddress();
    dependencies.renderLayerInspector();
    dependencies.announce("已暂不采用自动换绑建议；没有写入任何 revision");
  }

  function consumeAddress() {
    removeConsumedRebindAddress(dependencies.location, dependencies.history);
  }
}

export function removeConsumedRebindAddress(location = globalThis.location,
  history = globalThis.history) {
  const url = new URL(location.href);
  for (const name of ["rebind_package", "rebind_candidate"]) url.searchParams.delete(name);
  history.replaceState(null, "", url);
}

function metric(document, label, value) {
  const group = document.createElement("div");
  group.append(textNode(document, "dt", label), textNode(document, "dd", value));
  return group;
}

function textNode(document, tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function button(document, label, className) {
  const node = textNode(document, "button", label, className);
  node.type = "button";
  return node;
}
