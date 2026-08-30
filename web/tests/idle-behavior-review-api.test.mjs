import assert from "node:assert/strict";
import test from "node:test";

import {
  IdleBehaviorReviewApiError, createIdleBehaviorReviewApi,
} from "../modules/idle-behavior-review-api.js";
import { buildIdleReviewSubmission } from "../modules/idle-behavior-review-model.js";
import {
  DIGESTS, canvasAdjustmentDraftEntry, entryDocument, jsonResponse,
  packageList, receiptDocument,
} from "./idle-behavior-review-fixtures.mjs";
import { ADJUSTMENT_SHA } from "./body-sway-canvas-adjustment-fixtures.mjs";

test("API loads the automatic package and submits one explicit path-free decision", async () => {
  const calls = [];
  const api = createIdleBehaviorReviewApi(async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/decisions")) return jsonResponse(201, receiptDocument());
    if (url.endsWith(DIGESTS.package)) return jsonResponse(200, entryDocument());
    return jsonResponse(200, packageList());
  });
  const list = await api.list();
  const entry = await api.entry(list.recommended_package_id);
  const body = buildIdleReviewSubmission(entry, "adjust", {
    cycles: 2, lowerAmplitude: 0.7, headAmplitude: 0.2, phaseDelay: 0.04,
  });
  const receipt = await api.submit(DIGESTS.package, body);

  assert.equal(list.count, 1);
  assert.equal(entry.package.project_id, "seethrough_output");
  assert.equal(receipt.decision_sha256, DIGESTS.decision);
  assert.deepEqual(calls.map((call) => call.url), [
    "/api/idle-behavior/review-packages",
    `/api/idle-behavior/review-packages/${DIGESTS.package}`,
    `/api/idle-behavior/review-packages/${DIGESTS.package}/decisions`,
  ]);
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(calls[2].options.method, "POST");
  assert.equal(calls[2].options.headers.Accept, "application/json");
  assert.equal(calls[2].options.headers["X-Autospine-Intent"], "body-sway-human-review-v1");
  assert.equal(JSON.parse(calls[2].options.body).explicit_confirmation, true);
});

test("API rejects package cross-wiring, private paths, and elevated draft claims", async () => {
  const crosswired = entryDocument();
  crosswired.package.package_id = "9".repeat(64);
  await assert.rejects(
    createIdleBehaviorReviewApi(async () => jsonResponse(200, crosswired)).entry(DIGESTS.package),
    /身份串线/,
  );

  const privatePath = entryDocument();
  privatePath.candidate.target_capabilities.local_path = "E:/private/state";
  await assert.rejects(
    createIdleBehaviorReviewApi(async () => jsonResponse(200, privatePath)).entry(DIGESTS.package),
    /本机路径字段/,
  );

  const elevated = entryDocument();
  elevated.suggestion.claims.safe_range = true;
  await assert.rejects(
    createIdleBehaviorReviewApi(async () => jsonResponse(200, elevated)).entry(DIGESTS.package),
    /不能声明通过/,
  );
});

test("detail contract rejects unknown package/source/timing fields and unsafe composite URLs", async () => {
  const cases = [
    [() => {
      const value = entryDocument();
      value.package.local_hint = "latest";
      return value;
    }, /精确复核包字段无效|精确复核包\s+字段无效/],
    [() => {
      const value = entryDocument();
      value.package.reviewed_motion_bundle_sha256 = "6".repeat(64);
      return value;
    }, /P9 source 身份串线/],
    [() => {
      const value = entryDocument();
      value.package.project.composite_url = "https://example.invalid/character.png";
      return value;
    }, /composite URL 无效/],
    [() => {
      const value = entryDocument();
      value.candidate.source.latest_sha256 = "7".repeat(64);
      return value;
    }, /source\s+字段无效/],
    [() => {
      const value = entryDocument();
      value.candidate.timing.fps = 30;
      return value;
    }, /timing\s+字段无效/],
    [() => {
      const value = entryDocument();
      value.candidate.features[1].automatic_acceptance = true;
      return value;
    }, /Idle 特性\s+字段无效/],
    [() => {
      const value = entryDocument();
      value.preview.composite_url = "/api/projects/sample-b/composite";
      return value;
    }, /composite URL 与项目不一致/],
    [() => {
      const value = entryDocument();
      value.preview.duration_ticks += 1;
      return value;
    }, /候选时间不一致/],
    [() => {
      const value = entryDocument();
      value.history = {
        current_revision: 2, revision_count: 1,
        head_decision_sha256: DIGESTS.decision,
        items: [{
          revision: 2, decision_sha256: DIGESTS.decision,
          action: "reject", probe_status: "not_applicable", parameters: null,
        }],
      };
      return value;
    }, /current revision 与数量不一致|revision 不连续/],
    [() => {
      const value = entryDocument();
      value.status = "reviewed";
      return value;
    }, /状态与历史不一致/],
  ];
  for (const [build, pattern] of cases) {
    await assert.rejects(
      createIdleBehaviorReviewApi(async () => jsonResponse(200, build())).entry(DIGESTS.package),
      pattern,
    );
  }
});

test("API rejects malformed inventory and receipt identities", async () => {
  const invalidList = packageList();
  invalidList.packages[0].reviewed_motion_bundle_sha256 = DIGESTS.bundle;
  await assert.rejects(
    createIdleBehaviorReviewApi(async () => jsonResponse(200, invalidList)).list(),
    /摘要\s+字段无效/,
  );

  const api = createIdleBehaviorReviewApi(async () => jsonResponse(201,
    receiptDocument({ candidate_sha256: "7".repeat(64) })));
  await assert.rejects(api.submit(DIGESTS.package, {
    candidate_sha256: DIGESTS.candidate, base_revision: 0, action: "adjust",
  }), /回执与请求身份不一致/);
});

test("API exposes only the server public error message", async () => {
  const api = createIdleBehaviorReviewApi(async () => jsonResponse(409, {
    error: "stale_revision", message: "人工基线已变化",
  }));
  await assert.rejects(api.list(), (error) =>
    error instanceof IdleBehaviorReviewApiError
    && error.status === 409 && error.message === "人工基线已变化");
});

test("API loads one exact P10.2 canvas draft without file or SHA form input", async () => {
  const calls = [];
  const api = createIdleBehaviorReviewApi(async (url) => {
    calls.push(url);
    return jsonResponse(200, canvasAdjustmentDraftEntry());
  });
  const draft = await api.entryWithCanvasAdjustment(DIGESTS.package, ADJUSTMENT_SHA);
  assert.equal(draft.entry.history.current_revision, 1);
  assert.equal(draft.canvasAdjustment.candidateSha256, ADJUSTMENT_SHA);
  assert.equal(draft.proposal.gain.numerator, 4);
  assert.deepEqual(calls, [
    `/api/idle-behavior/review-packages/${DIGESTS.package}`
      + `/canvas-adjustment-drafts/${ADJUSTMENT_SHA}`,
  ]);
  await assert.rejects(
    api.entryWithCanvasAdjustment(DIGESTS.package, "../latest"), /ID 无效/,
  );
});
