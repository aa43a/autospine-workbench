"use strict";

import { animatedReason } from "./workbench-animated-contract.js";

export function readAnimatedRebase(value, context) {
  if (value === undefined || value === null) return null;
  if (!["ready", "blocked"].includes(value.status)
    || value.status === "ready" && !/^[a-f0-9]{64}$/.test(value.expected_registration_sha256 || "")
    || !Array.isArray(value.changed_joint_ids) || value.changed_joint_ids.some((id) => typeof id !== "string")
    || !Array.isArray(value.unsupported_items)) throw new Error("animated_rebase_invalid");
  if (value.ignored_joint_ids !== undefined && (!Array.isArray(value.ignored_joint_ids)
    || value.ignored_joint_ids.some((id) => typeof id !== "string"))) throw new Error("animated_rebase_invalid");
  if (value.expected_resolved_sha256 && context && value.expected_resolved_sha256 !== context.resolvedSha) throw new Error("project_snapshot_stale");
  return value;
}

const FIELDS = { x: "水平坐标", y: "垂直坐标", layer_overrides: "图层校正", joint_overrides: "关节校正",
  split_decisions: "切分决定", joint_decisions: "关节决定", canonical_role: "图层语义", side: "左右侧",
  disposition: "图层保留方式", visible: "图层可见性", pivot_xy: "旋转中心", candidate_bone: "绑定骨骼", split_spec: "图层切分方案" };
const REASONS = {
  animated_rebase_audit_or_texture_changed: "原始审计或图层纹理已变化，需要重新核验动画来源。",
  animated_rebase_joint_decision_unsupported: "已保存关节候选采用或拒绝决定；坐标同步不能代替该决定的复核。",
  animated_rebase_split_unsupported: "图层切分发生变化，需要重新生成分区与绑定来源。",
  animated_rebase_layer_override_unsupported: "图层属性已变化，需要重新复核语义、结构或绑定来源。",
  animated_rebase_joint_override_removed: "此前已同步的关节校正已被移除。请选择该关节，核对 X/Y 后点击“确认当前关节坐标”，再点顶部“保存校正”。即使坐标未变化也需要明确确认；图层的“确认语义、Pivot 与目标骨”不能代替此操作。",
};
export function rebaseItemDescription(item) {
  if (typeof item === "string") return REASONS[item] || animatedReason(item);
  const entity = item?.joint_id || item?.layer_id || item?.entity_id || item?.id || "当前项目";
  const field = FIELDS[item?.field] || item?.field;
  if (item?.reason_code === "animated_rebase_layer_override_unsupported" && item.field === "candidate_bone")
    return `${entity}：图层目标骨修改暂不支持同步。若为误改，选中该图层，点击“撤销本图层目标骨校正”并保存；如需保留该换绑，本次动画同步仍需等待绑定迁移支持。`;
  if (REASONS[item?.reason_code]) return `${entity}${field ? ` · ${field}` : ""}：${REASONS[item.reason_code]}`;
  return field ? `${entity}：${field} 的已保存修改暂不支持同步，请复核此项；现有校正仍保留。`
    : `${entity}：${animatedReason(item?.reason_code)}`;
}

export function createAnimatedRebase(document, synchronize) {
  const section = document.createElement("section"), title = document.createElement("h4");
  const description = document.createElement("p"), changes = document.createElement("p"), ignored = document.createElement("p"), items = document.createElement("ul");
  const button = document.createElement("button"); button.type = "button";
  button.textContent = "同步已保存校正并重建"; button.className = "button button-primary";
  title.textContent = "动画来源需要同步";
  description.textContent = "将主画布中已保存的校正同步到动画链，保留主项目校正记录；受影响的图层绑定会退回待复核。";
  section.append(title, description, changes, ignored, items, button); section.hidden = true;
  button.addEventListener("click", () => { if (!button.disabled) synchronize(); });
  function render(model) {
    const source = model.sourceRebase;
    section.hidden = !source;
    if (!source) return;
    title.textContent = `${Number.isInteger(source.authoring_revision) ? `r${source.authoring_revision} ` : ""}${source.status === "ready" ? "已保存校正可同步到动画" : "当前校正需要进一步处理"}`;
    changes.textContent = source.changed_joint_ids.length
      ? `将同步 ${source.changed_joint_ids.length} 个关节：${source.changed_joint_ids.join("、")}`
      : "将检查已保存校正与动画来源的一致性。";
    ignored.textContent = source.ignored_joint_ids?.length
      ? `当前动画骨架不使用 ${source.ignored_joint_ids.join("、")}；这些点的主项目校正会完整保留。` : "";
    items.replaceChildren(...source.unsupported_items.map((item) => {
      const row = document.createElement("li");
      row.textContent = rebaseItemDescription(item);
      return row;
    }));
    button.hidden = source.status !== "ready"; button.disabled = !model.canRebase;
    button.textContent = model.rebasing ? "正在同步已保存校正…" : "同步已保存校正并重建";
  }
  return { element: section, render };
}
