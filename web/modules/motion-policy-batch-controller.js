import { applyBatchPreview, createBatchPreview } from "./motion-policy-batch-model.js";
import { undoDecisionBatch } from "./motion-policy-review-state.js";
import {
  renderDecisionSummary, renderReviewSegments, selectedSegmentIds,
  setAllSegmentsSelected, updateSegmentProgress,
} from "./motion-policy-batch-view.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

export function createMotionPolicyBatchController(elements, { onChanged, onLocate }) {
  let state = null;
  let model = null;
  let preview = null;

  elements.segmentList.addEventListener("change", selectionChanged);
  elements.segmentList.addEventListener("click", locateSegment);
  elements.selectAllSegments.addEventListener("change", () => {
    setAllSegmentsSelected(elements.segmentList, elements.selectAllSegments.checked);
    rebuildPreview();
  });
  elements.batchAction.addEventListener("change", rebuildPreview);
  elements.batchReason.addEventListener("input", rebuildPreview);
  elements.batchConfirm.addEventListener("change", refreshApplyState);
  elements.batchOverwriteConfirm.addEventListener("change", refreshApplyState);
  elements.batchForm.addEventListener("submit", applyPreview);
  elements.batchUndo.addEventListener("click", undoLastBatch);

  return { load, clear, refresh };

  function load(nextState, evidenceModel) {
    state = nextState;
    model = evidenceModel;
    preview = null;
    renderReviewSegments(elements.segmentList, model.reviewSegments);
    elements.selectAllSegments.checked = false;
    elements.batchForm.reset();
    elements.batchOverwriteRow.hidden = true;
    elements.batchUndo.disabled = true;
    elements.segmentBadge.textContent = `0 / ${actionableCount()} 可裁决段已选`;
    updateStaticState();
    setStatus(elements.batchStatus, "请选择一个或多个证据段；系统不会预选 action。", "warning");
  }

  function clear() {
    state = null;
    model = null;
    preview = null;
    elements.segmentList.replaceChildren();
    elements.decisionSummary.replaceChildren();
    elements.batchForm.reset();
    elements.selectAllSegments.checked = false;
    elements.segmentBadge.textContent = "0 段";
    elements.batchPreview.textContent = "尚未形成批量预览。";
    elements.batchConfirm.disabled = true;
    elements.batchOverwriteRow.hidden = true;
    elements.batchApply.disabled = true;
    elements.batchUndo.disabled = true;
  }

  function refresh() {
    if (!state || !model) return;
    if (preview && preview.decisionVersion !== state.decisionVersion) rebuildPreview();
    elements.batchUndo.disabled = !latestManualBatch();
    updateStaticState();
  }

  function selectionChanged(event) {
    if (!event.target.matches("[data-segment-select]")) return;
    const enabled = [...elements.segmentList.querySelectorAll("[data-segment-select]:not(:disabled)")];
    elements.selectAllSegments.checked = enabled.length > 0 && enabled.every((input) => input.checked);
    elements.selectAllSegments.indeterminate = enabled.some((input) => input.checked) && !elements.selectAllSegments.checked;
    rebuildPreview();
  }

  function locateSegment(event) {
    const button = event.target.closest("[data-locate-segment]");
    if (!button || !model) return;
    const segment = model.reviewSegments.find((row) => row.segmentId === button.dataset.locateSegment);
    if (segment) onLocate(segment);
  }

  function rebuildPreview() {
    invalidatePreview();
    if (!state || !model) return;
    const segmentIds = selectedSegmentIds(elements.segmentList);
    const segments = model.reviewSegments.filter((row) => segmentIds.includes(row.segmentId));
    elements.segmentBadge.textContent = `${segments.length} / ${actionableCount()} 可裁决段已选`;
    const candidateIds = segments.flatMap((row) => row.candidateIds);
    const action = elements.batchAction.value;
    const reason_code = elements.batchReason.value.trim();
    if (!candidateIds.length || !action || !reason_code) {
      elements.batchPreview.textContent = `已选 ${segments.length} 段、${candidateIds.length} 项；还需显式选择 action 并填写 reason。`;
      setStatus(elements.batchStatus, "批量预览尚不完整。", "warning");
      return;
    }
    try {
      preview = createBatchPreview(state, candidateIds, { action, reason_code });
      elements.batchPreview.textContent = `冻结预览：${segments.length} 段、${preview.candidateIds.length} 个精确 candidate ID；其中 ${preview.overwriteCount} 项已有草稿。`;
      elements.batchConfirm.disabled = false;
      elements.batchOverwriteRow.hidden = preview.overwriteCount === 0;
      setStatus(elements.batchStatus, "请核对冻结范围后确认；修改任何字段都会使预览失效。", "warning");
    } catch (error) {
      elements.batchPreview.textContent = `无法形成预览：${errorMessage(error)}`;
      setStatus(elements.batchStatus, errorMessage(error), "error");
    }
    refreshApplyState();
  }

  function invalidatePreview() {
    preview = null;
    elements.batchConfirm.checked = false;
    elements.batchConfirm.disabled = true;
    elements.batchOverwriteConfirm.checked = false;
    elements.batchOverwriteRow.hidden = true;
    elements.batchApply.disabled = true;
  }

  function refreshApplyState() {
    elements.batchApply.disabled = !preview || !elements.batchConfirm.checked ||
      (preview.overwriteCount > 0 && !elements.batchOverwriteConfirm.checked);
  }

  function applyPreview(event) {
    event.preventDefault();
    if (!preview || elements.batchApply.disabled) return;
    try {
      const result = applyBatchPreview(state, preview);
      elements.batchUndo.disabled = false;
      const count = result.candidateIds.length;
      resetDraftControls();
      onChanged(result.candidateIds);
      setStatus(elements.batchStatus, `已将 ${count} 项写入可撤销草稿；没有发布任何决定。`, "success");
    } catch (error) {
      invalidatePreview();
      setStatus(elements.batchStatus, errorMessage(error), "error");
    }
  }

  function undoLastBatch() {
    const record = latestManualBatch();
    if (!record) return;
    try {
      const result = undoDecisionBatch(state, record.batchId);
      elements.batchUndo.disabled = !latestManualBatch();
      onChanged([]);
      setStatus(elements.batchStatus, `已撤销 ${result.restoredCount} 项；${result.skippedCount} 项因后续逐项修改而保留。`, "success");
    } catch (error) {
      setStatus(elements.batchStatus, errorMessage(error), "error");
    }
  }

  function resetDraftControls() {
    setAllSegmentsSelected(elements.segmentList, false);
    elements.selectAllSegments.checked = false;
    elements.selectAllSegments.indeterminate = false;
    elements.batchAction.value = "";
    elements.batchReason.value = "";
    invalidatePreview();
    elements.segmentBadge.textContent = `0 / ${actionableCount()} 可裁决段已选`;
    elements.batchPreview.textContent = "尚未形成批量预览。";
  }

  function updateStaticState() {
    updateSegmentProgress(elements.segmentList, model.reviewSegments, state);
    renderDecisionSummary(elements.decisionSummary, state);
  }

  function actionableCount() {
    return model?.reviewSegments.filter((row) => row.candidateIds.length > 0).length || 0;
  }

  function latestManualBatch() {
    return [...(state?.batchHistory || [])].reverse()
      .find((row) => !row.undone && row.sourceKind === "batch") || null;
  }
}
