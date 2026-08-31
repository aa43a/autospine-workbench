"use strict";

import {
  BodySwayReviewV2ApiError, createBodySwayReviewV2Api,
} from "./body-sway-review-v2-api.js";
import {
  normalizeCompletedReviewJob, normalizeReviewCandidateV2,
  normalizeReviewDecisionV2, normalizeReviewHistoryV2,
  normalizeReviewSubmissionV2, requireReviewJobId,
} from "./body-sway-review-v2-contract.js";
import { createCaseInteractions } from "./body-sway-review-cases.js";
import { currentHeadBaseline } from "./body-sway-review-history.js";
import {
  buildReviewSubmission, createReviewState, markSubmissionConflict,
  setCaseDecision,
} from "./body-sway-review-state.js";
import {
  announce, renderBaseline, renderCandidate, renderDecisionSummary,
  renderHistory, renderJobFacts, reviewV2Elements, setLocked, setStatus,
  updateSummary,
} from "./body-sway-review-v2-view.js";

const elements = reviewV2Elements();
let state = createReviewState();
let api = null;
let job = null;
let busy = false;
let generation = 0;
let pendingSubmission = null;

elements.refreshHistoryBtn.addEventListener("click", refreshHistory);
elements.useHeadBtn.addEventListener("click", selectCurrentHead);
elements.batchApproveBtn.addEventListener("click", () => {
  if (!busy && state.candidate) elements.batchDialog.showModal();
});
elements.confirmBatchBtn.addEventListener("click", applyBatchApprove);
elements.submitReviewBtn.addEventListener("click", openSubmitConfirmation);
elements.cancelSubmitBtn.addEventListener("click", clearPendingSubmission);
elements.confirmSubmitBtn.addEventListener("click", submitConfirmedReview);
elements.confirmDialog.addEventListener("cancel", clearPendingSubmission);
elements.confirmDialog.addEventListener("close", () => {
  if (elements.confirmDialog.returnValue !== "confirm") clearPendingSubmission();
});
for (const dialog of [elements.confirmDialog, elements.batchDialog]) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });
}
elements.reviewerId.addEventListener("input", syncHumanFields);
elements.reviewNotes.addEventListener("input", syncHumanFields);
elements.historyList.addEventListener("click", (event) => {
  const target = event.target.closest?.("button[data-history-revision]");
  if (target) selectHistory(target);
});

const caseInteractions = createCaseInteractions({
  container: elements.reviewCases,
  submitButton: elements.submitReviewBtn,
  getState: () => state,
  setState: (next) => { state = next; },
  onChange: syncControls,
  onAnnounce: (message) => announce(elements, message),
  onError: (error) => setStatus(elements.submitStatus, message(error), "error"),
  onSubmit: openSubmitConfirmation,
  isLocked: () => busy,
});

elements.reviewCases.addEventListener("change", (event) => {
  if (event.target.dataset.caseAction) caseInteractions.updateDraft(event.target);
});
elements.reviewCases.addEventListener("input", (event) => {
  if (event.target.dataset.caseNotes) caseInteractions.updateDraft(event.target);
});
elements.reviewCases.addEventListener("focusin", (event) => {
  caseInteractions.rememberFocus(event.target);
});
document.addEventListener("keydown", caseInteractions.handleKeyboard);

boot();

async function boot() {
  const token = ++generation;
  setBusy(true);
  try {
    const jobId = requireReviewJobId(
      new URLSearchParams(location.search).get("job_id"),
    );
    api = createBodySwayReviewV2Api(jobId);
    setStatus(elements.entryStatus, "正在校验已完成采集并重放当前项目…");
    job = normalizeCompletedReviewJob(await api.job(), jobId);
    const envelope = normalizeReviewCandidateV2(await api.candidate(), job);
    if (token !== generation) return;
    state = {
      ...createReviewState(), candidate: envelope.candidate,
      candidateSha256: envelope.candidateSha256,
    };
    renderJobFacts(elements, job, envelope.job);
    renderCandidate(elements, state, api);
    setStatus(elements.entryStatus,
      `已自动加载 ${envelope.job.case_count} 个官方 Runtime 采样帧。`, "success");
    await loadHistory(token);
  } catch (error) {
    if (token === generation) {
      elements.entryBadge.textContent = "无法进入";
      elements.entryBadge.dataset.tone = "error";
      setStatus(elements.entryStatus, entryMessage(error), "error");
    }
  } finally {
    if (token === generation) setBusy(false);
  }
}

async function loadHistory(token = generation) {
  const value = await api.history(state.candidateSha256);
  if (token !== generation) return;
  state = {
    ...state,
    history: normalizeReviewHistoryV2(
      value, job.job_id, state.candidateSha256,
    ),
    selectedDecision: null,
    baseline: null,
    stale: false,
  };
  renderHistory(elements, state.history);
  elements.decisionSummary.textContent = "—";
  setStatus(elements.historySelectionStatus, "尚未选择历史 revision。");
  setStatus(elements.baselineStatus, "尚未选择提交基线。");
  syncControls();
}

async function refreshHistory() {
  if (!api || busy || !state.candidate) return;
  const token = ++generation;
  setBusy(true);
  setStatus(elements.baselineStatus, "正在重新读取 current head…");
  try {
    await loadHistory(token);
  } catch (error) {
    if (token === generation) setStatus(
      elements.baselineStatus, `历史读取失败：${message(error)}`, "error",
    );
  } finally {
    if (token === generation) setBusy(false);
  }
}

async function selectHistory(target) {
  if (busy || !state.history) return;
  const revision = Number(target.dataset.historyRevision);
  const digest = target.dataset.historySha;
  const row = state.history.items.find(
    (item) => item.revision === revision && item.decisionSha256 === digest,
  );
  if (!row) return;
  const token = generation;
  setStatus(elements.historySelectionStatus, `正在读取 revision ${revision}…`);
  try {
    const value = await api.decision(
      state.candidateSha256, revision, digest,
    );
    if (token !== generation) return;
    const decision = normalizeReviewDecisionV2(
      value, job.job_id, state.candidateSha256, revision, digest,
    );
    state = { ...state, selectedDecision: decision };
    renderDecisionSummary(elements, decision);
    setStatus(elements.historySelectionStatus, `已读取 revision ${revision}。`, "success");
  } catch (error) {
    if (token === generation) setStatus(
      elements.historySelectionStatus, `历史读取失败：${message(error)}`, "error",
    );
  }
}

function selectCurrentHead() {
  if (busy || state.stale || !state.history) return;
  state = { ...state, baseline: currentHeadBaseline(state.history) };
  renderBaseline(elements, state.baseline);
  syncControls();
}

function applyBatchApprove() {
  if (busy || !state.candidate) return;
  for (const row of state.candidate.cases) {
    if (!state.decisions[row.case_id]?.action) {
      state = setCaseDecision(state, row.case_id, "approve", "");
      const radio = elements.reviewCases.querySelector(
        `input[data-case-id="${CSS.escape(row.case_id)}"][data-case-action="approve"]`,
      );
      if (radio) radio.checked = true;
    }
  }
  announce(elements, "所有未判定帧已标记为通过草稿，尚未提交");
  syncControls();
}

function syncHumanFields() {
  state = {
    ...state,
    reviewerId: elements.reviewerId.value,
    reviewNotes: elements.reviewNotes.value,
  };
  syncControls();
}

function openSubmitConfirmation() {
  if (busy) return;
  try {
    syncHumanFields();
    pendingSubmission = {
      payload: buildReviewSubmission(state), baseline: state.baseline,
    };
    const summary = updateSummary(elements, state);
    elements.confirmSummary.textContent = [
      `项目 ${job.addresses.project}，共 ${summary.caseCount} 帧；`,
      `通过 ${summary.counts.approve}，拒绝 ${summary.counts.reject}，`,
      `不可观测 ${summary.counts.unobservable}；`,
      `提交为 revision ${state.baseline.revision + 1}。`,
    ].join("");
    elements.confirmDialog.showModal();
  } catch (error) {
    pendingSubmission = null;
    setStatus(elements.submitStatus, message(error), "error");
  }
}

function clearPendingSubmission() {
  pendingSubmission = null;
}

async function submitConfirmedReview() {
  if (!pendingSubmission || busy) return;
  const current = pendingSubmission;
  pendingSubmission = null;
  const token = ++generation;
  setBusy(true);
  setStatus(elements.submitStatus, "正在追加不可变人工 revision…");
  try {
    const raw = await api.submit(state.candidateSha256, current.payload);
    if (token !== generation) return;
    const result = normalizeReviewSubmissionV2(
      raw, job.job_id, state.candidateSha256, current.baseline,
    );
    state = {
      ...state, history: null, selectedDecision: null,
      baseline: null, stale: false,
    };
    setStatus(elements.submitStatus, `提交成功：revision ${result.revision}。`, "success");
    announce(elements, `视觉复核 revision ${result.revision} 已提交`);
    await loadHistory(token);
  } catch (error) {
    if (token !== generation) return;
    if (error instanceof BodySwayReviewV2ApiError && error.status === 409) {
      state = markSubmissionConflict(state);
      elements.historyList.replaceChildren();
      elements.decisionSummary.textContent = "—";
      const revisionConflict = error.payload?.error
        === "body_sway_visual_review_v2_revision_conflict";
      setStatus(elements.baselineStatus,
        revisionConflict ? "旧基线已失效，请刷新历史。" : "当前动作来源已变化，旧基线已清除。",
        "warning");
      setStatus(elements.submitStatus, revisionConflict
        ? "提交未生效（409）。草稿已保留；请刷新并显式选择新的 current head。"
        : "提交未生效（409）。草稿已保留；请返回 Runtime 采集页重新采集当前动作。",
      "warning");
    } else {
      setStatus(elements.submitStatus, `提交失败：${message(error)}`, "error");
    }
  } finally {
    if (token === generation) setBusy(false);
  }
}

function setBusy(value) {
  busy = value;
  setLocked(elements, value);
  syncControls();
}

function syncControls() {
  const summary = updateSummary(elements, state);
  elements.batchApproveBtn.disabled = busy || !state.candidate || summary.counts.pending === 0;
  elements.refreshHistoryBtn.disabled = busy || !state.candidate;
  elements.useHeadBtn.disabled = busy || !state.history;
  if (busy) elements.submitReviewBtn.disabled = true;
}

function entryMessage(error) {
  if (error instanceof BodySwayReviewV2ApiError && error.status === 409) {
    return `${message(error)} 请返回 Runtime 采集页创建与当前项目匹配的新采集。`;
  }
  return `${message(error)} 请从已完成的 Runtime 采集结果进入。`;
}

function message(error) {
  return error instanceof Error && error.message ? error.message : "未知错误";
}
