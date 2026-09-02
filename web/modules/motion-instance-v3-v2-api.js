"use strict";

import {
  motionInstanceV3V2Path, motionInstanceV3V2ResultPath,
  motionInstanceV3V2RunPath, motionInstanceV3V2RunsPath,
} from "./motion-instance-v3-v2-contract.js";

export const MOTION_INSTANCE_V3_V2_INTENT = "p10-body-sway-motion-instance-v3-v2";

export class MotionInstanceV3V2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "MotionInstanceV3V2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createMotionInstanceV3V2Api(
  jobId, safetyRunId, dynamicRunId, fetchImpl = globalThis.fetch,
) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    inspect: () => requestJson(
      fetchImpl, motionInstanceV3V2Path(jobId, safetyRunId, dynamicRunId),
    ),
    start: () => requestJson(
      fetchImpl, motionInstanceV3V2RunsPath(jobId, safetyRunId, dynamicRunId), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Autospine-Intent": MOTION_INSTANCE_V3_V2_INTENT,
        },
        body: "{}",
      },
    ),
    status: (runId) => requestJson(
      fetchImpl,
      motionInstanceV3V2RunPath(jobId, safetyRunId, dynamicRunId, runId),
    ),
    result: (runId) => requestJson(
      fetchImpl,
      motionInstanceV3V2ResultPath(jobId, safetyRunId, dynamicRunId, runId),
    ),
  });
}

async function requestJson(fetchImpl, url, options = {}) {
  const { headers = {}, ...rest } = options;
  const response = await fetchImpl(url, {
    credentials: "same-origin", cache: "no-store", ...rest,
    headers: { Accept: "application/json", ...headers },
  });
  const type = response.headers?.get?.("content-type") || "";
  const payload = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const message = payload && typeof payload === "object"
      ? payload.message || payload.error : String(payload || `HTTP ${response.status}`);
    throw new MotionInstanceV3V2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new MotionInstanceV3V2ApiError(
      "服务返回的 JSON 结构无效", response.status, payload,
    );
  }
  return payload;
}
