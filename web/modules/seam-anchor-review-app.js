"use strict";

import {
  normalizeSeamReviewAddress,
} from "./seam-anchor-review-address.js";
import {
  SeamAnchorReviewApiError, createSeamAnchorReviewApi,
} from "./seam-anchor-review-api.js";
import { normalizeSeamCandidateEnvelope } from "./seam-anchor-review-candidate.js";
import {
  createSeamReviewHistoryController,
} from "./seam-anchor-review-history-controller.js";
import { createSeamReviewInteractions } from "./seam-anchor-review-interactions.js";
import {
  buildSeamReviewSubmission, clearSeamReviewForAddress, createBusyGroup,
  createRequestSequence, createSeamReviewState, expectedSeamSubmissionResult,
  hasLoadedSeamReviewAddress, markSeamSubmissionConflict,
} from "./seam-anchor-review-state.js";
import {
  announce, resetSeamReviewView, seamAddressValues, seamReviewElements,
  setSeamDraftDisabled, setStatus, showSeamCandidate,
  updateAnchorValidity, updateSeamReviewSummary,
} from "./seam-anchor-review-view.js";

const elements = seamReviewElements();
const api = createSeamAnchorReviewApi();
const requests = createRequestSequence();
let state = createSeamReviewState();
let address = null;
let activity = { candidate: false, history: false, mutation: false };

function syncOperationControls() {
  const locked = activity.mutation;
  for (const control of elements.addressForm.querySelectorAll("input, button")) {
    control.disabled = locked;
  }
  elements.loadCandidateBtn.disabled = activity.candidate || locked;
  elements.refreshHistoryBtn.disabled = activity.history || locked || !state.candidate;
  elements.useHeadBtn.disabled = activity.history || locked || !state.history;
  elements.historyList.inert = activity.history || locked;
  elements.historyList.setAttribute("aria-busy", String(activity.history));
  setSeamDraftDisabled(elements, locked);
  if (activity.candidate || activity.history || locked) {
    elements.submitReviewBtn.disabled = true;
  } else updateSeamReviewSummary(elements, state);
}

const busy = createBusyGroup(
  ["candidate", "history", "mutation"],
  (next) => { activity = next; syncOperationControls(); },
);

function errorText(error) {
  return error instanceof Error ? error.message : "未知错误";
}
function invalidateAddress() {
  requests.invalidate();
  state = clearSeamReviewForAddress(state);
  address = null;
  resetSeamReviewView(elements);
  setStatus(
    elements.addressStatus,
    "地址已改变；候选、图片证据、历史、基线和草稿均已清空。", "warning",
  );
}
async function loadCandidate(event) {
  event.preventDefault();
  if (!elements.addressForm.reportValidity()) return;
  let requestedAddress;
  try { requestedAddress = normalizeSeamReviewAddress(seamAddressValues(elements)); }
  catch (error) {
    setStatus(elements.addressStatus, errorText(error), "error");
    return;
  }
  if (hasLoadedSeamReviewAddress(state, requestedAddress)) {
    setStatus(
      elements.addressStatus,
      "该精确候选已加载；草稿保持不变。需要更新提交基线时请重新读取历史。",
      "warning",
    );
    return;
  }
  address = requestedAddress;
  const focusId = state.currentRelationshipId;
  state = clearSeamReviewForAddress(state, address);
  const token = requests.next();
  resetSeamReviewView(elements);
  const busyToken = busy.begin("candidate");
  setStatus(elements.addressStatus, "正在读取精确候选与 attachment 证据…");
  try {
    const payload = await api.loadCandidate(address);
    if (!requests.isCurrent(token)) return;
    const envelope = normalizeSeamCandidateEnvelope(
      payload, address,
      (optionId, attachmentId, imageSha) => api.imageUrl(
        address, payload.candidate_sha256, optionId, attachmentId, imageSha,
      ),
    );
    state = {
      ...state, candidate: envelope.candidate,
      candidateSha256: envelope.candidateSha256,
      attachmentImages: envelope.attachmentImages,
    };
    showSeamCandidate(elements, state, focusId);
    setStatus(
      elements.addressStatus,
      `已加载固定 ${state.candidate.relationships.length} 个 relationship。`, "success",
    );
    try {
      const history = await api.loadHistory(address, state.candidateSha256);
      if (requests.isCurrent(token)) historyController.applyHistory(history);
    } catch (historyError) {
      if (requests.isCurrent(token)) setStatus(
        elements.baselineStatus,
        `候选已加载，但历史读取失败：${errorText(historyError)}`, "error",
      );
    }
  } catch (error) {
    if (!requests.isCurrent(token)) return;
    resetSeamReviewView(elements);
    setStatus(elements.addressStatus, `加载失败：${errorText(error)}`, "error");
  } finally {
    busy.finish("candidate", busyToken);
  }
}
function validateSubmitEnvelope(payload, baseline, expected) {
  if (payload?.candidate_sha256 !== state.candidateSha256
      || payload?.revision !== baseline.revision + 1
      || !/^[0-9a-f]{64}$/.test(payload?.decision_sha256)
      || typeof payload?.reused !== "boolean"
      || payload?.status !== expected.status
      || JSON.stringify(payload?.release_gate) !== JSON.stringify(expected.releaseGate)
      || JSON.stringify(payload?.summary) !== JSON.stringify(expected.summary)) {
    throw new Error("提交响应与请求的 revision 链不一致");
  }
  return payload;
}

async function submitReview() {
  let payload;
  try {
    state = {
      ...state, reviewerId: elements.reviewerId.value,
      reviewNotes: elements.reviewNotes.value,
    };
    payload = buildSeamReviewSubmission(state);
  } catch (error) {
    setStatus(elements.submitStatus, errorText(error), "error");
    return;
  }
  const baseline = state.baseline;
  const expected = expectedSeamSubmissionResult(state);
  const token = requests.next();
  const busyToken = busy.begin("mutation");
  setStatus(elements.submitStatus, "正在提交不可变 seam review revision…");
  try {
    const response = validateSubmitEnvelope(
      await api.submit(address, state.candidateSha256, payload), baseline,
      expected,
    );
    if (!requests.isCurrent(token)) return;
    state = {
      ...state, history: null, selectedDecision: null, baseline: null, stale: false,
    };
    elements.historyList.replaceChildren();
    elements.decisionDocument.textContent = "—";
    elements.useHeadBtn.disabled = true;
    setStatus(elements.historySelectionStatus, "历史选择已清除。");
    setStatus(elements.baselineStatus, "已提交；必须重新读取并显式选择下一基线。");
    setStatus(elements.submitStatus, `提交成功：revision ${response.revision}`, "success");
    announce(elements, `Seam anchor review revision ${response.revision} 已提交`);
    try {
      const history = await api.loadHistory(address, state.candidateSha256);
      if (requests.isCurrent(token)) historyController.applyHistory(history);
    } catch (historyError) {
      if (requests.isCurrent(token)) setStatus(
        elements.submitStatus,
        `revision ${response.revision} 已提交，但历史刷新失败：${errorText(historyError)}`,
        "warning",
      );
    }
  } catch (error) {
    if (!requests.isCurrent(token)) return;
    if (error instanceof SeamAnchorReviewApiError && error.status === 409) {
      state = markSeamSubmissionConflict(state);
      elements.historyList.replaceChildren();
      elements.decisionDocument.textContent = "—";
      elements.useHeadBtn.disabled = true;
      setStatus(elements.baselineStatus, "旧基线已失效；请重新读取历史。", "warning");
      setStatus(elements.historySelectionStatus, "历史选择已清除。", "warning");
      setStatus(
        elements.submitStatus,
        "基线已过期（409）。草稿与 anchors 已保留；请读取新 head 后再提交。",
        "warning",
      );
    } else setStatus(elements.submitStatus, `提交失败：${errorText(error)}`, "error");
  } finally {
    busy.finish("mutation", busyToken);
    if (requests.isCurrent(token)) updateSeamReviewSummary(elements, state);
  }
}

const interactions = createSeamReviewInteractions({
  container: elements.reviewRelationships,
  submitButton: elements.submitReviewBtn,
  getState: () => state,
  setState: (next) => { state = next; },
  onChange: () => updateSeamReviewSummary(elements, state),
  onRender: (relationshipId, selector) => showSeamCandidate(
    elements, state, relationshipId, selector,
  ),
  onAnchorValidity: (relationshipId, error) => updateAnchorValidity(
    elements, relationshipId, error,
  ),
  onAnnounce: (message) => announce(elements, message),
  onError: (error) => setStatus(elements.submitStatus, errorText(error), "error"),
  onSubmit: submitReview,
  isLocked: () => activity.mutation,
});

const historyController = createSeamReviewHistoryController({
  api, elements, requests, busy, errorText,
  getAddress: () => address,
  getState: () => state,
  setState: (next) => { state = next; },
});

elements.addressForm.addEventListener("submit", loadCandidate);
for (const input of [
  elements.projectId, elements.layerManifestSha256,
  elements.p3RigSha256, elements.p3BundleSha256,
]) input.addEventListener("input", invalidateAddress);
elements.reviewRelationships.addEventListener("change", (event) => {
  if (event.target.dataset.seamOption || event.target.dataset.seamAction) {
    interactions.updateDraft(event.target);
  }
});
elements.reviewRelationships.addEventListener("input", (event) => {
  if (event.target.dataset.seamNotes || event.target.dataset.anchorJson) {
    interactions.updateDraft(event.target);
  }
});
elements.reviewRelationships.addEventListener(
  "focusin", (event) => interactions.rememberFocus(event.target),
);
elements.refreshHistoryBtn.addEventListener("click", historyController.refresh);
elements.historyList.addEventListener("click", (event) => {
  const target = event.target.closest?.("button[data-history-revision]");
  if (target) historyController.select(target);
});
elements.useHeadBtn.addEventListener("click", historyController.applyHeadBaseline);
elements.reviewerId.addEventListener("input", () => {
  state = { ...state, reviewerId: elements.reviewerId.value };
  updateSeamReviewSummary(elements, state);
});
elements.reviewNotes.addEventListener("input", () => {
  state = { ...state, reviewNotes: elements.reviewNotes.value };
  updateSeamReviewSummary(elements, state);
});
elements.submitReviewBtn.addEventListener("click", submitReview);
document.addEventListener("keydown", interactions.handleKeyboard);
