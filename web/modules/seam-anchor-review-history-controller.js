"use strict";

import {
  currentSeamHeadBaseline, normalizeSeamDecisionEnvelope,
  normalizeSeamReviewHistory,
} from "./seam-anchor-review-history.js";
import {
  renderDecisionDocument, setStatus, showSeamBaseline,
  showSeamHistory, updateSeamReviewSummary,
} from "./seam-anchor-review-view.js";

export function createSeamReviewHistoryController({
  api, elements, requests, busy, getAddress, getState, setState, errorText,
}) {
  function applyHistory(payload) {
    let state = getState();
    state = {
      ...state,
      history: normalizeSeamReviewHistory(payload, state.candidateSha256),
      selectedDecision: null, baseline: null, stale: false,
    };
    setState(state);
    showSeamHistory(elements, state.history);
    elements.decisionDocument.textContent = "—";
    setStatus(elements.historySelectionStatus, "尚未选择历史 revision。");
    updateSeamReviewSummary(elements, state);
  }

  async function refresh() {
    const state = getState();
    if (!state.candidate) return;
    const token = requests.next();
    const busyToken = busy.begin("history");
    setStatus(elements.baselineStatus, "正在重新读取历史…");
    try {
      const payload = await api.loadHistory(getAddress(), state.candidateSha256);
      if (requests.isCurrent(token)) applyHistory(payload);
    } catch (error) {
      if (requests.isCurrent(token)) setStatus(
        elements.baselineStatus, `历史读取失败：${errorText(error)}`, "error",
      );
    } finally { busy.finish("history", busyToken); }
  }

  async function select(target) {
    const state = getState();
    const revision = Number(target.dataset.historyRevision);
    const digest = target.dataset.historySha;
    const row = state.history?.rows.find(
      (item) => item.revision === revision && item.decisionSha256 === digest,
    );
    if (!row) return;
    const token = requests.next();
    const busyToken = busy.begin("history");
    setStatus(elements.historySelectionStatus, `正在读取 revision ${revision}…`);
    try {
      const payload = await api.loadDecision(
        getAddress(), state.candidateSha256, revision, digest,
      );
      if (!requests.isCurrent(token)) return;
      const next = { ...getState(), selectedDecision: normalizeSeamDecisionEnvelope(
        payload, state.candidateSha256, revision, digest,
      ) };
      setState(next);
      for (const button of elements.historyList.querySelectorAll("button")) {
        if (button === target) button.setAttribute("aria-current", "true");
        else button.removeAttribute("aria-current");
      }
      renderDecisionDocument(elements.decisionDocument, next.selectedDecision);
      setStatus(
        elements.historySelectionStatus,
        `已读取 revision ${revision} / ${digest}`, "success",
      );
    } catch (error) {
      if (requests.isCurrent(token)) setStatus(
        elements.historySelectionStatus, `历史读取失败：${errorText(error)}`, "error",
      );
    } finally { busy.finish("history", busyToken); }
  }

  function applyHeadBaseline() {
    try {
      const state = getState();
      if (state.stale || !state.history) throw new Error("请先重新读取历史");
      const next = {
        ...state, baseline: currentSeamHeadBaseline(state.history), stale: false,
      };
      setState(next);
      showSeamBaseline(elements, next.baseline);
      updateSeamReviewSummary(elements, next);
    } catch (error) {
      setStatus(elements.baselineStatus, errorText(error), "error");
    }
  }

  return Object.freeze({ applyHistory, applyHeadBaseline, refresh, select });
}
