"use strict";

import { AUTOMATION_STATUS } from "./workbench-automation-view.js";
const REASONS = {
  runner_unavailable: "真实姿态 Runner 尚不可用，请完成隔离 Runner 配置后重试。",
  unsupported: "当前输入尚不支持自动准备，请检查输入质量与图层结构。",
  input_preparation_authoring_edits_unsupported: "当前项目存在尚不支持迁移的结构或图层校正（例如图层拆分、图层属性变更），请检查这些操作后重试。已保存的关节位置可以保留迁移；无需撤销关节校正。",
  preparation_interrupted: "上次来源准备因服务中断而停止，可重新准备。",
  pipeline_queue_full: "准备队列已满，请稍后重试。",
};
export function preparationReason(code) {
  if (Object.hasOwn(REASONS, code)) return REASONS[code];
  if (code?.includes("runner") || code?.includes("model")) return REASONS.runner_unavailable;
  if (code?.includes("changed") || code?.includes("stale")) return "项目输入已变化，请刷新后重新准备。";
  if (code === "unsupported") return REASONS.unsupported;
  return "准备未完成，请检查输入和 Runner 状态后重试。";
}
export function preparationSuccess(result) {
  if (!Array.isArray(result?.imported_joint_ids)) return "来源已准备，请前往关节复核检查其余检测点。";
  const ignored = result.ignored_joint_ids || [];
  return `来源已准备，已迁入 ${result.imported_joint_ids.length} 个已保存的关节校正。模型原始观测与人工校正分开记录；其余检测点仍需复核。`
    + (ignored.length ? ` ${ignored.join('、')} 保留在主项目中，未迁入当前动画骨架。` : '');
}
export function createPreparationView(document, actions) {
  const element = document.createElement("section"); element.className = "automation-panel";
  const heading = document.createElement("h4"); heading.textContent = "准备动画来源";
  const description = document.createElement("p");
  description.textContent = "从当前 audit 运行真实姿态检测，生成待复核骨架与绑定来源。已保存的关节校正会保留；模型观测与人工校正分开记录，未复核的检测点仍需明确复核。";
  const status = document.createElement("p"); status.setAttribute("role", "status");
  const controls = document.createElement("div"); controls.className = "automation-actions";
  const prepare = document.createElement("button"), refresh = document.createElement("button"), cancel = document.createElement("button");
  for (const [button, label, action] of [[prepare, "准备动画来源", actions.start], [refresh, "检查准备条件", actions.refresh], [cancel, "取消来源准备", actions.cancel]]) {
    button.type = "button"; button.className = "button button-secondary"; button.textContent = label;
    button.addEventListener("click", action); controls.append(button);
  }
  prepare.className = "button button-primary";
  const steps = document.createElement("ol"); element.append(heading, description, status, controls, steps);
  const labels = { "prepare-source": "准备当前图层来源", "run-pose": "运行真实姿态检测", "register-review": "登记待复核来源" };
  return { element, render(model) {
    element.hidden = !model.visible; prepare.disabled = !model.canStart; refresh.disabled = model.busy && !model.canCancel;
    cancel.hidden = !model.canCancel; cancel.disabled = model.canceling;
    status.textContent = model.message; element.setAttribute("aria-busy", String(model.busy));
    steps.replaceChildren(...model.progress.map((step) => {
      const row = document.createElement("li"); row.textContent = `${labels[step.id] || "准备阶段"} · ${AUTOMATION_STATUS[step.status] || "等待开始"}`; return row;
    }));
  } };
}
