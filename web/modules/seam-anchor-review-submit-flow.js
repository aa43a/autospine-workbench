"use strict";

import { downloadJson } from "./motion-policy-review-utils.js";
import {
  buildSeamReviewSubmission, expectedSeamSubmissionResult,
  markSeamSubmissionConflict,
} from "./seam-anchor-review-state.js";
import { createSeamReviewSubmitController } from "./seam-anchor-review-submit-controller.js";
import { renderSeamSubmitTransition } from "./seam-anchor-review-submit-view.js";
import { setStatus, updateSeamReviewSummary } from "./seam-anchor-review-view.js";

export function verifiedCommittedRevision(snapshot) {
  const revision = snapshot?.decision?.revision;
  return Number.isInteger(revision) && revision >= 1 ? revision : null;
}

export function createSeamReviewSubmitFlow({
  api, elements, requests, busy, errorText, announce,
  getState, setState, getAddress, getPackageId, getHistoryController,
}) {
  let receipt = null;
  let pendingBaseline = null;
  let pendingExpected = null;

  function validateDecision(payload) {
    const state = getState();
    const expected = pendingExpected;
    if (payload?.candidate_sha256 !== state.candidateSha256
        || !pendingBaseline || !expected
        || payload?.revision !== pendingBaseline.revision + 1
        || !/^[0-9a-f]{64}$/.test(payload?.decision_sha256)
        || typeof payload?.reused !== "boolean"
        || payload?.status !== expected.status
        || JSON.stringify(payload?.release_gate) !== JSON.stringify(expected.releaseGate)
        || JSON.stringify(payload?.summary) !== JSON.stringify(expected.summary)) {
      throw new Error("提交响应与请求的 revision 链不一致");
    }
  }

  const controller = createSeamReviewSubmitController({
    api, validateDecision,
    onChange: (next) => {
      const nextReceipt = renderSeamSubmitTransition(elements, next);
      if (next.phase === "idle") receipt = null;
      if (nextReceipt) receipt = nextReceipt;
    },
  });

  async function refreshCommittedDecision(snapshot, token) {
    const committedRevision = verifiedCommittedRevision(snapshot);
    let state = getState();
    state = { ...state, history: null, selectedDecision: null, baseline: null, stale: false };
    setState(state);
    elements.historyList.replaceChildren();
    elements.decisionDocument.textContent = "—";
    elements.useHeadBtn.disabled = true;
    setStatus(elements.historySelectionStatus, "历史选择已清除。");
    setStatus(
      elements.baselineStatus,
      committedRevision === null
        ? "提交回执无法验证；正在从历史重新核对，不能重复提交。"
        : "本次 revision 已保存。",
      committedRevision === null ? "warning" : "success",
    );
    announce(committedRevision === null
      ? "Seam anchor review 回执无法验证，正在重新核对历史"
      : `Seam anchor review revision ${committedRevision} 已保存`);
    try {
      const history = await api.loadHistory(getAddress(), state.candidateSha256);
      if (requests.isCurrent(token)) getHistoryController().applyHistory(history);
    } catch (error) {
      if (requests.isCurrent(token)) setStatus(
        elements.baselineStatus,
        `revision 已保存，但历史刷新失败：${errorText(error)}`, "warning",
      );
    }
  }

  async function submit() {
    let payload;
    let state = getState();
    try {
      state = {
        ...state, reviewerId: elements.reviewerId.value,
        reviewNotes: elements.reviewNotes.value,
      };
      setState(state);
      payload = buildSeamReviewSubmission(state);
    } catch (error) {
      setStatus(elements.submitStatus, errorText(error), "error");
      return;
    }
    pendingBaseline = state.baseline;
    pendingExpected = expectedSeamSubmissionResult(state);
    const token = requests.next();
    const busyToken = busy.begin("mutation");
    try {
      const result = await controller.submit({
        address: getAddress(), candidateSha256: state.candidateSha256, payload,
        packageId: getPackageId(),
      });
      if (requests.isCurrent(token) && result.decisionCommitted) {
        await refreshCommittedDecision(result, token);
      }
    } catch (error) {
      if (!requests.isCurrent(token)) return;
      const snapshot = controller.snapshot();
      if (snapshot.decisionCommitted) {
        await refreshCommittedDecision(snapshot, token);
        if (verifiedCommittedRevision(snapshot) === null) {
          setStatus(elements.submitStatus, errorText(error), "error");
        }
      } else {
        const stale = markSeamSubmissionConflict(getState());
        setState(stale);
        elements.historyList.replaceChildren();
        elements.decisionDocument.textContent = "—";
        elements.useHeadBtn.disabled = true;
        setStatus(
          elements.baselineStatus,
          "提交结果不确定；请重新读取历史并刷新页面。", "warning",
        );
        setStatus(elements.historySelectionStatus, "历史选择已清除。", "warning");
        setStatus(elements.submitStatus, errorText(error), "error");
      }
    } finally {
      pendingBaseline = null;
      pendingExpected = null;
      busy.finish("mutation", busyToken);
      if (!requests.isCurrent(token) && !controller.snapshot().busy) controller.reset();
      if (requests.isCurrent(token)) updateSeamReviewSummary(elements, getState());
    }
  }

  async function retryPublication() {
    const token = requests.next();
    const busyToken = busy.begin("mutation");
    try { await controller.retryPublication(); }
    catch (error) {
      if (requests.isCurrent(token)) {
        setStatus(elements.publicationStatus, errorText(error), "error");
      }
    } finally { busy.finish("mutation", busyToken); }
  }

  function reset() {
    receipt = null;
    if (!controller.snapshot().busy) controller.reset();
  }

  function download() {
    if (!receipt) return;
    downloadJson(
      `${getState().candidate?.project_id || "autospine"}.reviewed-seam-anchor-set-receipt.json`,
      receipt,
    );
  }

  return Object.freeze({
    download, hasReceipt: () => receipt !== null, reset,
    retryPublication, snapshot: controller.snapshot, submit,
  });
}
