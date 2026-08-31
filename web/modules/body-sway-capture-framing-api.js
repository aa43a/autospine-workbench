"use strict";

const SHA = /^[0-9a-f]{64}$/;
const BASE = "/api/idle-behavior/structural-probes";
export const CAPTURE_FRAMING_INTENT = "capture-framing-human-review-v1";

export class CaptureFramingApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "CaptureFramingApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function captureFramingDecisionPath(packageId) {
  if (typeof packageId !== "string" || !SHA.test(packageId)) {
    throw new Error("自动取景项目 ID 无效");
  }
  return `${BASE}/${packageId}/capture-framing-decisions`;
}

export function createCaptureFramingApi(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    submit(packageId, payload) {
      return postJson(fetchImpl, captureFramingDecisionPath(packageId), payload);
    },
  });
}

async function postJson(fetchImpl, url, payload) {
  const response = await fetchImpl(url, {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Autospine-Intent": CAPTURE_FRAMING_INTENT,
    },
    body: JSON.stringify(payload),
  });
  const type = response.headers?.get?.("content-type") || "";
  const data = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    throw new CaptureFramingApiError(message(data, response.status), response.status, data);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new CaptureFramingApiError("自动取景服务返回了无效 JSON", response.status, data);
  }
  return data;
}

function message(payload, status) {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload.message || payload.detail || payload.error || `HTTP ${status}`;
  }
  return String(payload || `HTTP ${status}`);
}
