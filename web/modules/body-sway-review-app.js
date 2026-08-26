"use strict";

import { normalizeReviewAddress } from "./body-sway-review-address.js";
import { BodySwayReviewApiError, createBodySwayReviewApi } from "./body-sway-review-api.js";
import { createCaseInteractions } from "./body-sway-review-cases.js";
import {
  currentHeadBaseline, normalizeDecisionEnvelope, normalizeHistoryEnvelope,
  renderDecisionDocument,
} from "./body-sway-review-history.js";
import {
  buildReviewSubmission, clearReviewForAddress, createBusyGroup,
  createRequestSequence, createReviewState, markSubmissionConflict,
  normalizeCandidateEnvelope,
} from "./body-sway-review-state.js";
import {
  addressValues, announce, resetReviewView, reviewElements, setStatus,
  setDraftControlsDisabled, showBaseline, showCandidate, showHistory,
  updateReviewSummary,
} from "./body-sway-review-view.js";

const elements = reviewElements();
const api = createBodySwayReviewApi();
const requests = createRequestSequence();
let state = createReviewState();
let address = null;
let activity = { candidate: false, history: false, mutation: false };

function syncOperationControls() {
  const locked = activity.mutation;
  for (const control of elements.addressForm.querySelectorAll("input, button")) {
    control.disabled = locked;
  }
  elements.loadCandidateBtn.disabled = activity.candidate || locked;
  elements.refreshHistoryBtn.disabled = activity.history || locked;
  elements.useHeadBtn.disabled = activity.history || locked || !state.history;
  elements.historyList.inert = activity.history || locked;
  setDraftControlsDisabled(elements, locked);
  if (activity.candidate || activity.history || locked) {
    elements.submitReviewBtn.disabled = true;
  } else {
    updateReviewSummary(elements, state);
  }
}

const busyGroup = createBusyGroup(
  ["candidate", "history", "mutation"],
  (next) => { activity = next; syncOperationControls(); },
);
const candidateBusy = busyGroup.gate("candidate");
const historyBusy = busyGroup.gate("history");
const mutationBusy = busyGroup.gate("mutation");

function errorText(error) {
  return error instanceof Error ? error.message : "未知错误";
}

function invalidateAddress() {
  requests.invalidate();
  state = clearReviewForAddress(state);
  address = null;
  resetReviewView(elements);
  setStatus(elements.addressStatus, "地址已改变；候选、历史、基线和草稿均已清空。", "warning");
}

async function loadHistory(token) {
  const payload = await api.loadHistory(address, state.candidateSha256);
  if (!requests.isCurrent(token)) return false;
  state = {
    ...state,
    history: normalizeHistoryEnvelope(payload, state.candidateSha256),
    selectedDecision: null,
    baseline: null,
    stale: false,
  };
  showHistory(elements, state.history);
  elements.decisionDocument.textContent = "—";
  setStatus(elements.historySelectionStatus, "尚未选择历史 revision。");
  updateReviewSummary(elements, state);
  return true;
}

async function loadCandidate(event) {
  event.preventDefault();
  if (!elements.addressForm.reportValidity()) return;
  let nextAddress;
  try {
    nextAddress = normalizeReviewAddress(addressValues(elements));
  } catch (error) {
    setStatus(elements.addressStatus, errorText(error), "error");
    return;
  }
  const focusCaseId = state.currentCaseId;
  state = clearReviewForAddress(state, nextAddress);
  address = nextAddress;
  const token = requests.next();
  resetReviewView(elements);
  const busyToken = candidateBusy.begin();
  setStatus(elements.addressStatus, "正在读取精确候选…");
  try {
    const envelope = normalizeCandidateEnvelope(await api.loadCandidate(address), address);
    if (!requests.isCurrent(token)) return;
    state = { ...state, candidate: envelope.candidate,
      candidateSha256: envelope.candidateSha256 };
    showCandidate(elements, state, api, address, focusCaseId);
    setStatus(elements.addressStatus, `已加载 ${state.candidate.cases.length} 个 case。`, "success");
    try {
      await loadHistory(token);
    } catch (historyError) {
      if (requests.isCurrent(token)) setStatus(
        elements.baselineStatus, `候选已加载，但历史读取失败：${errorText(historyError)}`, "error",
      );
    }
  } catch (error) {
    if (!requests.isCurrent(token)) return;
    resetReviewView(elements);
    setStatus(elements.addressStatus, `加载失败：${errorText(error)}`, "error");
  } finally {
    candidateBusy.finish(busyToken);
  }
}

async function refreshHistory() {
  if (!state.candidate) return;
  const token = requests.next();
  const busyToken = historyBusy.begin();
  setStatus(elements.baselineStatus, "正在重新读取历史…");
  try {
    await loadHistory(token);
  } catch (error) {
    if (requests.isCurrent(token)) setStatus(
      elements.baselineStatus, `历史读取失败：${errorText(error)}`, "error",
    );
  } finally {
    historyBusy.finish(busyToken);
  }
}

async function selectHistory(target) {
  const revision = Number(target.dataset.historyRevision);
  const digest = target.dataset.historySha;
  const row = state.history?.items.find(
    (item) => item.revision === revision && item.decisionSha256 === digest,
  );
  if (!row) return;
  const token = requests.next();
  setStatus(elements.historySelectionStatus, `正在读取 revision ${revision}…`);
  try {
    const payload = await api.loadDecision(address, state.candidateSha256, revision, digest);
    if (!requests.isCurrent(token)) return;
    state = { ...state, selectedDecision: normalizeDecisionEnvelope(
      payload, state.candidateSha256, revision, digest,
    ) };
    for (const button of elements.historyList.querySelectorAll("button")) {
      if (button === target) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    }
    renderDecisionDocument(elements.decisionDocument, state.selectedDecision);
    setStatus(elements.historySelectionStatus, `已读取 revision ${revision} / ${digest}`, "success");
  } catch (error) {
    if (requests.isCurrent(token)) setStatus(
      elements.historySelectionStatus, `历史读取失败：${errorText(error)}`, "error",
    );
  }
}

function applyHeadBaseline() {
  try {
    if (state.stale || !state.history) {
      throw new Error("请先重新读取历史，再选择新的 head 基线");
    }
    state = { ...state, baseline: currentHeadBaseline(state.history), stale: false };
    showBaseline(elements, state.baseline);
    updateReviewSummary(elements, state);
  } catch (error) {
    setStatus(elements.baselineStatus, errorText(error), "error");
  }
}

function validateSubmitEnvelope(payload, baseline) {
  if (payload?.candidate_sha256 !== state.candidateSha256
      || payload?.revision !== baseline.revision + 1
      || !/^[0-9a-f]{64}$/.test(payload?.decision_sha256)
      || !["sampled_visual_approved", "sampled_visual_rejected"].includes(payload?.status)) {
    throw new Error("提交响应与请求的 revision 链不一致");
  }
  return payload;
}

async function submitReview() {
  let payload;
  try {
    state = { ...state, reviewerId: elements.reviewerId.value,
      reviewNotes: elements.reviewNotes.value };
    payload = buildReviewSubmission(state);
  } catch (error) {
    setStatus(elements.submitStatus, errorText(error), "error");
    return;
  }
  const baseline = state.baseline;
  const token = requests.next();
  const busyToken = mutationBusy.begin();
  elements.submitReviewBtn.disabled = true;
  setStatus(elements.submitStatus, "正在提交不可变 revision…");
  try {
    const response = await api.submit(address, state.candidateSha256, payload);
    if (!requests.isCurrent(token)) return;
    validateSubmitEnvelope(response, baseline);
    state = { ...state, history: null, selectedDecision: null, baseline: null, stale: false };
    elements.historyList.replaceChildren();
    elements.decisionDocument.textContent = "—";
    elements.useHeadBtn.disabled = true;
    setStatus(elements.historySelectionStatus, "历史选择已清除。", "neutral");
    setStatus(elements.baselineStatus, "已提交；必须重新读取并显式选择下一基线。");
    setStatus(elements.submitStatus, `提交成功：revision ${response.revision}`, "success");
    announce(elements, `视觉复核 revision ${response.revision} 已提交`);
    try {
      await loadHistory(token);
    } catch (historyError) {
      if (requests.isCurrent(token)) setStatus(
        elements.submitStatus,
        `revision ${response.revision} 已提交，但历史刷新失败：${errorText(historyError)}`,
        "warning",
      );
    }
  } catch (error) {
    if (!requests.isCurrent(token)) return;
    if (error instanceof BodySwayReviewApiError && error.status === 409) {
      state = markSubmissionConflict(state);
      elements.historyList.replaceChildren();
      elements.decisionDocument.textContent = "—";
      elements.useHeadBtn.disabled = true;
      setStatus(elements.baselineStatus, "旧基线已失效；请重新读取历史。", "warning");
      setStatus(elements.historySelectionStatus, "历史选择已清除。", "warning");
      setStatus(elements.submitStatus, "基线已过期（409）。草稿已保留；请重新读取历史并显式选择新 head。", "warning");
    } else {
      setStatus(elements.submitStatus, `提交失败：${errorText(error)}`, "error");
    }
  } finally {
    mutationBusy.finish(busyToken);
    if (requests.isCurrent(token)) updateReviewSummary(elements, state);
  }
}

const caseInteractions = createCaseInteractions({
  container: elements.reviewCases,
  submitButton: elements.submitReviewBtn,
  getState: () => state,
  setState: (next) => { state = next; },
  onChange: () => updateReviewSummary(elements, state),
  onAnnounce: (message) => announce(elements, message),
  onError: (error) => setStatus(elements.submitStatus, errorText(error), "error"),
  onSubmit: submitReview,
  isLocked: () => activity.mutation,
});

elements.addressForm.addEventListener("submit", loadCandidate);
for (const input of [elements.projectId, elements.previewSha256,
  elements.bundleSha256, elements.artifactSha256]) input.addEventListener("input", invalidateAddress);
elements.reviewCases.addEventListener("change", (event) => {
  if (event.target.dataset.caseAction) caseInteractions.updateDraft(event.target);
});
elements.reviewCases.addEventListener("input", (event) => {
  if (event.target.dataset.caseNotes) caseInteractions.updateDraft(event.target);
});
elements.reviewCases.addEventListener("focusin", (event) => caseInteractions.rememberFocus(event.target));
elements.refreshHistoryBtn.addEventListener("click", refreshHistory);
elements.historyList.addEventListener("click", (event) => {
  const target = event.target.closest?.("button[data-history-revision]");
  if (target) selectHistory(target);
});
elements.useHeadBtn.addEventListener("click", applyHeadBaseline);
elements.reviewerId.addEventListener("input", () => {
  state = { ...state, reviewerId: elements.reviewerId.value };
  updateReviewSummary(elements, state);
});
elements.reviewNotes.addEventListener("input", () => {
  state = { ...state, reviewNotes: elements.reviewNotes.value };
  updateReviewSummary(elements, state);
});
elements.submitReviewBtn.addEventListener("click", submitReview);
document.addEventListener("keydown", caseInteractions.handleKeyboard);
