"use strict";

import { DEFAULT_TARGET_VERSION, TARGET_VERSIONS } from "./workbench-automation-contract.js";
import { workbenchLayout } from "./workbench-layout.js";

export const AUTOMATION_STATUS = {
  pending: "等待开始", running: "正在构建", needs_review: "需要复核", succeeded: "预览已就绪",
  blocked: "暂时无法构建", failed: "构建失败", canceled: "已取消",
};
const TYPES = {
  layer: "图层", semantic: "图层语义", side: "左右侧", split: "图层拆分", joint: "关节",
  pivot: "Pivot", binding: "骨骼绑定", rig: "结构", geometry: "几何", project: "项目",
};
const ADVICE = {
  semantic_review_required: "确认图层语义和角色左右侧。", pivot_review_required: "检查图层并确认 Pivot 位置。",
  binding_review_required: "选择并复核目标骨骼。", layer_review_required: "检查图层保留方式与 QA 标记。",
  joint_review_required: "对照证据确认关节位置。", joint_candidate_rejected: "选择其他候选，或手工设置关节。",
  joint_unobservable: "该关节已标记为不可观测；有更好证据时再检查。", split_review_required: "检查左右子图，确认或调整切分。",
  split_candidate_rejected: "先调整已拒绝的切分方案。", split_decision_stale: "重新生成切分证据并复核。",
  project_review_required: "完成剩余项目复核并保存校正。", region_geometry_unsupported: "调整当前不支持的几何或图层设置。",
  certification_exact_entry_required: "请使用现有精确认证流程。",
};
const RISKS = { low: "低风险", medium: "中风险", high: "高风险", critical: "需优先处理" };
const REASONS = {
  project_review_required: "请复核图层与关节，然后保存校正。",
  spine_preview_review_required: "完成结构复核后，系统会继续构建预览。",
  project_changed_during_snapshot: "项目已发生变化，请保存并刷新后重试。",
  project_snapshot_stale: "项目已发生变化，请刷新后重试。",
  pipeline_artifact_invalid: "预览工件校验失败，请检查项目。",
  pipeline_canceled: "构建已取消。",
  region_geometry_unsupported: "当前结构暂不支持区域预览，请检查复核队列。",
};

export function automationReason(code) {
  return REASONS[code] || "请检查项目状态后重试；如仍失败，请查看 QA 报告。";
}

function node(document, tag, text, className) {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
}

export function createAutomationView(document, callbacks) {
  const mount = document.getElementById("automationMount");
  const section = node(document, "section", "", "automation-panel inspector-section");
  section.setAttribute("aria-labelledby", "automationHeading");
  const heading = node(document, "h3", "Spine 预览与异常复核");
  heading.id = "automationHeading";
  const description = node(document, "p", `从已保存的图层构建 Spine ${DEFAULT_TARGET_VERSION} 静态预览。`, "automation-description");
  const targetRow = node(document, "div", "", "automation-target");
  const targetLabel = node(document, "label", "Spine 版本");
  targetLabel.setAttribute("for", "automationTargetVersion");
  const targetSelect = node(document, "select");
  targetSelect.id = "automationTargetVersion";
  for (const version of TARGET_VERSIONS) {
    const option = node(document, "option", version === DEFAULT_TARGET_VERSION ? `${version}（默认）` : version);
    option.value = version; targetSelect.append(option);
  }
  targetSelect.value = DEFAULT_TARGET_VERSION;
  targetRow.append(targetLabel, targetSelect);
  const actions = node(document, "div", "", "automation-actions");
  const build = node(document, "button", "构建 Spine 预览", "button button-primary");
  const refresh = node(document, "button", "刷新", "button button-secondary");
  const cancel = node(document, "button", "取消构建", "button button-secondary");
  for (const button of [build, refresh, cancel]) button.type = "button";
  const download = node(document, "a", "下载 JSON / Atlas / PNG / QA", "button button-secondary");
  download.setAttribute("download", "");
  const importHelp = node(document, "p", "完整解压后，在 Spine 中导入 editor/skeleton.json；独立图片位于 editor/images。", "automation-description");
  const status = node(document, "p", "请选择项目。", "automation-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const steps = node(document, "ol", "", "automation-steps");
  const queueHeading = node(document, "h4", "待复核项");
  const queue = node(document, "ul", "", "automation-queue");
  const note = node(document, "p", "静态预览不包含动作，也未执行官方 Runtime 验证。", "automation-description");
  actions.append(build, refresh, cancel);
  section.append(heading, description, targetRow, actions, status, steps, download, importHelp, queueHeading, queue, note);
  const layout = workbenchLayout(document);
  if (layout) { layout.mount("export", section); layout.mountIssues("static", queueHeading, queue); }
  else mount?.append(section);
  build.addEventListener("click", () => callbacks.start());
  refresh.addEventListener("click", () => callbacks.refresh());
  cancel.addEventListener("click", () => callbacks.cancel());
  targetSelect.addEventListener("change", () => callbacks.setTarget(targetSelect.value));
  download.addEventListener("click", (event) => { if (!callbacks.canDownload()) event.preventDefault(); });

  function render(model) {
    targetSelect.value = model.targetVersion || DEFAULT_TARGET_VERSION;
    description.textContent = `从已保存的图层构建 Spine ${targetSelect.value} 静态预览。`;
    build.disabled = !model.canStart;
    refresh.disabled = !model.hasProject || model.fetching;
    cancel.hidden = !model.canCancel;
    cancel.disabled = model.canceling;
    download.hidden = !model.downloadUrl;
    importHelp.hidden = !model.downloadUrl;
    if (model.downloadUrl) download.setAttribute("href", model.downloadUrl);
    else download.removeAttribute("href");
    status.textContent = model.message;
    section.setAttribute("aria-busy", String(model.fetching || model.active));
    steps.replaceChildren(...(model.steps || []).map((step, index) => node(document, "li",
      `${["解析项目", "构建区域骨架", "编译 Spine 预览"][index] || "构建阶段"} · ${AUTOMATION_STATUS[step.status] || "等待开始"}`)));
    queueHeading.textContent = `待复核项 · ${model.items.length}`;
    queue.replaceChildren(...model.items.map((item) => renderItem(item)));
    if (!model.items.length) queue.append(node(document, "li", model.fetching ? "正在读取…" : "当前没有待复核项。"));
  }

  function renderItem(item) {
    const row = node(document, "li", "", "automation-review-item");
    const title = node(document, "strong", `${TYPES[item.type] || "复核项"} · ${item.entity_id || "项目"}`);
    const risk = node(document, "span", item.blocking === false ? "参考信息 · 不阻塞预览" : RISKS[item.risk] || "需要复核", "automation-risk");
    row.append(title, risk);
    row.append(node(document, "p", ADVICE[item.reason_code] || "请检查此项并保存校正。"));
    const locate = node(document, "button", "定位并复核", "text-button");
    locate.type = "button";
    locate.disabled = !callbacks.canLocate(item);
    locate.addEventListener("click", () => callbacks.locate(item));
    row.append(locate);
    for (const evidence of item.evidence || []) {
      const link = node(document, "a", evidence.kind === "layer_image" ? "查看图层证据" : "查看角色合成图", "automation-evidence");
      link.setAttribute("href", evidence.url);
      link.setAttribute("target", "_blank"); link.setAttribute("rel", "noopener noreferrer");
      row.append(link);
    }
    row.append(node(document, "p", "回退：在新校正版本中恢复之前的复核值。", "automation-detail"));
    row.append(node(document, "p", "修改后需重新构建图层清单、区域骨架和 Spine 预览。", "automation-detail"));
    return row;
  }
  return { render };
}
