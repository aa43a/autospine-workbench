"use strict";

import {
  normalizeDynamicSeamEntry, normalizeDynamicSeamResult,
} from "./body-sway-dynamic-seam-v2-contract.js";

const ACTIVE = new Set(["queued", "running"]);
const FAILED = new Set(["failed_retryable", "failed_terminal"]);
const POLL_DELAYS = Object.freeze([400, 700, 1200, 2000, 3000, 4000]);

export function dynamicSeamPollDelay(attempt) {
  const index = Math.max(0, Math.min(POLL_DELAYS.length - 1, attempt));
  return POLL_DELAYS[index];
}

export async function runDynamicSeamV2({
  api, jobId, safetyRunId, onState = () => {}, sleep = defaultSleep,
  startNew = false,
}) {
  let state = normalizeDynamicSeamEntry(
    await (startNew ? api.start() : api.inspect()), jobId, safetyRunId,
  );
  onState(state);
  if (state.status === "ready") {
    state = normalizeDynamicSeamEntry(await api.start(), jobId, safetyRunId);
    onState(state);
  }
  let poll = 0;
  while (ACTIVE.has(state.status)) {
    await sleep(dynamicSeamPollDelay(poll++));
    state = normalizeDynamicSeamEntry(
      await api.status(state.run.runId), jobId, safetyRunId,
    );
    onState(state);
  }
  if (FAILED.has(state.status)) return Object.freeze({ kind: "failed", state });
  if (state.status !== "completed" || !state.run) {
    throw new Error("动态接缝分析进入未知状态");
  }
  const result = normalizeDynamicSeamResult(
    await api.result(state.run.runId), jobId, safetyRunId, state.run.runId,
  );
  return Object.freeze({ kind: "completed", state, result });
}

function defaultSleep(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}
