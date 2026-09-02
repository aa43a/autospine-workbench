"use strict";

import {
  normalizeSafetyAnalysisEntry, normalizeSafetyAnalysisResult,
} from "./body-sway-safety-analysis-v2-contract.js";

const ACTIVE = new Set(["queued", "running"]);
const FAILED = new Set(["failed_retryable", "failed_terminal"]);
const POLL_DELAYS = Object.freeze([400, 700, 1200, 2000, 3000, 4000]);

export function safetyAnalysisPollDelay(attempt) {
  const index = Math.max(0, Math.min(POLL_DELAYS.length - 1, attempt));
  return POLL_DELAYS[index];
}

export async function runSafetyAnalysisV2({
  api, jobId, onState = () => {}, sleep = defaultSleep, startNew = false,
}) {
  let state = normalizeSafetyAnalysisEntry(
    await (startNew ? api.start() : api.inspect()), jobId,
  );
  onState(state);
  if (state.status === "ready") {
    state = normalizeSafetyAnalysisEntry(await api.start(), jobId);
    onState(state);
  }
  let attempt = 0;
  while (ACTIVE.has(state.status)) {
    await sleep(safetyAnalysisPollDelay(attempt++));
    state = normalizeSafetyAnalysisEntry(
      await api.status(state.run.runId), jobId,
    );
    onState(state);
  }
  if (FAILED.has(state.status)) {
    return Object.freeze({ kind: "failed", state });
  }
  if (state.status !== "completed" || !state.run) {
    throw new Error("安全分析进入未知状态");
  }
  const result = normalizeSafetyAnalysisResult(
    await api.result(state.run.runId), jobId, state.run.runId,
  );
  return Object.freeze({ kind: "completed", state, result });
}

function defaultSleep(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}
