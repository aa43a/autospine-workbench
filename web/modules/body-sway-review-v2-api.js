"use strict";

import { reviewV2Paths } from "./body-sway-review-v2-contract.js";

export const REVIEW_V2_INTENT = "p10-body-sway-visual-review-v2";

export class BodySwayReviewV2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "BodySwayReviewV2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function requestJson(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, {
    cache: "no-store", ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  const type = response.headers?.get?.("content-type") || "";
  const payload = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const message = payload && typeof payload === "object"
      ? payload.message || payload.error : String(payload || `HTTP ${response.status}`);
    throw new BodySwayReviewV2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BodySwayReviewV2ApiError("服务返回的 JSON 结构无效", response.status, payload);
  }
  return payload;
}

export function createBodySwayReviewV2Api(jobId, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  const paths = reviewV2Paths(jobId);
  return Object.freeze({
    job: () => requestJson(fetchImpl, paths.job()),
    candidate: () => requestJson(fetchImpl, paths.candidate()),
    history: (digest) => requestJson(fetchImpl, paths.history(digest)),
    decision: (digest, revision, sha256) => requestJson(
      fetchImpl, paths.decision(digest, revision, sha256),
    ),
    submit: (digest, payload) => requestJson(fetchImpl, paths.submit(digest), {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Autospine-Intent": REVIEW_V2_INTENT,
      },
      body: JSON.stringify(payload),
    }),
    imageUrl: (digest, caseId, pngSha256) => paths.image(
      digest, caseId, pngSha256,
    ),
  });
}
