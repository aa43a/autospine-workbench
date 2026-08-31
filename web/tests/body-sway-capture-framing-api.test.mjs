import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPTURE_FRAMING_INTENT, CaptureFramingApiError,
  captureFramingDecisionPath, createCaptureFramingApi,
} from "../modules/body-sway-capture-framing-api.js";
import { PACKAGE_B } from "./body-sway-probe-fixtures.mjs";

function response(payload, { ok = true, status = 200 } = {}) {
  return {
    ok, status, headers: { get: () => "application/json" },
    json: async () => payload, text: async () => JSON.stringify(payload),
  };
}

test("capture framing POST is same-origin, intent-bound, and JSON-only", async () => {
  const calls = [];
  const payload = { format: "autospine-capture-framing-submission" };
  const api = createCaptureFramingApi(async (url, options) => {
    calls.push({ url, options });
    return response({ format: "autospine-capture-framing-receipt" });
  });
  await api.submit(PACKAGE_B, payload);
  assert.equal(calls[0].url,
    `/api/idle-behavior/structural-probes/${PACKAGE_B}/capture-framing-decisions`);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(calls[0].options.headers["X-Autospine-Intent"], CAPTURE_FRAMING_INTENT);
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), payload);
});

test("capture framing API rejects malformed package IDs and preserves conflicts", async () => {
  let called = false;
  const invalid = createCaptureFramingApi(async () => { called = true; });
  assert.throws(() => invalid.submit("../latest", {}), /项目 ID 无效/);
  assert.equal(called, false);
  assert.throws(() => captureFramingDecisionPath("A".repeat(64)), /项目 ID 无效/);

  const conflict = createCaptureFramingApi(async () => response({
    error: "capture_framing_revision_conflict",
    message: "Framing revision is stale; reload exact history.",
  }, { ok: false, status: 409 }));
  await assert.rejects(() => conflict.submit(PACKAGE_B, {}), (error) =>
    error instanceof CaptureFramingApiError && error.status === 409
      && /reload exact history/.test(error.message));
});
