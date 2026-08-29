"use strict";

import {
  normalizeIdleReviewEntry, normalizeIdleReviewPackageList,
  normalizeIdleReviewReceipt,
} from "./idle-behavior-review-contract.js";

const BASE = "/api/idle-behavior/review-packages";
const SHA = /^[0-9a-f]{64}$/;
export const IDLE_REVIEW_INTENT = "body-sway-human-review-v1";

export class IdleBehaviorReviewApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "IdleBehaviorReviewApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createIdleBehaviorReviewApi(fetchApi = globalThis.fetch) {
  return {
    async list() {
      return normalizeIdleReviewPackageList(await request(fetchApi, BASE));
    },
    async entry(packageId) {
      requirePackageId(packageId);
      const payload = await request(fetchApi, `${BASE}/${packageId}`);
      return normalizeIdleReviewEntry(payload, packageId);
    },
    async submit(packageId, body) {
      requirePackageId(packageId);
      const payload = await request(fetchApi, `${BASE}/${packageId}/decisions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Autospine-Intent": IDLE_REVIEW_INTENT,
        },
        body: JSON.stringify(body),
      });
      return normalizeIdleReviewReceipt(payload, {
        packageId, candidateSha256: body.candidate_sha256,
        baseRevision: body.base_revision, action: body.action,
      });
    },
  };
}

async function request(fetchApi, url, options = {}) {
  const { headers = {}, ...requestOptions } = options;
  const response = await fetchApi(url, {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    ...requestOptions,
    headers: { Accept: "application/json", ...headers },
  });
  let payload = null;
  try { payload = await response.json(); } catch { /* public fallback below */ }
  if (!response.ok) {
    const message = typeof payload?.message === "string"
      ? payload.message : `P10 请求失败（HTTP ${response.status}）`;
    throw new IdleBehaviorReviewApiError(message, response.status, payload);
  }
  if (payload === null) throw new Error("P10 服务返回了无效 JSON");
  return payload;
}

function requirePackageId(value) {
  if (typeof value !== "string" || !SHA.test(value)) {
    throw new Error("P10 复核包 ID 无效");
  }
}
