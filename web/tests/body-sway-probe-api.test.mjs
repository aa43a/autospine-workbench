import assert from "node:assert/strict";
import test from "node:test";

import {
  BodySwayProbeApiError, createBodySwayProbeApi, structuralProbePaths,
} from "../modules/body-sway-probe-api.js";
import { PACKAGE_B, inventoryFixture, probeEntryFixture } from "./body-sway-probe-fixtures.mjs";

function response(payload, { ok = true, status = 200, type = "application/json" } = {}) {
  return {
    ok,
    status,
    headers: { get: () => type },
    json: async () => payload,
    text: async () => typeof payload === "string" ? payload : JSON.stringify(payload),
  };
}

test("API uses zero-write no-store GET routes for list and exact package", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return response(url.endsWith(PACKAGE_B) ? probeEntryFixture() : inventoryFixture());
  };
  const api = createBodySwayProbeApi(fetchImpl);
  assert.equal((await api.list()).packages.length, 1);
  assert.equal((await api.entry(PACKAGE_B)).package.package_id, PACKAGE_B);
  assert.deepEqual(calls.map((row) => row.url), [
    "/api/idle-behavior/structural-probes",
    `/api/idle-behavior/structural-probes/${PACKAGE_B}`,
  ]);
  for (const { options } of calls) {
    assert.equal(options.method, "GET");
    assert.equal(options.cache, "no-store");
    assert.equal(options.headers.Accept, "application/json");
    assert.equal(options.body, undefined);
  }
});

test("API rejects malformed package IDs before fetch", async () => {
  let called = false;
  const api = createBodySwayProbeApi(async () => { called = true; });
  assert.throws(() => api.entry("../latest"), /项目 ID 无效/);
  assert.equal(called, false);
  assert.throws(() => structuralProbePaths("A".repeat(64)), /项目 ID 无效/);
});

test("API preserves safe HTTP errors and rejects non-object success payloads", async () => {
  const conflict = createBodySwayProbeApi(async () => response({
    error: "body_sway_probe_head_changed",
    message: "The P10.1 review head changed; reload the probe list.",
  }, { ok: false, status: 409 }));
  await assert.rejects(
    () => conflict.entry(PACKAGE_B),
    (error) => error instanceof BodySwayProbeApiError
      && error.status === 409 && /review head changed/.test(error.message),
  );

  const invalid = createBodySwayProbeApi(async () => response(["not", "an", "object"]));
  await assert.rejects(() => invalid.list(), /无效 JSON/);
});
