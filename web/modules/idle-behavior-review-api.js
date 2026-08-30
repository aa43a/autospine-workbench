"use strict";

import {
  normalizeIdleReviewEntry, normalizeIdleReviewPackageList,
  normalizeIdleReviewReceipt,
} from "./idle-behavior-review-contract.js";
import {
  normalizeIdleCanvasAdjustmentDraft,
} from "./idle-behavior-canvas-adjustment-contract.js";

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
    async list(projectId = null) {
      return normalizeIdleReviewPackageList(await request(
        fetchApi, scopedUrl(BASE, projectId),
      ));
    },
    async entry(packageId, projectId = null) {
      requirePackageId(packageId);
      const payload = await request(
        fetchApi, scopedUrl(`${BASE}/${packageId}`, projectId),
      );
      return normalizeIdleReviewEntry(payload, packageId);
    },
    async entryWithCanvasAdjustment(
      packageId, candidateSha256, projectId = null,
    ) {
      requirePackageId(packageId);
      requirePackageId(candidateSha256);
      const payload = await request(fetchApi, scopedUrl(
        `${BASE}/${packageId}/canvas-adjustment-drafts/${candidateSha256}`,
        projectId,
      ));
      return normalizeIdleCanvasAdjustmentDraft(payload, {
        packageId, canvasAdjustmentSha256: candidateSha256,
      });
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

function scopedUrl(url, projectId) {
  if (projectId === null) return url;
  if (typeof projectId !== "string"
      || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(projectId)) {
    throw new Error("P10 项目 ID 无效");
  }
  return `${url}?project_id=${encodeURIComponent(projectId)}`;
}
