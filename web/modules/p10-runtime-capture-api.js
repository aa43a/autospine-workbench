"use strict";

import { createIdleBehaviorReviewApi } from "./idle-behavior-review-api.js";
import {
  normalizeRuntimeCaptureJob, normalizeRuntimeCapturePreflight,
} from "./p10-runtime-capture-contract.js";

const BASE = "/api/p10/runtime-capture";
export const CAPTURE_INTENT = "p10-official-runtime-capture-v2";

export class P10RuntimeCaptureApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "P10RuntimeCaptureApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createP10RuntimeCaptureApi(fetchImpl = globalThis.fetch) {
  const packages = createIdleBehaviorReviewApi(fetchImpl);
  return {
    listPackages: () => packages.list(),
    async preflight(packageId) {
      requireSha(packageId, "package_id");
      const value = await request(fetchImpl, `${BASE}/packages/${packageId}`);
      return normalizeRuntimeCapturePreflight(value, packageId);
    },
    async submit(body) {
      const value = await request(fetchImpl, `${BASE}/jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Autospine-Intent": CAPTURE_INTENT,
        },
        body: JSON.stringify(body),
      });
      return normalizeRuntimeCaptureJob(value);
    },
    async job(jobId) {
      requireSha(jobId, "job_id");
      const value = await request(fetchImpl, `${BASE}/jobs/${jobId}`);
      return normalizeRuntimeCaptureJob(value, jobId);
    },
  };
}

async function request(fetchImpl, url, options = {}) {
  const { headers = {}, ...requestOptions } = options;
  const response = await fetchImpl(url, {
    credentials: "same-origin", cache: "no-store",
    ...requestOptions,
    headers: { Accept: "application/json", ...headers },
  });
  let payload = null;
  try { payload = await response.json(); } catch { /* public fallback below */ }
  if (!response.ok) {
    const message = typeof payload?.message === "string"
      ? payload.message : `Runtime 采集请求失败（HTTP ${response.status}）`;
    throw new P10RuntimeCaptureApiError(message, response.status, payload);
  }
  if (payload === null) throw new Error("Runtime 采集服务返回了无效 JSON");
  return payload;
}

function requireSha(value, label) {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value)) {
    throw new Error(`${label} 无效`);
  }
}
