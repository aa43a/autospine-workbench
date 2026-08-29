"use strict";

import {
  normalizeSeamReviewAddress,
} from "./seam-anchor-review-address.js";
import {
  createSeamAnchorReviewApi,
} from "./seam-anchor-review-api.js";
import { createSeamAssistController } from "./seam-anchor-review-assist-controller.js";
import { normalizeSeamCandidateEnvelope } from "./seam-anchor-review-candidate.js";
import { createSeamReviewEntryFlow } from "./seam-anchor-review-entry-flow.js";
import {
  createSeamReviewHistoryController,
} from "./seam-anchor-review-history-controller.js";
import { createSeamReviewInteractions } from "./seam-anchor-review-interactions.js";
import { createSeamReviewSubmitFlow } from "./seam-anchor-review-submit-flow.js";
import {
  clearSeamReviewForAddress, createBusyGroup, createRequestSequence,
  createSeamReviewState, hasLoadedSeamReviewAddress,
} from "./seam-anchor-review-state.js";
import {
  announce, resetSeamReviewView, seamAddressValues, seamReviewElements,
  setSeamDraftDisabled, setStatus, showSeamAssist, showSeamCandidate,
  updateAnchorValidity, updateSeamReviewSummary,
} from "./seam-anchor-review-view.js";

const elements = seamReviewElements();
const api = createSeamAnchorReviewApi();
const requests = createRequestSequence();
let state = createSeamReviewState();
let address = null;
let activity = { candidate: false, history: false, mutation: false };
let entryFlow = null;
let assistUndoAvailable = false;
let submitFlow = null;

function syncOperationControls() {
  const locked = activity.mutation;
  const committed = Boolean(submitFlow?.snapshot().decisionCommitted);
  for (const control of elements.addressForm.querySelectorAll("input, button")) {
    control.disabled = locked;
  }
  elements.loadCandidateBtn.disabled = activity.candidate || locked;
  elements.applyAssistBtn.disabled = activity.candidate || locked || committed
    || !state.reviewAssist;
  elements.undoAssistBtn.disabled = locked || committed || !assistUndoAvailable;
  elements.retryPublicationBtn.disabled = locked;
  elements.downloadPublicationBtn.disabled = locked || !submitFlow?.hasReceipt();
  elements.refreshHistoryBtn.disabled = activity.history || locked || !state.candidate;
  elements.useHeadBtn.disabled = activity.history || locked || !state.history;
  elements.historyList.inert = activity.history || locked;
  elements.historyList.setAttribute("aria-busy", String(activity.history));
  setSeamDraftDisabled(elements, locked || committed);
  if (activity.candidate || activity.history || locked || committed) {
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
  submitFlow?.reset();
  resetSeamReviewView(elements);
  assistController?.reset();
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
    const packageEntry = entryFlow?.verifyCandidate(envelope);
    state = {
      ...state, candidate: envelope.candidate,
      candidateSha256: envelope.candidateSha256,
      attachmentImages: envelope.attachmentImages,
      setupCanvas: envelope.setupCanvas, reviewAssist: envelope.reviewAssist,
      reviewerId: packageEntry ? "workbench-operator" : state.reviewerId,
    };
    elements.reviewerId.value = state.reviewerId;
    assistController.reset();
    assistController.apply({ automatic: true });
    showSeamAssist(elements, state.reviewAssist, true);
    setStatus(
      elements.addressStatus,
      `已加载固定 ${state.candidate.relationships.length} 个 relationship。`, "success",
    );
    try {
      const history = await api.loadHistory(address, state.candidateSha256);
      if (requests.isCurrent(token)) historyController.applyHistory(history, {
        autoBaseline: Boolean(entryFlow?.currentEntry()),
      });
    } catch (historyError) {
      if (requests.isCurrent(token)) setStatus(
        elements.baselineStatus,
        `候选已加载，但历史读取失败：${errorText(historyError)}`, "error",
      );
    }
  } catch (error) {
    if (!requests.isCurrent(token)) return;
    state = clearSeamReviewForAddress(state, address);
    assistController.reset();
    resetSeamReviewView(elements);
    entryFlow?.candidateFailed(error);
    setStatus(elements.addressStatus, `加载失败：${errorText(error)}`, "error");
  } finally {
    busy.finish("candidate", busyToken);
  }
}
const assistController = createSeamAssistController({
  getState: () => state,
  setState: (next) => { state = next; },
  onRender: () => showSeamCandidate(elements, state, state.currentRelationshipId),
  onStatus: (message, tone) => setStatus(elements.assistStatus, message, tone),
  onUndoAvailability: (available) => {
    assistUndoAvailable = available;
    elements.undoAssistBtn.disabled = activity.mutation || !available;
  },
});

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
  onSubmit: () => submitFlow.submit(),
  isLocked: () => activity.mutation,
});

const historyController = createSeamReviewHistoryController({
  api, elements, requests, busy, errorText,
  getAddress: () => address,
  getState: () => state,
  setState: (next) => { state = next; },
});
submitFlow = createSeamReviewSubmitFlow({
  api, elements, requests, busy, errorText,
  announce: (message) => announce(elements, message),
  getState: () => state,
  setState: (next) => { state = next; },
  getAddress: () => address,
  getPackageId: () => entryFlow?.currentEntry()?.packageId || null,
  getHistoryController: () => historyController,
});

entryFlow = createSeamReviewEntryFlow({
  api, elements, busy,
  onReset: () => {
    requests.invalidate();
    state = clearSeamReviewForAddress(state);
    address = null;
    assistController.reset();
    submitFlow.reset();
    resetSeamReviewView(elements);
    setStatus(elements.addressStatus, "等待自动入口或专业模式地址。");
  },
  onSubmitAddress: () => elements.addressForm.requestSubmit(),
});

elements.addressForm.addEventListener("submit", loadCandidate);
for (const input of [
  elements.projectId, elements.layerManifestSha256,
  elements.p3RigSha256, elements.p3BundleSha256,
]) input.addEventListener("input", () => {
  entryFlow.enterManual();
  invalidateAddress();
});
elements.reviewRelationships.addEventListener("change", (event) => {
  if (event.target.dataset.seamOption || event.target.dataset.seamAction) {
    assistController.authoredChange();
    interactions.updateDraft(event.target);
  }
});
elements.reviewRelationships.addEventListener("input", (event) => {
  if (event.target.dataset.seamNotes || event.target.dataset.anchorJson) {
    assistController.authoredChange();
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
elements.applyAssistBtn.addEventListener("click", () => assistController.apply());
elements.undoAssistBtn.addEventListener("click", () => assistController.undo());
elements.retryPublicationBtn.addEventListener("click", submitFlow.retryPublication);
elements.downloadPublicationBtn.addEventListener("click", submitFlow.download);
elements.reviewerId.addEventListener("input", () => {
  state = { ...state, reviewerId: elements.reviewerId.value };
  updateSeamReviewSummary(elements, state);
});
elements.reviewNotes.addEventListener("input", () => {
  state = { ...state, reviewNotes: elements.reviewNotes.value };
  updateSeamReviewSummary(elements, state);
});
elements.submitReviewBtn.addEventListener("click", submitFlow.submit);
document.addEventListener("keydown", interactions.handleKeyboard);
window.addEventListener("popstate", () => {
  void entryFlow.loadSearch(window.location.search);
});
void entryFlow.loadSearch(window.location.search);
