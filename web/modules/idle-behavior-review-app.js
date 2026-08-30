"use strict";

import {
  IdleBehaviorReviewApiError, createIdleBehaviorReviewApi,
} from "./idle-behavior-review-api.js";
import {
  createIdleDecisionConfirmation,
} from "./idle-behavior-review-confirmation.js";
import { createIdleBehaviorReviewLoader } from "./idle-behavior-review-loader.js";
import {
  buildIdleReviewSubmission, controlsFromParameters,
  initialBodySwayParameters, parametersFromControls,
} from "./idle-behavior-review-model.js";
import { createIdleBehaviorPreview } from "./idle-behavior-review-preview.js";
import {
  idleCanvasDraftElements, markIdleCanvasDraftRestored,
  renderIdleCanvasDraft, resetIdleCanvasDraftView,
} from "./idle-behavior-canvas-adjustment-view.js";
import {
  applyControlValues, controlValues, idleReviewElements, renderIdleReviewEntry,
  resetIdleReviewView, setStatus, showIdleReviewReceipt, syncDecisionControls,
} from "./idle-behavior-review-view.js";

const elements = idleReviewElements();
const canvasElements = idleCanvasDraftElements();
const api = createIdleBehaviorReviewApi();
const decisionConfirmation = createIdleDecisionConfirmation();
const preview = createIdleBehaviorPreview({
  image: elements.previewImage,
  svg: elements.previewSvg,
  fallback: elements.previewFallback,
  playButton: elements.playPreview,
  timeline: elements.timeline,
  timeOutput: elements.timeOutput,
});
let state = emptyState();

const loader = createIdleBehaviorReviewLoader({
  panel: elements.autoEntryPanel,
  projectSelect: elements.projectSelect,
  reloadButton: elements.reloadProject,
  status: elements.autoLoadStatus,
}, {
  api,
  onReset: reset,
  onLoad: loadEntry,
});

for (const input of [
  elements.cycles, elements.lowerAmplitude,
  elements.headAmplitude, elements.phaseDelay,
]) input.addEventListener("input", changeParameters);

elements.explicitConfirmation.addEventListener("change", syncControls);
elements.confirmAdjust.addEventListener(
  "click", (event) => requestDecision("adjust", event.currentTarget),
);
elements.rejectBodySway.addEventListener(
  "click", (event) => requestDecision("reject", event.currentTarget),
);
elements.unobservableBodySway.addEventListener(
  "click", (event) => requestDecision("unobservable", event.currentTarget),
);
canvasElements.restoreCanvasParameters.addEventListener("click", restoreCurrentParameters);

loader.start();

function emptyState() {
  return {
    entry: null, baseParameters: null, baseControls: null, currentParameters: null,
    canvasAdjustmentDraft: null,
    parametersTouched: false, available: false,
    confirming: false, busy: false, committed: false, uncertain: false,
  };
}

function reset() {
  state = emptyState();
  preview.reset();
  resetIdleReviewView(elements);
  resetIdleCanvasDraftView(canvasElements);
}

async function loadEntry(entry, context) {
  if (!context.isCurrent()) return;
  const currentParameters = initialBodySwayParameters(entry);
  const draft = context.canvasAdjustmentDraft;
  const baseParameters = draft?.proposal?.parameters ?? currentParameters;
  const controls = controlsFromParameters(baseParameters);
  state = {
    entry, baseParameters, baseControls: controls, currentParameters,
    canvasAdjustmentDraft: draft, parametersTouched: Boolean(draft),
    available: renderIdleReviewEntry(elements, entry) && entry.history !== null,
    confirming: false, busy: false,
    committed: false,
    uncertain: false,
  };
  applyControlValues(elements, controls);
  elements.explicitConfirmation.checked = false;
  preview.load(entry.preview, baseParameters);
  renderIdleCanvasDraft(canvasElements, draft, currentParameters);
  syncControls();
  setStatus(elements.decisionStatus,
    state.available
      ? (draft
        ? "P10.2 建议已预填但尚未批准；请预览，仍须勾选并通过确认弹窗。"
        : "请先预览并调整；勾选人工确认后才能保存。")
      : "缺少可决定的身体摆动候选或提交基线。",
    state.available ? "warning" : "error");
}

function restoreCurrentParameters() {
  if (!state.entry || !state.canvasAdjustmentDraft || !state.currentParameters
      || state.confirming || state.busy || state.committed || state.uncertain) return;
  const controls = controlsFromParameters(state.currentParameters);
  state = {
    ...state, baseParameters: state.currentParameters, baseControls: controls,
    canvasAdjustmentDraft: null, parametersTouched: false,
  };
  applyControlValues(elements, controls);
  preview.setParameters(state.currentParameters);
  elements.explicitConfirmation.checked = false;
  elements.receiptPanel.hidden = true;
  markIdleCanvasDraftRestored(canvasElements);
  setStatus(elements.decisionStatus,
    "已恢复当前 revision 参数；尚未提交，人工确认仍为空。", "warning");
  syncControls();
}

function changeParameters() {
  if (!state.entry || state.confirming || state.busy || state.committed || state.uncertain) return;
  try {
    const controls = controlValues(elements);
    state = { ...state, parametersTouched: true };
    applyControlValues(elements, controls);
    preview.setParameters(parametersFromControls(controls, state.baseParameters));
    elements.explicitConfirmation.checked = false;
    elements.receiptPanel.hidden = true;
    setStatus(elements.decisionStatus, "参数已改变，请重新查看并进行人工确认。", "warning");
    syncControls();
  } catch (error) {
    setStatus(elements.decisionStatus, errorText(error), "error");
  }
}

function syncControls() {
  syncDecisionControls(elements, {
    available: state.available && !state.committed && !state.uncertain,
    busy: state.confirming || state.busy || state.committed || state.uncertain,
  });
}

async function requestDecision(action, invoker) {
  if (!state.entry || !elements.explicitConfirmation.checked
      || state.confirming || state.busy || state.committed || state.uncertain) return;
  let request;
  const identity = {
    packageId: state.entry.package.package_id,
    candidateSha256: state.entry.candidate_sha256,
  };
  try {
    request = buildIdleReviewSubmission(
      state.entry, action,
      state.parametersTouched ? controlValues(elements) : state.baseControls,
      state.baseParameters,
    );
  } catch (error) {
    setStatus(elements.decisionStatus, errorText(error), "error");
    return;
  }
  state = { ...state, confirming: true };
  loader.setMutationLocked(true);
  syncControls();
  setStatus(elements.decisionStatus,
    "请在确认弹窗中核对项目、动作与决定；取消不会发送请求。", "warning");
  try {
    const confirmed = await decisionConfirmation.request({
      entry: state.entry, action, invoker,
    });
    if (!confirmed) {
      state = { ...state, confirming: false };
      loader.setMutationLocked(false);
      syncControls();
      setStatus(elements.decisionStatus, "已取消，本次决定未发送。", "warning");
      return;
    }
  } catch (error) {
    state = { ...state, confirming: false };
    loader.setMutationLocked(false);
    syncControls();
    setStatus(elements.decisionStatus, `无法打开确认弹窗：${errorText(error)}`, "error");
    return;
  }
  if (!submissionIsCurrent(identity)) {
    state = { ...state, confirming: false, uncertain: true };
    loader.setMutationLocked(false);
    syncControls();
    setStatus(elements.decisionStatus,
      "项目身份在确认期间发生变化。页面未发送请求，请重新读取。", "error");
    return;
  }
  state = { ...state, confirming: false };
  await submitDecision(identity, request);
}

async function submitDecision(identity, request) {
  state = { ...state, busy: true };
  syncControls();
  setStatus(elements.decisionStatus, "正在保存不可变人工决定…", "warning");
  elements.decisionStatus.focus({ preventScroll: true });
  try {
    const receipt = await api.submit(identity.packageId, request);
    if (!submissionIsCurrent(identity)) {
      state = { ...state, busy: false, uncertain: true };
      setStatus(elements.decisionStatus,
        "项目身份在提交期间发生变化。请重新读取历史，页面不会重复发送。", "error");
      return;
    }
    state = { ...state, busy: false, committed: true };
    elements.explicitConfirmation.checked = false;
    showIdleReviewReceipt(elements, receipt);
    const next = receipt.probe_status === "pending_probe"
      ? "可打开 P10.2 自动结构探针。" : "本决定不进入结构探针。";
    setStatus(elements.decisionStatus,
      `P10.1 revision ${receipt.revision} 已保存。${next}`, "success");
  } catch (error) {
    if (!submissionIsCurrent(identity)) {
      state = { ...state, busy: false, uncertain: true };
      setStatus(elements.decisionStatus,
        "项目身份在提交期间发生变化。请重新读取历史，页面不会重复发送。", "error");
      return;
    }
    if (error instanceof IdleBehaviorReviewApiError) {
      state = { ...state, busy: false };
      setStatus(elements.decisionStatus,
        `服务端未接受本次决定：${error.message}。草稿已保留。`, "error");
    } else {
      state = { ...state, busy: false, uncertain: true };
      setStatus(elements.decisionStatus,
        "提交结果不确定。请点击“重新读取”核对历史，页面不会重复发送。", "error");
    }
  } finally {
    loader.setMutationLocked(false);
    syncControls();
  }
}

function submissionIsCurrent(identity) {
  return state.entry?.package?.package_id === identity.packageId
    && state.entry?.candidate_sha256 === identity.candidateSha256
    && loader.currentPackageId() === identity.packageId;
}

function errorText(error) {
  return error instanceof Error ? error.message : "P10 页面发生未知错误";
}
