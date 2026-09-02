import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  DYNAMIC_SEAM_V2_INTENT, createBodySwayDynamicSeamV2Api,
} from "../modules/body-sway-dynamic-seam-v2-api.js";
import {
  dynamicSeamV2Href, dynamicSeamV2Path, dynamicSeamV2ResultPath,
  dynamicSeamV2RunPath, dynamicSeamV2RunsPath, normalizeDynamicSeamEntry,
  normalizeDynamicSeamResult,
} from "../modules/body-sway-dynamic-seam-v2-contract.js";
import {
  dynamicSeamPollDelay, runDynamicSeamV2,
} from "../modules/body-sway-dynamic-seam-v2-state.js";
import {
  renderDynamicSeamFailure, renderDynamicSeamResult,
} from "../modules/body-sway-dynamic-seam-v2-view.js";

const JOB = "a".repeat(64);
const SAFETY = "b".repeat(64);
const RUN = "c".repeat(64);
const PREVIOUS = "d".repeat(64);
const SHA = (character) => character.repeat(64);
const STAGES = [
  "compile_segments", "exact_inputs", "dynamic_seam_segments",
  "dynamic_seam_validation_segments", "publication", "parent_exact_readback",
];

function run(status, options = {}) {
  const stage = options.stage || (status === "queued" ? "queued"
    : status === "running" ? "dynamic_seam_segments"
      : status === "completed" ? "completed" : "failed");
  const failed = status.startsWith("failed_");
  const attempt = options.attempt || 1;
  return {
    run_id: options.runId || RUN, status, stage,
    progress: { current: options.current || 0, total: options.total || 6 },
    failure_code: failed ? options.failureCode || "compile_failed" : null,
    result: null, event_count: options.eventCount || 2,
    head_event_sha256: SHA("e"), terminal: [
      "completed", "failed_retryable", "failed_terminal",
    ].includes(status),
    retryable: status === "failed_retryable", attempt,
    previous_run_id: attempt === 1 ? null : PREVIOUS,
  };
}

function entry(status, options = {}) {
  return {
    ok: true, status, job_id: JOB, safety_run_id: SAFETY,
    ...(status === "ready" ? {} : { run: run(status, options) }),
  };
}

function resultFixture() {
  const ids = [
    "seam.leg_foot.left", "seam.leg_foot.right",
    "seam.pelvis_leg.left", "seam.pelvis_leg.right",
    "seam.torso_arm.left", "seam.torso_arm.right",
  ];
  const relationships = ids.map((relationship_id, index) => ({
    relationship_id, segment_count: 5,
    status: "finite_upper_bound",
    max_squared_anchor_residual_upper_px2: 4 + index,
    gap_proxy: {
      model: "anchor-residual-upper-bound-not-raster-gap",
      max_squared_upper_px2: 4 + index, raster_gap_claimed: false,
    },
    overlap: { status: "not_evaluated", raster_overlap_claimed: false },
    reason_codes: [],
  }));
  return {
    ok: true, status: "completed", job_id: JOB, safety_run_id: SAFETY,
    run: run("completed", { current: 1, total: 1 }),
    project_id: "seethrough_output", clip_id: "wave-left-v1",
    probe: {
      sha256: SHA("f"),
      status: "continuous_preview_v2_reviewed_anchor_residual_certified",
      summary: {
        segment_count: 5, certified_segment_count: 5,
        indeterminate_segment_count: 0, evaluated_box_count: 120,
        certified_terminal_box_count: 120,
        indeterminate_terminal_box_count: 0, maximum_depth_reached: 3,
        relationship_count: 6, anchor_pair_count: 24,
        segment_relationship_count: 30,
        finite_anchor_residual_relationship_count: 30,
        overlap_not_evaluated_relationship_count: 30,
        max_squared_anchor_residual_upper_px2: 9,
        threshold_squared_px2: 16,
        upstream_continuous_preview_model_status:
          "continuous_preview_model_structural_certified",
        all_anchor_residual_segments_certified: true, reason_codes: [],
      },
      relationships,
    },
    bundle: {
      source_set_sha256: SHA("1"), source_document_sha256: SHA("2"),
      probe_sha256: SHA("f"), bundle_sha256: SHA("3"),
    },
    claims: {
      reviewed_seam_anchor_set_v1_bound: true,
      continuous_preview_v2_anchor_residual_within_engineering_tolerance: true,
      structural_gap_proxy_within_engineering_tolerance: true,
      attachment_area_overlap_assessed: false, dynamic_seam_safety: false,
      official_runtime_equivalence: false, raster_gap_safety: false,
      raster_overlap_safety: false, visual_seam_quality: false,
      publishable_timeline: false, release_authority: false,
    },
    release_gate: {
      status: "blocked", reason_codes: [
        "attachment_overlap_not_modeled", "release_authority_unavailable",
      ],
    },
    permanent_current_authority_claimed: false,
    release_authority_granted: false,
  };
}

test("exact job and safety-run routes never accept latest or manual source fields", () => {
  const base = `/api/p10/runtime-capture/jobs/${JOB}/visual-review-v2/`
    + `safety-analysis-v2/runs/${SAFETY}/dynamic-seam-v2`;
  assert.equal(dynamicSeamV2Path(JOB, SAFETY), base);
  assert.equal(dynamicSeamV2RunsPath(JOB, SAFETY), `${base}/runs`);
  assert.equal(dynamicSeamV2RunPath(JOB, SAFETY, RUN), `${base}/runs/${RUN}`);
  assert.equal(dynamicSeamV2ResultPath(JOB, SAFETY, RUN), `${base}/runs/${RUN}/result`);
  assert.equal(dynamicSeamV2Href(JOB, SAFETY),
    `./body-sway-dynamic-seam-v2.html?job_id=${JOB}&safety_run_id=${SAFETY}`);
  assert.throws(() => dynamicSeamV2Href("latest", SAFETY), /job ID/i);
  assert.throws(() => dynamicSeamV2Href(JOB, "latest"), /safety_run_id/i);
});

test("API starts with empty JSON and the dedicated same-origin intent", async () => {
  const calls = [];
  const api = createBodySwayDynamicSeamV2Api(JOB, SAFETY, async (url, options) => {
    calls.push({ url, options });
    return response(entry(options.method === "POST" ? "queued" : "ready"));
  });
  await api.inspect();
  await api.start();
  assert.equal(calls[0].options.method, undefined);
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.body, "{}");
  assert.equal(calls[1].options.credentials, "same-origin");
  assert.equal(calls[1].options.headers["X-Autospine-Intent"], DYNAMIC_SEAM_V2_INTENT);
});

test("every backend progress stage is normalized and rendered as a running state", () => {
  for (const stage of STAGES) {
    const value = normalizeDynamicSeamEntry(entry("running", { stage, current: 2 }), JOB, SAFETY);
    assert.equal(value.run.stage, stage);
    assert.equal(value.run.progress.current, 2);
  }
  const future = entry("running", { stage: "future_unbounded_stage" });
  assert.throws(() => normalizeDynamicSeamEntry(future, JOB, SAFETY), /stage/);
});

test("first visit auto-starts once, polls, and reads one completed result", async () => {
  const states = [];
  const sleeps = [];
  const queue = [
    entry("running", { stage: "exact_inputs", current: 1 }),
    entry("running", { stage: "dynamic_seam_segments", current: 3 }),
    entry("completed", { current: 1, total: 1 }),
  ];
  let starts = 0;
  const api = {
    inspect: async () => entry("ready"),
    start: async () => { starts += 1; return entry("queued"); },
    status: async () => queue.shift(), result: async () => resultFixture(),
  };
  const outcome = await runDynamicSeamV2({
    api, jobId: JOB, safetyRunId: SAFETY,
    onState: ({ status }) => states.push(status),
    sleep: async (delay) => sleeps.push(delay),
  });
  assert.equal(outcome.kind, "completed");
  assert.equal(starts, 1);
  assert.deepEqual(states, ["ready", "queued", "running", "running", "completed"]);
  assert.deepEqual(sleeps, [400, 700, 1200]);
  assert.equal(dynamicSeamPollDelay(999), 4000);
});

test("reload preserves terminal attempt and never retries without confirmation", async () => {
  let starts = 0;
  const failed = entry("failed_retryable", { attempt: 2, failureCode: "worker_process_failed" });
  const api = {
    inspect: async () => failed,
    start: async () => { starts += 1; return failed; },
  };
  const outcome = await runDynamicSeamV2({ api, jobId: JOB, safetyRunId: SAFETY });
  assert.equal(outcome.kind, "failed");
  assert.equal(outcome.state.run.attempt, 2);
  assert.equal(starts, 0);
  await runDynamicSeamV2({ api, jobId: JOB, safetyRunId: SAFETY, startNew: true });
  assert.equal(starts, 1);
});

test("strict result keeps gap proxy separate from raster and overlap", () => {
  const value = normalizeDynamicSeamResult(resultFixture(), JOB, SAFETY, RUN);
  assert.equal(value.probe.relationships.length, 6);
  assert.equal(value.probe.relationships[0].gapProxy.maximumSquaredPx2, 4);
  assert.equal(value.probe.relationships[0].overlap.status, "not_evaluated");
  assert.equal(value.claims.dynamic_seam_safety, false);
  assert.equal(value.claims.visual_seam_quality, false);
  assert.equal(value.releaseGate.status, "blocked");

  const overlapClaim = resultFixture();
  overlapClaim.probe.relationships[0].overlap.raster_overlap_claimed = true;
  assert.throws(() => normalizeDynamicSeamResult(overlapClaim, JOB, SAFETY, RUN), /越权/);
  const release = resultFixture();
  release.release_authority_granted = true;
  assert.throws(() => normalizeDynamicSeamResult(release, JOB, SAFETY, RUN), /权威范围/);
  const crossed = resultFixture();
  crossed.bundle.probe_sha256 = SHA("4");
  assert.throws(() => normalizeDynamicSeamResult(crossed, JOB, SAFETY, RUN), /地址不一致/);
  const leaked = resultFixture();
  leaked.local_path = "C:/secret";
  assert.throws(() => normalizeDynamicSeamResult(leaked, JOB, SAFETY, RUN), /路径/);
});

test("renderer shows six relationship cards and six explicit evidence scopes", () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const value = normalizeDynamicSeamResult(resultFixture(), JOB, SAFETY, RUN);
  renderDynamicSeamResult(elements, value);
  assert.equal(elements.seamResult.hidden, false);
  assert.equal(elements.relationshipGrid.children.length, 6);
  assert.match(elements.relationshipGrid.children[0].attributes["aria-label"], /左踝/);
  assert.equal(elements.scopeGrid.children.length, 6);
  assert.equal(elements.scopeGrid.children[2].children[1].textContent, "未评估");
  assert.match(elements.scopeGrid.children[5].children[1].textContent, /阻塞/);
  assert.equal(elements.attemptNumber.textContent, "#1");
  assert.match(elements.technicalReceipts.textContent, /bundle_sha256/);
  assert.doesNotMatch(elements.technicalReceipts.textContent, /path/i);
  assert.equal(elements.motionHandoff.hidden, false);

  const unresolved = resultFixture();
  unresolved.probe.status = "indeterminate";
  unresolved.probe.summary.certified_segment_count = 4;
  unresolved.probe.summary.indeterminate_segment_count = 1;
  unresolved.claims.continuous_preview_v2_anchor_residual_within_engineering_tolerance = false;
  unresolved.claims.structural_gap_proxy_within_engineering_tolerance = false;
  renderDynamicSeamResult(
    elements, normalizeDynamicSeamResult(unresolved, JOB, SAFETY, RUN),
  );
  assert.equal(elements.motionHandoff.hidden, true);
});

test("only retryable failures expose retry, and app requires confirmation", async () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const retryable = normalizeDynamicSeamEntry(
    entry("failed_retryable", { attempt: 2 }), JOB, SAFETY,
  ).run;
  renderDynamicSeamFailure(elements, retryable, retryable.failureCode);
  assert.equal(elements.retrySeamBtn.hidden, false);
  assert.match(elements.failureHeading.textContent, /第 2 次/);
  const terminal = normalizeDynamicSeamEntry(
    entry("failed_terminal", { failureCode: "parent_validation_failed" }), JOB, SAFETY,
  ).run;
  renderDynamicSeamFailure(elements, terminal, terminal.failureCode);
  assert.equal(elements.retrySeamBtn.hidden, true);
  const app = await readFile(new URL(
    "../modules/body-sway-dynamic-seam-v2-app.js", import.meta.url,
  ), "utf8");
  assert.match(app, /globalThis\.confirm/);
  assert.match(app, /全新的 P10\.5d v2 attempt/);
});

test("page is nontechnical, responsive, keyboard-safe, and reduced-motion aware", async () => {
  const root = new URL("../", import.meta.url);
  const [html, css, view, app] = await Promise.all([
    readFile(new URL("body-sway-dynamic-seam-v2.html", root), "utf8"),
    readFile(new URL("body-sway-dynamic-seam-v2.css", root), "utf8"),
    readFile(new URL("modules/body-sway-dynamic-seam-v2-view.js", root), "utf8"),
    readFile(new URL("modules/body-sway-dynamic-seam-v2-app.js", root), "utf8"),
  ]);
  assert.match(html, /<progress[^>]+id="seamProgress"/);
  assert.match(html, /无需选择项目、文件或填写 SHA/);
  assert.match(html, /gap proxy 不是像素裂缝/);
  assert.match(html, /Overlap、Raster、官方 Runtime、视觉质量/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /href="\.\/workflow-hub\.html"/);
  assert.doesNotMatch(html, /type="file"|name="sha|id=".*Sha/i);
  assert.doesNotMatch(`${html}\n${view}\n${app}`,
    /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(css, /@media \(max-width:\s*420px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.doesNotMatch(css, /overflow-x:\s*(auto|scroll)/);
  for (const file of [
    "modules/body-sway-dynamic-seam-v2-contract.js",
    "modules/body-sway-dynamic-seam-v2-api.js",
    "modules/body-sway-dynamic-seam-v2-state.js",
    "modules/body-sway-dynamic-seam-v2-view.js",
    "modules/body-sway-dynamic-seam-v2-app.js",
  ]) {
    const source = await readFile(new URL(file, root), "utf8");
    assert.ok(source.split(/\r?\n/).length <= 301, `${file} exceeds 300 lines`);
  }
});

function response(payload) {
  return { ok: true, status: 200, headers: { get: () => "application/json" },
    json: async () => payload };
}

class FakeElement {
  constructor(ownerDocument) {
    this.ownerDocument = ownerDocument;
    this.dataset = {}; this.attributes = {}; this.children = [];
    this.hidden = false; this.disabled = false; this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() { this.focused = true; }
}
class FakeDocument { createElement() { return new FakeElement(this); } }
function fakeElements(doc) {
  const ids = [
    "seamBadge", "seamStatus", "seamProgress", "seamProgressText",
    "attemptNumber", "attemptState", "attemptCode", "seamResult",
    "resultHeading", "resultFacts", "relationshipGrid", "scopeGrid",
    "releaseReasons", "technicalReceipts", "seamFailure", "failureHeading",
    "failureMessage", "retrySeamBtn", "returnToSafetyLink",
    "continueMotionLink", "motionHandoff",
  ];
  return Object.fromEntries(ids.map((id) => [id, new FakeElement(doc)]));
}
