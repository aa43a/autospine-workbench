"use strict";

const IDS = [
  "captureFramingDialog", "captureFramingDialogProject", "captureFramingDialogMotion",
  "captureFramingDialogAction", "captureFramingDialogConsequence",
  "cancelCaptureFraming", "commitCaptureFraming",
];

const DECISIONS = Object.freeze({
  accept: Object.freeze({
    label: "采用自动取景",
    consequence: "将保存一条人工确认记录，并把系统建议的完整动作取景范围交给下一阶段。仍不会授予发布权。",
  }),
  reject: Object.freeze({
    label: "不采用自动取景",
    consequence: "将记录本次不采用该建议。原候选和历史仍会保留，下一阶段不会使用这次取景。",
  }),
  unobservable: Object.freeze({
    label: "当前无法判断",
    consequence: "将记录当前证据不足。需要补充证据或创建新 revision 后才能继续临时 Runtime 预览。",
  }),
});

export function captureFramingConfirmationElements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = doc.getElementById(id);
    if (!element) throw new Error(`缺少自动取景二次确认元素：${id}`);
    return [id, element];
  }));
}

export function describeCaptureFramingDecision(entry, action) {
  const copy = DECISIONS[action];
  const packageRow = entry?.package;
  if (!copy || !packageRow?.project_id || !packageRow?.motion_id || !packageRow?.clip_id) {
    throw new Error("自动取景决定缺少项目、动作或决定类型");
  }
  return {
    project: packageRow.project_id,
    motion: `${packageRow.motion_id} · ${packageRow.clip_id}`,
    action: copy.label,
    consequence: copy.consequence,
  };
}

export function createCaptureFramingConfirmation({
  elements = captureFramingConfirmationElements(), schedule = queueMicrotask,
} = {}) {
  let pending = null;
  elements.cancelCaptureFraming.addEventListener("click", () => finish(false));
  elements.commitCaptureFraming.addEventListener("click", () => finish(true));
  elements.captureFramingDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    finish(false);
  });
  elements.captureFramingDialog.addEventListener("click", (event) => {
    if (event.target === elements.captureFramingDialog) finish(false);
  });
  elements.captureFramingDialog.addEventListener("close", settle);

  return Object.freeze({ request, isOpen: () => pending !== null });

  function request({ entry, action, invoker = null }) {
    if (pending) return Promise.resolve(false);
    const summary = describeCaptureFramingDecision(entry, action);
    elements.captureFramingDialogProject.textContent = summary.project;
    elements.captureFramingDialogMotion.textContent = summary.motion;
    elements.captureFramingDialogAction.textContent = summary.action;
    elements.captureFramingDialogConsequence.textContent = summary.consequence;
    elements.commitCaptureFraming.disabled = false;
    elements.captureFramingDialog.returnValue = "";
    return new Promise((resolve, reject) => {
      pending = { resolve, reject, invoker };
      try {
        elements.captureFramingDialog.showModal();
        elements.cancelCaptureFraming.focus({ preventScroll: true });
      } catch (error) {
        pending = null;
        reject(error);
      }
    });
  }

  function finish(confirmed) {
    if (!pending) return;
    elements.commitCaptureFraming.disabled = true;
    elements.captureFramingDialog.close(confirmed ? "confirm" : "cancel");
  }

  function settle() {
    if (!pending) return;
    const current = pending;
    pending = null;
    const confirmed = elements.captureFramingDialog.returnValue === "confirm";
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
