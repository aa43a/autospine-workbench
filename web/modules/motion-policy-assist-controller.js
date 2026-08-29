import {
  allSafeCandidateIds, ASSIST_PROFILE, ASSIST_REASON, assistedCoverage,
  safeCandidateIdsForSampleRange,
} from "./motion-policy-assist-model.js";
import {
  reviewProgress, setDecisionBatch, undoDecisionBatch,
} from "./motion-policy-review-state.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

export function createMotionPolicyAssistController(elements, { onChanged, onLocate, onAdopt }) {
  let state = null;
  let model = null;

  elements.autoApplyAllBtn.addEventListener("click", applyAll);
  elements.autoUndoBtn.addEventListener("click", undoLastAssisted);
  elements.approveOnScrub.addEventListener("change", refresh);
  elements.autoDownloadBtn.addEventListener("click", () => onAdopt());

  return { load, clear, applyRange, refresh };

  function load(nextState, nextModel, { assistOnScrub = true } = {}) {
    state = nextState;
    model = nextModel;
    elements.approveOnScrub.checked = assistOnScrub;
    setStatus(elements.autoDecisionStatus,
      "项目证据已准备好。拖动时间轴，或一键采用全部安全建议。", "success");
    refresh();
  }

  function clear() {
    state = null;
    model = null;
    elements.autoApplyAllBtn.disabled = true;
    elements.autoUndoBtn.disabled = true;
    elements.autoDownloadBtn.disabled = true;
    elements.autoCoverageBar.value = 0;
    elements.autoCoverageBar.max = 1;
    elements.automationSummary.textContent = "等待项目证据。";
  }

  function applyRange(startIndex, endIndex) {
    if (!state || !model) return;
    if (!elements.approveOnScrub.checked) {
      const sample = model.samples[endIndex];
      if (sample?.candidateId) onLocate(sample.candidateId);
      return;
    }
    applyIds(safeCandidateIdsForSampleRange(model, state, startIndex, endIndex), "timeline");
  }

  function applyAll() {
    if (!state || !model) return;
    applyIds(allSafeCandidateIds(model, state), "all-safe");
  }

  function applyIds(ids, trigger) {
    if (!ids.length) {
      setStatus(elements.autoDecisionStatus, "这次范围没有新的安全建议；既有决定没有被覆盖。", "warning");
      refresh();
      return;
    }
    try {
      const result = setDecisionBatch(state, ids, {
        action: "accept", reason_code: ASSIST_REASON, payload: null,
      }, {
        sourceKind: "assisted", profile: ASSIST_PROFILE, rule: ASSIST_REASON,
        trigger, snapshotKey: state.snapshotKey,
      });
      onChanged(result.candidateIds);
      setStatus(elements.autoDecisionStatus,
        `已采用 ${result.candidateIds.length} 项安全建议；异常项仍保留，且可整批撤销。`, "success");
      refresh();
    } catch (error) {
      setStatus(elements.autoDecisionStatus, errorMessage(error), "error");
    }
  }

  function undoLastAssisted() {
    const record = latestAssisted();
    if (!record) return;
    try {
      const result = undoDecisionBatch(state, record.batchId);
      onChanged([]);
      setStatus(elements.autoDecisionStatus,
        `已撤销最近一次自动采用：恢复 ${result.restoredCount} 项；后续人工修改保留 ${result.skippedCount} 项。`,
        "success");
      refresh();
    } catch (error) {
      setStatus(elements.autoDecisionStatus, errorMessage(error), "error");
    }
  }

  function refresh() {
    if (!state || !model) return;
    const coverage = assistedCoverage(model, state);
    const complete = reviewProgress(state).complete;
    elements.automationSummary.textContent = coverage.exceptions
      ? `安全建议 ${coverage.adopted}/${coverage.safe}；另有 ${coverage.exceptions} 项需要人工处理。`
      : `安全建议 ${coverage.adopted}/${coverage.safe}；当前没有算法异常项。`;
    elements.autoCoverageBar.max = Math.max(1, coverage.total);
    elements.autoCoverageBar.value = complete;
    elements.autoCoverageBar.setAttribute("aria-valuetext", `${complete}/${coverage.total} 项已完成`);
    elements.autoApplyAllBtn.disabled = coverage.safePending === 0;
    elements.autoUndoBtn.disabled = !latestAssisted();
  }

  function latestAssisted() {
    return [...(state?.batchHistory || [])].reverse()
      .find((row) => !row.undone && row.sourceKind === "assisted") || null;
  }
}
