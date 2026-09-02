"use strict";

import {
  spine42V3V2Path, spine42V3V2ResultPath,
  spine42V3V2RunPath, spine42V3V2RunsPath,
} from "./spine42-v3-v2-contract.js";

export const SPINE42_V3_V2_INTENT = "p10-body-sway-spine42-v3-v2";

export class Spine42V3V2ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "Spine42V3V2ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function createSpine42V3V2Api(
  job, safety, dynamic, motion, fetchImpl = globalThis.fetch,
) {
  if (typeof fetchImpl !== "function") {
    throw new TypeError("fetch implementation is required");
  }
  return Object.freeze({
    inspect: () => requestJson(
      fetchImpl, spine42V3V2Path(job, safety, dynamic, motion),
    ),
    start: () => requestJson(
      fetchImpl, spine42V3V2RunsPath(job, safety, dynamic, motion), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Autospine-Intent": SPINE42_V3_V2_INTENT,
        },
        body: "{}",
      },
    ),
    status: (run) => requestJson(
      fetchImpl, spine42V3V2RunPath(job, safety, dynamic, motion, run),
    ),
    result: (run) => requestJson(
      fetchImpl, spine42V3V2ResultPath(job, safety, dynamic, motion, run),
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
    throw new Spine42V3V2ApiError(message, response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Spine42V3V2ApiError(
      "服务返回的 JSON 结构无效", response.status, payload,
    );
  }
  return payload;
}
