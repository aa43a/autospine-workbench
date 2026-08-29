import { buildMotionPolicyEvidenceModel } from "./motion-policy-evidence-model.js";
import { createMotionPolicyEvidenceView } from "./motion-policy-evidence-view.js";
import { createMotionPolicyBatchController } from "./motion-policy-batch-controller.js";
import { handleCandidateKeyboard } from "./motion-policy-keyboard.js";
import {
  buildReviewInput, createReviewState, reviewProgress, setDecision, setRelease, validateDecision,
} from "./motion-policy-review-state.js";
import {
  renderCandidateList, renderReleaseList, setReleaseFields, updateCandidateCard,
} from "./motion-policy-review-view.js";
import { downloadJson, errorMessage, integerOrNull, setStatus } from "./motion-policy-review-utils.js";

const IDS = [
  "reviewWorkspace", "candidateSearch", "kindFilter", "progressFilter", "candidateList",
  "candidateDetails", "exceptionBadge", "coverageBadge", "reviewRevision", "loopResetFieldset",
  "releaseList", "reviewStatus", "finalConfirm", "downloadReviewBtn", "liveRegion",
  "evidenceReview", "evidenceSummary", "frameLabel", "metricChart", "frameScrubber",
  "attentionList", "metricTableBody", "characterComposite", "footOverlay", "overlayEmpty",
  "frameState", "frameFacts", "observationBody", "segmentBadge", "selectAllSegments",
  "segmentList", "batchForm", "batchAction", "batchReason", "batchPreview", "batchConfirm",
  "batchOverwriteRow", "batchOverwriteConfirm", "batchApply", "batchUndo", "batchStatus",
  "decisionSummary",
];

export function createMotionPolicyDecisionController(doc) {
  const elements = Object.fromEntries(IDS.map((id) => [id, doc.getElementById(id)]));
  let state = null;
  let evidenceModel = null;
  let candidatesById = new Map();
  const evidenceView = createMotionPolicyEvidenceView(elements, { onFrameCandidate: locateCandidate });
  const batch = createMotionPolicyBatchController(elements, {
    onChanged: syncAfterBatch,
    onLocate: locateSegment,
  });

  elements.candidateList.addEventListener("change", handleCandidateChange);
  elements.candidateList.addEventListener("input", handleCandidateChange);
  elements.candidateList.addEventListener("focusin", focusFrameFromCard);
  elements.candidateList.addEventListener("keydown", (event) => {
    handleCandidateKeyboard(event, elements.candidateList, chooseKeyboardAction);
  });
  [elements.candidateSearch, elements.kindFilter, elements.progressFilter]
    .forEach((control) => control.addEventListener("input", applyFilters));
  elements.reviewRevision.addEventListener("input", updateRevision);
  elements.loopResetFieldset.addEventListener("change", updateLoopReset);
  elements.releaseList.addEventListener("change", handleReleaseChange);
  elements.releaseList.addEventListener("input", handleReleaseChange);
  elements.finalConfirm.addEventListener("change", updateFinalConfirmation);
  elements.downloadReviewBtn.addEventListener("click", downloadReviewInput);

  return { load, clear };

  function load(inventory) {
    clear();
    evidenceModel = buildMotionPolicyEvidenceModel(inventory);
    state = createReviewState(inventory);
    candidatesById = new Map(inventory.candidates.map((row) => [row.candidateId, row]));
    renderCandidateList(elements.candidateList, inventory.candidates);
    renderReleaseList(elements.releaseList, inventory.unconstrainedTicks);
    elements.reviewRevision.value = "";
    elements.loopResetFieldset.querySelectorAll("input").forEach((input) => { input.checked = false; });
    elements.candidateSearch.value = "";
    elements.kindFilter.value = "all";
    elements.progressFilter.value = "pending";
    evidenceView.load(evidenceModel);
    batch.load(state, evidenceModel);
    elements.reviewWorkspace.hidden = false;
    applyFilters();
    refreshProgress();
  }

  function clear() {
    state = null;
    evidenceModel = null;
    candidatesById = new Map();
    evidenceView.clear();
    batch.clear();
    elements.candidateList.replaceChildren();
    elements.releaseList.replaceChildren();
    elements.coverageBadge.textContent = "0 / 0";
    elements.exceptionBadge.textContent = "0 项待处理";
    elements.finalConfirm.checked = false;
    elements.reviewWorkspace.hidden = true;
  }

  function handleCandidateChange(event) {
    if (!state) return;
    const id = event.target.dataset.candidateId;
    const candidate = candidatesById.get(id);
    const card = event.target.closest("[data-candidate-id]");
    if (!candidate || !card) return;
    const saved = state.decisions.get(id);
    const current = saved ? { ...saved, payload: saved.payload ? structuredClone(saved.payload) : null }
      : { action: null, reason_code: "", payload: null };
    if (event.target.dataset.action) current.action = event.target.dataset.action;
    if (event.target.dataset.reason) current.reason_code = event.target.value.trim();
    current.payload = current.action === "adjust" ? adjustmentFromCard(candidate, card) : null;
    const issue = setDecision(state, candidate, current);
    updateCandidateCard(card, current, issue);
    changed();
  }

  function chooseKeyboardAction(id, action, card) {
    if (!state) return;
    const candidate = candidatesById.get(id);
    const saved = state.decisions.get(id);
    const current = saved ? { ...saved } : { action: null, reason_code: "", payload: null };
    current.action = action;
    current.payload = action === "adjust" ? adjustmentFromCard(candidate, card) : null;
    setDecision(state, candidate, current);
    syncCard(card, candidate);
    changed();
  }

  function adjustmentFromCard(candidate, card) {
    return candidate.kind === "foot_lock"
      ? { x: card.querySelector("[data-adjust-x]").value, y: card.querySelector("[data-adjust-y]").value }
      : { frontSlot: card.querySelector("[data-adjust-front]").value };
  }

  function handleReleaseChange(event) {
    if (!state) return;
    const row = event.target.closest("[data-tick]");
    if (!row) return;
    const toggle = row.querySelector("[data-release-toggle]");
    setReleaseFields(row, toggle.checked);
    setRelease(state, Number(row.dataset.tick), toggle.checked ? {
      x: row.querySelector("[data-release-x]").value,
      y: row.querySelector("[data-release-y]").value,
      interpolation: row.querySelector("[data-release-interpolation]").value,
      reasonCode: row.querySelector("[data-release-reason]").value.trim(),
    } : null);
    changed();
  }

  function updateRevision() {
    if (!state) return;
    state.revision = integerOrNull(elements.reviewRevision.value);
    changed();
  }

  function updateLoopReset(event) {
    if (!state || event.target.name !== "loopReset") return;
    state.loopResetApproved = event.target.value === "true";
    changed();
  }

  function updateFinalConfirmation() {
    if (!state) return;
    state.humanConfirmed = elements.finalConfirm.checked;
    elements.downloadReviewBtn.disabled = !state.humanConfirmed || !reviewProgress(state).ready;
  }

  function changed() {
    invalidateConfirmation();
    batch.refresh();
    applyFilters();
    refreshProgress();
  }

  function syncAfterBatch() {
    if (!state) return;
    elements.candidateList.querySelectorAll(".candidate-card[data-candidate-id]").forEach((card) => {
      syncCard(card, candidatesById.get(card.dataset.candidateId));
    });
    changed();
  }

  function syncCard(card, candidate) {
    const decision = state.decisions.get(candidate.candidateId);
    card.querySelectorAll("[data-action]").forEach((input) => {
      input.checked = input.dataset.action === decision?.action;
    });
    card.querySelector("[data-reason]").value = decision?.reason_code || "";
    if (decision?.action === "adjust" && decision.payload) {
      if (candidate.kind === "foot_lock") {
        card.querySelector("[data-adjust-x]").value = decision.payload.x;
        card.querySelector("[data-adjust-y]").value = decision.payload.y;
      } else card.querySelector("[data-adjust-front]").value = decision.payload.frontSlot;
    }
    updateCandidateCard(card, decision, validateDecision(candidate, decision));
  }

  function applyFilters() {
    if (!state) return;
    const query = elements.candidateSearch.value.trim().toLowerCase();
    const kind = elements.kindFilter.value;
    const progress = elements.progressFilter.value;
    let visible = 0;
    for (const card of elements.candidateList.querySelectorAll(".candidate-card[data-candidate-id]")) {
      const candidate = candidatesById.get(card.dataset.candidateId);
      const complete = !validateDecision(candidate, state.decisions.get(candidate.candidateId));
      const blocked = candidate.kind === "foot_lock" && candidate.footState.startsWith("rejected_");
      const text = [candidate.candidateId, candidate.kind, candidate.tick, candidate.sourceFrameIndex,
        candidate.footState, candidate.pairId, ...(candidate.slots || [])].join(" ").toLowerCase();
      const show = (!query || text.includes(query)) && (kind === "all" || candidate.kind === kind) &&
        (progress === "all" || (progress === "pending" && !complete) ||
          (progress === "reviewed" && complete) || (progress === "blocked" && blocked));
      card.hidden = !show;
      if (show) visible += 1;
    }
    elements.liveRegion.textContent = `当前显示 ${visible} 项候选`;
  }

  function refreshProgress() {
    if (!state) return;
    const progress = reviewProgress(state);
    elements.coverageBadge.textContent = `${progress.complete} / ${progress.total} · ${progress.percent}%`;
    elements.exceptionBadge.textContent = `${progress.total - progress.complete} 项待处理`;
    elements.finalConfirm.disabled = !progress.ready;
    if (!progress.ready) invalidateConfirmation();
    elements.downloadReviewBtn.disabled = !progress.ready || !state.humanConfirmed;
    setStatus(elements.reviewStatus, progress.ready ? "覆盖率 100%，全局字段有效；等待最终人工确认。"
      : `${progress.complete}/${progress.total} 项有效；${progress.errors[0]?.message || "仍有未完成字段"}`,
    progress.ready ? "success" : "warning");
  }

  function invalidateConfirmation() {
    if (!state) return;
    state.humanConfirmed = false;
    elements.finalConfirm.checked = false;
    elements.downloadReviewBtn.disabled = true;
  }

  function focusFrameFromCard(event) {
    const card = event.target.closest("[data-candidate-id]");
    if (!card || !evidenceModel) return;
    const candidate = candidatesById.get(card.dataset.candidateId);
    const index = evidenceModel.samples.findIndex((row) => row.sourceFrameIndex === candidate.sourceFrameIndex);
    if (index >= 0) evidenceView.selectFrame(index);
  }

  function locateCandidate(candidateId) {
    if (!state || !candidatesById.has(candidateId)) return;
    elements.candidateDetails.open = true;
    elements.candidateSearch.value = candidateId;
    elements.kindFilter.value = "all";
    elements.progressFilter.value = "all";
    applyFilters();
    const card = [...elements.candidateList.querySelectorAll(".candidate-card[data-candidate-id]")]
      .find((item) => item.dataset.candidateId === candidateId);
    if (!card) return;
    card.scrollIntoView({ block: "center", behavior: "auto" });
    card.focus({ preventScroll: true });
    elements.liveRegion.textContent = `已打开 frame 对应的精确候选 ${candidateId}`;
  }

  function locateSegment(segment) {
    const index = evidenceModel.samples.findIndex((row) => row.sourceFrameIndex === segment.startFrame);
    if (index >= 0) evidenceView.selectFrame(index);
    elements.evidenceReview.scrollIntoView({ block: "start", behavior: "auto" });
  }

  function downloadReviewInput() {
    try {
      const review = buildReviewInput(state);
      downloadJson(`${state.inventory.projectId}.motion-policy-review-input.json`, review);
      setStatus(elements.reviewStatus, "严格四字段 review input 已下载；请交给 CLI 做最终合同校验。", "success");
    } catch (error) {
      setStatus(elements.reviewStatus, errorMessage(error), "error");
    }
  }
}
