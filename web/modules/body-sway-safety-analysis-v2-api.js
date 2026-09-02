"use strict";

import {
  safetyAnalysisV2Path, safetyAnalysisV2ResultPath,
  safetyAnalysisV2RunPath, safetyAnalysisV2RunsPath,
} from "./body-sway-safety-analysis-v2-contract.js";

export const SAFETY_ANALYSIS_V2_INTENT = "p10-body-sway-safety-analysis-v2";

export class BodySwaySafetyAnalysisV2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "BodySwaySafetyAnalysisV2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createBodySwaySafetyAnalysisV2Api(
  jobId, fetchImpl = globalThis.fetch,
) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    inspect: () => requestJson(fetchImpl, safetyAnalysisV2Path(jobId)),
    start: () => requestJson(fetchImpl, safetyAnalysisV2RunsPath(jobId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Autospine-Intent": SAFETY_ANALYSIS_V2_INTENT,
      },
      body: "{}",
    }),
    status: (runId) => requestJson(
      fetchImpl, safetyAnalysisV2RunPath(jobId, runId),
    ),
    result: (runId) => requestJson(
      fetchImpl, safetyAnalysisV2ResultPath(jobId, runId),
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
    throw new BodySwaySafetyAnalysisV2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BodySwaySafetyAnalysisV2ApiError(
      "服务返回的 JSON 结构无效", response.status, payload,
    );
  }
  return payload;
}
