"use strict";

const SHA = /^[0-9a-f]{64}$/;
const BASE = "/api/idle-behavior/structural-probes";

export class BodySwayProbeApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "BodySwayProbeApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function structuralProbePaths(packageId = null) {
  if (packageId === null) return BASE;
  if (typeof packageId !== "string" || !SHA.test(packageId)) {
    throw new Error("结构探针项目 ID 无效");
  }
  return `${BASE}/${packageId}`;
}

export function createBodySwayProbeApi(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    list() { return requestJson(fetchImpl, structuralProbePaths()); },
    entry(packageId) { return requestJson(fetchImpl, structuralProbePaths(packageId)); },
  });
}

async function requestJson(fetchImpl, url) {
  const response = await fetchImpl(url, {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  const type = response.headers?.get?.("content-type") || "";
  const payload = type.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    throw new BodySwayProbeApiError(message(payload, response.status), response.status, payload);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new BodySwayProbeApiError("结构探针服务返回了无效 JSON", response.status, payload);
  }
  return payload;
}

function message(payload, status) {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload.message || payload.detail || payload.error || `HTTP ${status}`;
  }
  return String(payload || `HTTP ${status}`);
}
