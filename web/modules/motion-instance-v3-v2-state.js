"use strict";

import {
  normalizeMotionInstanceV3V2Entry, normalizeMotionInstanceV3V2Result,
} from "./motion-instance-v3-v2-contract.js";

const ACTIVE = new Set(["queued", "running"]);
const FAILED = new Set(["failed_retryable", "failed_terminal"]);
const POLL_DELAYS = Object.freeze([350, 600, 900, 1400, 2200, 3000]);

export function motionInstanceV3V2PollDelay(attempt) {
  return POLL_DELAYS[Math.max(0, Math.min(POLL_DELAYS.length - 1, attempt))];
}

export async function runMotionInstanceV3V2({
  api, jobId, safetyRunId, dynamicRunId, onState = () => {},
  sleep = defaultSleep, startNew = false,
}) {
  const args = [jobId, safetyRunId, dynamicRunId];
  let state = normalizeMotionInstanceV3V2Entry(
    await (startNew ? api.start() : api.inspect()), ...args,
  );
  onState(state);
  if (state.status === "ready") {
    state = normalizeMotionInstanceV3V2Entry(await api.start(), ...args);
    onState(state);
  }
  let poll = 0;
  while (ACTIVE.has(state.status)) {
    await sleep(motionInstanceV3V2PollDelay(poll++));
    state = normalizeMotionInstanceV3V2Entry(
      await api.status(state.run.runId), ...args,
    );
    onState(state);
  }
  if (FAILED.has(state.status)) return Object.freeze({ kind: "failed", state });
  if (state.status !== "completed" || !state.run) {
    throw new Error("MotionInstance v3 生成进入未知状态");
  }
  const result = normalizeMotionInstanceV3V2Result(
    await api.result(state.run.runId), ...args, state.run.runId,
  );
  return Object.freeze({ kind: "completed", state, result });
}

function defaultSleep(milliseconds) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));
}
