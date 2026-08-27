"use strict";

import { seamAnchorReviewPaths } from "./seam-anchor-review-address.js";

export const REVIEW_INTENT = "seam-anchor-review";

export class SeamAnchorReviewApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "SeamAnchorReviewApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function responsePayload(response) {
  const type = response.headers?.get?.("content-type") || "";
  if (type.includes("application/json")) {
    return response.json().catch(() => null);
  }
  return response.text().catch(() => "");
}

function errorMessage(payload, status) {
  if (payload && typeof payload === "object") {
    return payload.message || payload.detail || payload.error || `HTTP ${status}`;
  }
  return String(payload || `HTTP ${status}`);
}

async function requestJson(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, {
    cache: "no-store", ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  const payload = await responsePayload(response);
  if (!response.ok) {
    throw new SeamAnchorReviewApiError(
      errorMessage(payload, response.status), response.status, payload,
    );
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new SeamAnchorReviewApiError("服务返回的 JSON 结构无效", response.status, payload);
  }
  return payload;
}

export function createSeamAnchorReviewApi(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    loadCandidate(address) {
      return requestJson(fetchImpl, seamAnchorReviewPaths(address).candidate());
    },
    loadHistory(address, candidateSha256) {
      return requestJson(
        fetchImpl, seamAnchorReviewPaths(address).history(candidateSha256),
      );
    },
    loadDecision(address, candidateSha256, revision, decisionSha256) {
      return requestJson(fetchImpl, seamAnchorReviewPaths(address).decision(
        candidateSha256, revision, decisionSha256,
      ));
    },
    submit(address, candidateSha256, payload) {
      return requestJson(fetchImpl, seamAnchorReviewPaths(address).submit(candidateSha256), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Autospine-Intent": REVIEW_INTENT,
        },
        body: JSON.stringify(payload),
      });
    },
    imageUrl(address, candidateSha256, optionId, attachmentId, imageSha256) {
      return seamAnchorReviewPaths(address).optionImage(
        candidateSha256, optionId, attachmentId, imageSha256,
      );
    },
  });
}
