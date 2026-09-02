"use strict";

import {
  dynamicSeamV2Path, dynamicSeamV2ResultPath,
  dynamicSeamV2RunPath, dynamicSeamV2RunsPath,
} from "./body-sway-dynamic-seam-v2-contract.js";

export const DYNAMIC_SEAM_V2_INTENT = "p10-body-sway-dynamic-seam-v2";

export class BodySwayDynamicSeamV2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "BodySwayDynamicSeamV2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createBodySwayDynamicSeamV2Api(
  jobId, safetyRunId, fetchImpl = globalThis.fetch,
) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    inspect: () => requestJson(fetchImpl, dynamicSeamV2Path(jobId, safetyRunId)),
    start: () => requestJson(fetchImpl, dynamicSeamV2RunsPath(jobId, safetyRunId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Autospine-Intent": DYNAMIC_SEAM_V2_INTENT,
      },
      body: "{}",
    }),
    status: (runId) => requestJson(
      fetchImpl, dynamicSeamV2RunPath(jobId, safetyRunId, runId),
    ),
    result: (runId) => requestJson(
      fetchImpl, dynamicSeamV2ResultPath(jobId, safetyRunId, runId),
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
    throw new BodySwayDynamicSeamV2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BodySwayDynamicSeamV2ApiError(
      "服务返回的 JSON 结构无效", response.status, payload,
    );
  }
  return payload;
}
