"use strict";

import { reviewAdmissionV2Path } from "./body-sway-review-admission-v2-contract.js";

export class BodySwayReviewAdmissionV2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "BodySwayReviewAdmissionV2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createBodySwayReviewAdmissionV2Api(
  jobId, fetchImpl = globalThis.fetch,
) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  const url = reviewAdmissionV2Path(jobId);
  return Object.freeze({
    compile: () => requestJson(fetchImpl, url),
  });
}

async function requestJson(fetchImpl, url) {
  const response = await fetchImpl(url, {
    cache: "no-store", headers: { Accept: "application/json" },
  });
  const type = response.headers?.get?.("content-type") || "";
  const payload = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const message = payload && typeof payload === "object"
      ? payload.message || payload.error : String(payload || `HTTP ${response.status}`);
    throw new BodySwayReviewAdmissionV2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BodySwayReviewAdmissionV2ApiError(
      "服务返回的 JSON 结构无效", response.status, payload,
    );
  }
  return payload;
}
