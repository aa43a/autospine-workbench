import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyAutoApi } from "../modules/motion-policy-auto-api.js";

const PACKAGE_A = "a".repeat(64);
const PACKAGE_B = "b".repeat(64);

function packageRow(packageId = PACKAGE_A, documents = false, alignment = "current") {
  const row = {
    format: "autospine-motion-policy-review-package",
    format_version: 2,
    project_id: packageId === PACKAGE_A ? "sample-a" : "sample-b",
    package_id: packageId,
    motion_id: "kimodo-wave",
    clip_id: "wave-left",
    identities: {
      policy_sha256: "1".repeat(64),
      foot_candidates_sha256: "2".repeat(64),
      depth_candidates_sha256: "3".repeat(64),
    },
    inventory: {
      total_count: 119,
      foot_count: 119,
      depth_count: 0,
      unconstrained_count: 1,
      candidate_ids_sha256: "4".repeat(64),
    },
    automation_profile: "safe-assist-v1",
    authoring_alignment: alignment,
  };
  if (documents) {
    row.policy_json = "{\"policy\":true}";
    row.foot_candidates_json = "{\"foot\":true}";
    row.depth_candidates_json = "{\"depth\":true}";
  }
  return row;
}

function listPayload(rows = [packageRow()]) {
  return {
    format: "autospine-motion-policy-package-list",
    format_version: 2,
    count: rows.length,
    skipped_count: 0,
    recommended_package_id: rows[0]?.package_id ?? null,
    packages: rows,
  };
}

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

test("automatic package API uses read-only same-origin requests and exact package identity", async () => {
  const calls = [];
  const api = createMotionPolicyAutoApi(async (url, options) => {
    calls.push({ url, options });
    return url.endsWith(PACKAGE_A)
      ? response(packageRow(PACKAGE_A, true))
      : response(listPayload());
  });

  const list = await api.list();
  const detail = await api.package(PACKAGE_A);

  assert.equal(list.recommended_package_id, PACKAGE_A);
  assert.equal(detail.package_id, PACKAGE_A);
  assert.deepEqual(calls.map((call) => call.url), [
    "/api/motion-policy/review-packages",
    `/api/motion-policy/review-packages/${PACKAGE_A}`,
  ]);
  for (const call of calls) {
    assert.equal(call.options.method, "GET");
    assert.equal(call.options.credentials, "same-origin");
    assert.equal(call.options.cache, "no-store");
    assert.equal(call.options.headers.Accept, "application/json");
  }
});

test("automatic package API rejects malformed IDs before making a request", async () => {
  let requestCount = 0;
  const api = createMotionPolicyAutoApi(async () => {
    requestCount += 1;
    return response({});
  });

  await assert.rejects(api.package("sample-a"), /ID 无效/);
  await assert.rejects(api.package("A".repeat(64)), /ID 无效/);
  assert.equal(requestCount, 0);
});

test("automatic package detail must retain the requested exact package identity", async () => {
  const api = createMotionPolicyAutoApi(async () => response(packageRow(PACKAGE_B, true)));
  await assert.rejects(api.package(PACKAGE_A), /详情身份不匹配/);
});

test("automatic package list rejects duplicate identities and unknown recommendations", async () => {
  const duplicate = listPayload([packageRow(PACKAGE_A), packageRow(PACKAGE_A)]);
  const apiDuplicate = createMotionPolicyAutoApi(async () => response(duplicate));
  await assert.rejects(apiDuplicate.list(), /重复或未知推荐项/);

  const unknown = listPayload([packageRow(PACKAGE_A)]);
  unknown.recommended_package_id = PACKAGE_B;
  const apiUnknown = createMotionPolicyAutoApi(async () => response(unknown));
  await assert.rejects(apiUnknown.list(), /重复或未知推荐项/);
});

test("automatic package list accepts historical rows but never a historical recommendation", async () => {
  const rows = [
    packageRow(PACKAGE_A, false, "historical"),
    packageRow(PACKAGE_B),
  ];
  const accepted = listPayload(rows);
  accepted.recommended_package_id = PACKAGE_B;
  const list = await createMotionPolicyAutoApi(async () => response(accepted)).list();
  assert.equal(list.packages[0].authoring_alignment, "historical");

  const unsafe = listPayload(rows);
  unsafe.recommended_package_id = PACKAGE_A;
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(unsafe)).list(),
    /不得推荐历史版本/,
  );
});

test("automatic package API fails closed on extra fields, invalid counts, and missing evidence", async () => {
  const extra = listPayload();
  extra.local_path = "E:/private/reviews";
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(extra)).list(),
    /字段无效/,
  );

  const invalidCount = listPayload();
  invalidCount.count = 2;
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(invalidCount)).list(),
    /合同无效/,
  );

  const inconsistentInventory = packageRow(PACKAGE_A, true);
  inconsistentInventory.inventory.depth_count = 1;
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(inconsistentInventory)).package(PACKAGE_A),
    /候选摘要无效/,
  );

  const missingDocument = packageRow(PACKAGE_A, true);
  missingDocument.foot_candidates_json = "";
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(missingDocument)).package(PACKAGE_A),
    /缺少 JSON 证据/,
  );

  const invalidAlignment = packageRow(PACKAGE_A, true);
  invalidAlignment.authoring_alignment = "unknown";
  await assert.rejects(
    createMotionPolicyAutoApi(async () => response(invalidAlignment)).package(PACKAGE_A),
    /对齐状态无效/,
  );
});

test("automatic package API surfaces the server's public error without leaking parsing failures", async () => {
  const api = createMotionPolicyAutoApi(async () => response(
    { error: "not_found", message: "复核包不存在" },
    { ok: false, status: 404 },
  ));
  await assert.rejects(api.list(), /复核包不存在/);

  const invalidJson = createMotionPolicyAutoApi(async () => ({
    ok: false,
    status: 500,
    json: async () => { throw new Error("private parser detail"); },
  }));
  await assert.rejects(invalidJson.list(), /HTTP 500/);
});
