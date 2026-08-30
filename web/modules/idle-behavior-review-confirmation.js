"use strict";

const IDS = Object.freeze([
  "decisionDialog", "decisionDialogProject", "decisionDialogMotion",
  "decisionDialogAction", "decisionDialogConsequence",
  "cancelDecision", "commitDecision",
]);

const DECISIONS = Object.freeze({
  adjust: Object.freeze({
    label: "保存当前身体摆动参数",
    consequence: "将创建新的 P10.1 人工 revision；结果仍是待探针草稿，必须继续通过结构与视觉检查。",
  }),
  reject: Object.freeze({
    label: "不使用身体摆动",
    consequence: "将记录本动作不采用身体摆动，并把该候选标记为不适用；以后仍可创建新 revision 重新选择。",
  }),
  unobservable: Object.freeze({
    label: "当前无法判断",
    consequence: "将记录当前证据不足并把该候选标记为不适用；需要补充证据或创建新 revision 后才能继续。",
  }),
});

export function idleDecisionConfirmationElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少 P10 二次确认元素：${id}`);
    return [id, element];
  }));
}

export function describeIdleDecision(entry, action) {
  const copy = DECISIONS[action];
  if (!copy) throw new Error("未知的身体摆动决定");
  const packageRow = entry?.package;
  if (!packageRow?.project_id || !packageRow?.motion_id || !packageRow?.clip_id) {
    throw new Error("身体摆动决定缺少项目或动作身份");
  }
  return {
    project: packageRow.project_id,
    motion: `${packageRow.motion_id} · ${packageRow.clip_id}`,
    action: copy.label,
    consequence: copy.consequence,
  };
}

export function createIdleDecisionConfirmation({
  elements = idleDecisionConfirmationElements(),
  schedule = queueMicrotask,
} = {}) {
  let pending = null;

  elements.cancelDecision.addEventListener("click", () => finish(false));
  elements.commitDecision.addEventListener("click", () => finish(true));
  elements.decisionDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    finish(false);
  });
  elements.decisionDialog.addEventListener("click", (event) => {
    if (event.target === elements.decisionDialog) finish(false);
  });
  elements.decisionDialog.addEventListener("close", settle);

  return Object.freeze({ request, isOpen: () => pending !== null });

  function request({ entry, action, invoker = null }) {
    if (pending) return Promise.resolve(false);
    const summary = describeIdleDecision(entry, action);
    elements.decisionDialogProject.textContent = summary.project;
    elements.decisionDialogMotion.textContent = summary.motion;
    elements.decisionDialogAction.textContent = summary.action;
    elements.decisionDialogConsequence.textContent = summary.consequence;
    elements.commitDecision.disabled = false;
    elements.decisionDialog.returnValue = "";

    return new Promise((resolve, reject) => {
      pending = { resolve, reject, invoker };
      try {
        elements.decisionDialog.showModal();
        elements.cancelDecision.focus({ preventScroll: true });
      } catch (error) {
        pending = null;
        reject(error);
      }
    });
  }

  function finish(confirmed) {
    if (!pending) return;
    elements.commitDecision.disabled = true;
    elements.decisionDialog.close(confirmed ? "confirm" : "cancel");
  }

  function settle() {
    if (!pending) return;
    const current = pending;
    pending = null;
    const confirmed = elements.decisionDialog.returnValue === "confirm";
    current.resolve(confirmed);
    if (!confirmed && typeof current.invoker?.focus === "function") {
      schedule(() => {
        if (current.invoker.isConnected !== false && !current.invoker.disabled) {
          current.invoker.focus({ preventScroll: true });
        }
      });
    }
  }
}
