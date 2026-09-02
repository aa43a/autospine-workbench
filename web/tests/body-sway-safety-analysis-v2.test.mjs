import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  SAFETY_ANALYSIS_V2_INTENT, createBodySwaySafetyAnalysisV2Api,
} from "../modules/body-sway-safety-analysis-v2-api.js";
import {
  normalizeSafetyAnalysisEntry, normalizeSafetyAnalysisResult,
  safetyAnalysisV2Href, safetyAnalysisV2Path, safetyAnalysisV2ResultPath,
  safetyAnalysisV2RunPath, safetyAnalysisV2RunsPath,
} from "../modules/body-sway-safety-analysis-v2-contract.js";
import {
  runSafetyAnalysisV2, safetyAnalysisPollDelay,
} from "../modules/body-sway-safety-analysis-v2-state.js";
import {
  compactContinuousSegments, renderSafetyFailure, renderSafetyResult,
  safetyEvidenceTone,
} from "../modules/body-sway-safety-analysis-v2-view.js";

const JOB = "a".repeat(64);
const RUN = "b".repeat(64);
const SHA = (character) => character.repeat(64);

function run(status, current = 0, total = 4) {
  return {
    run_id: RUN, status, stage: status === "running" ? "continuous_validation" : status,
    progress: { current, total }, failure_code: null,
  };
}

function entry(status, current = 0) {
  return {
    ok: true, status, job_id: JOB,
    ...(status === "ready" ? {} : { run: run(status, current) }),
  };
}

function resultFixture() {
  const probes = Array.from({ length: 9 }, (_, numerator) => ({
    gain: { numerator, denominator: 8 }, status: "sampled_structural_passed",
    visual_review_status: numerator === 8
      ? "official_runtime_sampled_cases_approved" : "not_reviewed",
  }));
  return {
    ok: true, status: "completed", job_id: JOB,
    authority_scope: "compile_time_snapshot", run: run("completed", 4),
    project_id: "sample-a", clip_id: "wave-left-v1",
    amplitude: { sha256: SHA("c"), status: "candidate_only", probes },
    continuous: {
      sha256: SHA("d"), status: "indeterminate",
      summary: {
        segment_count: 2, certified_segment_count: 1,
        indeterminate_segment_count: 1,
      },
      segments: [
        {
          left_tick: 0, right_tick: 1,
          status: "continuous_structural_certified", reason_codes: [],
        },
        {
          left_tick: 1, right_tick: 2, status: "indeterminate",
          reason_codes: ["subdivision_box_budget_exhausted"],
        },
      ],
    },
    claims: {
      continuous_preview_model_structural_safety: false,
      uniform_gain_zero_to_reviewed_structurally_certified: false,
      official_runtime_continuous_equivalence: false, visual_gain_range: false,
      reviewed_seam_anchors: false, motion_instance_v3: false,
      publishable_timeline: false, release_authority: false,
    },
    release_gate: {
      status: "blocked", reason_codes: ["publishable_safe_range_unavailable"],
    },
    documents: {
      amplitude: {
        format: "autospine-body-sway-amplitude-envelope-candidate", format_version: 2,
        sha256: SHA("c"), size_bytes: 1024,
      },
      continuous: {
        format: "autospine-body-sway-continuous-preview-proof", format_version: 2,
        sha256: SHA("d"), size_bytes: 2048,
      },
    },
  };
}

test("job-only routes bind one exact P10.4b v2 run", () => {
  const base = `/api/p10/runtime-capture/jobs/${JOB}/visual-review-v2/safety-analysis-v2`;
  assert.equal(safetyAnalysisV2Path(JOB), base);
  assert.equal(safetyAnalysisV2RunsPath(JOB), `${base}/runs`);
  assert.equal(safetyAnalysisV2RunPath(JOB, RUN), `${base}/runs/${RUN}`);
  assert.equal(safetyAnalysisV2ResultPath(JOB, RUN), `${base}/runs/${RUN}/result`);
  assert.equal(safetyAnalysisV2Href(JOB), `./body-sway-safety-analysis-v2.html?job_id=${JOB}`);
  assert.throws(() => safetyAnalysisV2Href("latest"), /capture job ID/i);
});

test("API automatically starts with an empty body and explicit same-origin intent", async () => {
  const calls = [];
  const api = createBodySwaySafetyAnalysisV2Api(JOB, async (url, options) => {
    calls.push({ url, options });
    return response(entry(options.method === "POST" ? "queued" : "ready"));
  });
  await api.inspect();
  await api.start();
  assert.equal(calls[0].options.method, undefined);
  assert.equal(calls[1].url, safetyAnalysisV2RunsPath(JOB));
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.body, "{}");
  assert.equal(calls[1].options.credentials, "same-origin");
  assert.equal(calls[1].options.headers["X-Autospine-Intent"], SAFETY_ANALYSIS_V2_INTENT);
});

test("ready entry auto-starts, polls with bounded backoff, then reads one result", async () => {
  const states = [];
  const sleeps = [];
  const queue = [entry("running", 2), entry("completed", 4)];
  const api = {
    inspect: async () => entry("ready"), start: async () => entry("queued", 0),
    status: async () => queue.shift(), result: async () => resultFixture(),
  };
  const outcome = await runSafetyAnalysisV2({
    api, jobId: JOB, onState: ({ status }) => states.push(status),
    sleep: async (delay) => sleeps.push(delay),
  });
  assert.equal(outcome.kind, "completed");
  assert.equal(outcome.result.indeterminate, true);
  assert.deepEqual(states, ["ready", "queued", "running", "completed"]);
  assert.deepEqual(sleeps, [400, 700]);
  assert.equal(safetyAnalysisPollDelay(1000), 4000);
});

test("normalizers preserve indeterminate as a completed blocked-release result", () => {
  const value = normalizeSafetyAnalysisResult(resultFixture(), JOB, RUN);
  assert.equal(value.status, "completed");
  assert.equal(value.indeterminate, true);
  assert.equal(value.amplitude.probes.length, 9);
  assert.equal(value.continuous.summary.indeterminateSegmentCount, 1);
  assert.equal(value.receipts.amplitude.sha256, SHA("c"));
  assert.equal(value.receipts.continuous.sizeBytes, 2048);

  const unsafe = resultFixture();
  unsafe.release_gate.status = "open";
  assert.throws(() => normalizeSafetyAnalysisResult(unsafe, JOB, RUN), /不得解除发布门禁/);
  const crossedReceipt = resultFixture();
  crossedReceipt.documents.amplitude.sha256 = SHA("e");
  assert.throws(
    () => normalizeSafetyAnalysisResult(crossedReceipt, JOB, RUN),
    /结果身份不一致/,
  );
  assert.throws(
    () => normalizeSafetyAnalysisEntry({ ...entry("running"), status: "ready" }, JOB),
    /ready 状态/,
  );
});

test("strict result contract rejects cross-wired authority, stages, gains, and claims", () => {
  const missingJob = resultFixture();
  delete missingJob.job_id;
  assert.throws(() => normalizeSafetyAnalysisResult(missingJob, JOB, RUN), /job ID/);
  const wrongStage = entry("running", 1);
  wrongStage.run.stage = "completed";
  assert.throws(() => normalizeSafetyAnalysisEntry(wrongStage, JOB), /stage/);
  const wrongGain = resultFixture();
  wrongGain.amplitude.probes[3].gain.numerator = 4;
  assert.throws(() => normalizeSafetyAnalysisResult(wrongGain, JOB, RUN), /0\/8 到 8\/8/);
  const overclaim = resultFixture();
  overclaim.claims.publishable_timeline = true;
  assert.throws(() => normalizeSafetyAnalysisResult(overclaim, JOB, RUN), /权威范围/);
  const extraClaim = resultFixture();
  extraClaim.claims.runtime_safe = true;
  assert.throws(() => normalizeSafetyAnalysisResult(extraClaim, JOB, RUN), /权威范围/);
  const badReceipt = resultFixture();
  badReceipt.documents.continuous.format_version = 3;
  assert.throws(() => normalizeSafetyAnalysisResult(badReceipt, JOB, RUN), /身份不一致/);
  const wrongFormat = resultFixture();
  wrongFormat.documents.amplitude.format = "future-amplitude-document";
  assert.throws(() => normalizeSafetyAnalysisResult(wrongFormat, JOB, RUN), /身份不一致/);
  const unknownStatus = resultFixture();
  unknownStatus.amplitude.probes[0].status = "future_pass";
  assert.throws(() => normalizeSafetyAnalysisResult(unknownStatus, JOB, RUN), /status/);
  assert.equal(safetyEvidenceTone("future_unknown_status"), "blocked");
});

test("strict continuous contract rejects unknown reasons and inconsistent summaries", () => {
  const unknownReason = resultFixture();
  unknownReason.continuous.segments[1].reason_codes = ["future_reason"];
  assert.throws(() => normalizeSafetyAnalysisResult(unknownReason, JOB, RUN), /reason code/);
  const badSummary = resultFixture();
  badSummary.continuous.summary.certified_segment_count = 0;
  assert.throws(() => normalizeSafetyAnalysisResult(badSummary, JOB, RUN), /摘要/);
  const wrongVisual = resultFixture();
  wrongVisual.amplitude.probes[0].visual_review_status =
    "official_runtime_sampled_cases_approved";
  assert.throws(() => normalizeSafetyAnalysisResult(wrongVisual, JOB, RUN), /人工视觉范围/);
});

test("renderer shows four textual rails and treats indeterminate as warning, not failure", () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const value = normalizeSafetyAnalysisResult(resultFixture(), JOB, RUN);
  renderSafetyResult(elements, value);
  assert.equal(elements.analysisResult.hidden, false);
  assert.equal(elements.analysisFailure.hidden, true);
  assert.equal(elements.analysisBadge.dataset.tone, "warning");
  assert.match(elements.analysisBadge.textContent, /有未定区间/);
  assert.equal(elements.amplitudeRail.children.length, 9);
  assert.equal(elements.continuousRail.children.length, 2);
  assert.equal(elements.visualEvidenceRail.children.length, 1);
  assert.equal(elements.visualEvidenceRail.children[0].children[0].textContent, "100%");
  assert.equal(elements.publishableRail.children.length, 1);
  assert.match(elements.publishableRail.children[0].attributes["aria-label"], /不可用/);
  assert.match(elements.technicalReceipts.textContent, /"amplitude"/);
  assert.doesNotMatch(elements.technicalReceipts.textContent, /image_path|local_path/);
  assert.match(elements.resultHeading.textContent, /该 run 锁定的 Preview v2/);
  assert.match(elements.analysisFacts.children[2].children[1].textContent, /密封快照/);
  assert.equal(elements.dynamicSeamLink.attributes.href,
    `./body-sway-dynamic-seam-v2.html?job_id=${JOB}&safety_run_id=${RUN}`);
  assert.equal(elements.dynamicSeamLink.attributes["aria-disabled"], "false");
});

test("a failed immutable attempt offers a confirmed fresh attempt", async () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  renderSafetyFailure(elements, "analysis_validation_failed", true);
  assert.equal(elements.retryAnalysisBtn.hidden, false);
  assert.match(elements.failureHeading.textContent, /安全封存/);
  assert.match(elements.failureMessage.textContent, /不会覆盖本次回执/);

  const app = await readFile(new URL(
    "../modules/body-sway-safety-analysis-v2-app.js", import.meta.url,
  ), "utf8");
  assert.match(app, /globalThis\.confirm/);
  assert.match(app, /创建一次全新的 P10\.4b v2 分析/);
});

test("333 continuous segments collapse to bounded, accessible visual runs", () => {
  const certified = Array.from({ length: 333 }, (_, index) => ({
    leftTick: index, rightTick: index + 1,
    status: "continuous_structural_certified", reasonCodes: [],
  }));
  assert.equal(compactContinuousSegments(certified).runs.length, 1);
  const alternating = certified.map((segment, index) => index % 2 ? {
    ...segment, status: "indeterminate",
    reasonCodes: ["subdivision_depth_exhausted"],
  } : segment);
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const value = normalizeSafetyAnalysisResult(largeResultFixture(alternating), JOB, RUN);
  renderSafetyResult(elements, value);
  assert.equal(elements.continuousRail.children.length, 48);
  assert.match(elements.continuousRail.children.at(-1).attributes["aria-label"], /已折叠/);
});

test("page keeps the four evidence scopes explicit, responsive, and safe-DOM", async () => {
  const root = new URL("../", import.meta.url);
  const [html, css, view, app] = await Promise.all([
    readFile(new URL("body-sway-safety-analysis-v2.html", root), "utf8"),
    readFile(new URL("body-sway-safety-analysis-v2.css", root), "utf8"),
    readFile(new URL("modules/body-sway-safety-analysis-v2-view.js", root), "utf8"),
    readFile(new URL("modules/body-sway-safety-analysis-v2-app.js", root), "utf8"),
  ]);
  assert.match(html, /<progress[^>]+id="analysisProgress"/);
  assert.match(html, /九档离散结构点/);
  assert.match(html, /相邻时间连续区间/);
  assert.match(html, /现有人工复核只覆盖当前 100%/);
  assert.match(html, /当前不可用/);
  assert.match(html, /内容地址回执/);
  assert.match(html, /id="dynamicSeamLink"/);
  assert.match(html, /exact job_id 与 safety_run_id/);
  assert.match(view, /dynamicSeamV2Href/);
  assert.doesNotMatch(html, /canonical documents/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.doesNotMatch(`${html}\n${view}\n${app}`, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(css, /@media \(max-width:\s*420px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.doesNotMatch(css, /overflow-x:\s*(auto|scroll)/);
});

function response(payload) {
  return {
    ok: true, status: 200, headers: { get: () => "application/json" },
    json: async () => payload,
  };
}

function largeResultFixture(segments) {
  const value = resultFixture();
  value.continuous.segments = segments.map((segment) => ({
    left_tick: segment.leftTick, right_tick: segment.rightTick,
    status: segment.status, reason_codes: segment.reasonCodes,
  }));
  value.continuous.summary = {
    segment_count: segments.length,
    certified_segment_count: segments.filter(({ status }) =>
      status === "continuous_structural_certified").length,
    indeterminate_segment_count: segments.filter(({ status }) =>
      status === "indeterminate").length,
  };
  return value;
}

class FakeElement {
  constructor(ownerDocument) {
    this.ownerDocument = ownerDocument;
    this.dataset = {};
    this.attributes = {};
    this.children = [];
    this.hidden = false;
    this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() { this.focused = true; }
}

class FakeDocument {
  createElement() { return new FakeElement(this); }
}

function fakeElements(doc) {
  const ids = [
    "analysisBadge", "analysisStatus", "analysisProgress", "analysisProgressText",
    "analysisResult", "resultHeading", "analysisFacts", "amplitudeRail",
    "continuousRail", "visualEvidenceRail", "publishableRail", "releaseReasons",
    "amplitudeDigest", "continuousDigest", "technicalReceipts", "analysisFailure",
    "failureHeading", "failureMessage", "retryAnalysisBtn", "returnToAdmissionLink",
    "dynamicSeamLink",
  ];
  return Object.fromEntries(ids.map((id) => [id, new FakeElement(doc)]));
}
