"use strict";

import {
  IdleBehaviorReviewApiError, createIdleBehaviorReviewApi,
} from "./idle-behavior-review-api.js";
import { createIdleBehaviorReviewLoader } from "./idle-behavior-review-loader.js";
import {
  buildIdleReviewSubmission, controlsFromParameters,
  initialBodySwayParameters, parametersFromControls,
} from "./idle-behavior-review-model.js";
import { createIdleBehaviorPreview } from "./idle-behavior-review-preview.js";
import {
  applyControlValues, controlValues, idleReviewElements, renderIdleReviewEntry,
  resetIdleReviewView, setStatus, showIdleReviewReceipt, syncDecisionControls,
} from "./idle-behavior-review-view.js";

const elements = idleReviewElements();
const api = createIdleBehaviorReviewApi();
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
elements.confirmAdjust.addEventListener("click", () => submitDecision("adjust"));
elements.rejectBodySway.addEventListener("click", () => submitDecision("reject"));
elements.unobservableBodySway.addEventListener(
  "click", () => submitDecision("unobservable"),
);

loader.start();

function emptyState() {
  return {
    entry: null, baseParameters: null, baseControls: null,
    parametersTouched: false, available: false,
    busy: false, committed: false, uncertain: false,
  };
}

function reset() {
  state = emptyState();
  preview.reset();
  resetIdleReviewView(elements);
}

async function loadEntry(entry, context) {
  if (!context.isCurrent()) return;
  const baseParameters = initialBodySwayParameters(entry);
  const controls = controlsFromParameters(baseParameters);
  state = {
    entry, baseParameters, baseControls: controls, parametersTouched: false,
    available: renderIdleReviewEntry(elements, entry) && entry.history !== null,
    busy: false,
    committed: false,
    uncertain: false,
  };
  applyControlValues(elements, controls);
  elements.explicitConfirmation.checked = false;
  preview.load(entry.preview, baseParameters);
  syncControls();
  setStatus(elements.decisionStatus,
    state.available
      ? "请先预览并调整；勾选人工确认后才能保存。"
      : "缺少可决定的身体摆动候选或提交基线。",
    state.available ? "warning" : "error");
}

function changeParameters() {
  if (!state.entry || state.busy || state.committed) return;
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
    busy: state.busy || state.committed || state.uncertain,
  });
}

async function submitDecision(action) {
  if (!state.entry || !elements.explicitConfirmation.checked
      || state.busy || state.committed || state.uncertain) return;
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
  state = { ...state, busy: true };
  loader.setMutationLocked(true);
  syncControls();
  setStatus(elements.decisionStatus, "正在保存不可变人工决定…", "warning");
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
    setStatus(elements.decisionStatus,
      `P10.1 revision ${receipt.revision} 已保存。下一步请运行结构探针。`, "success");
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
