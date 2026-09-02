import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  MOTION_INSTANCE_V3_V2_INTENT, createMotionInstanceV3V2Api,
} from "../modules/motion-instance-v3-v2-api.js";
import {
  INVENTORY, MOTION_INSTANCE_V3_V2_AUTHORITY, motionInstanceV3V2Href,
  motionInstanceV3V2Path, motionInstanceV3V2ResultPath,
  motionInstanceV3V2RunPath, motionInstanceV3V2RunsPath,
  normalizeMotionInstanceV3V2Entry, normalizeMotionInstanceV3V2Result,
} from "../modules/motion-instance-v3-v2-contract.js";
import {
  motionInstanceV3V2PollDelay, runMotionInstanceV3V2,
} from "../modules/motion-instance-v3-v2-state.js";
import {
  renderMotionInstanceV3V2Failure, renderMotionInstanceV3V2Result,
} from "../modules/motion-instance-v3-v2-view.js";

const JOB = "a".repeat(64);
const SAFETY = "b".repeat(64);
const DYNAMIC = "c".repeat(64);
const RUN = "d".repeat(64);
const PREVIOUS = "e".repeat(64);
const SHA = (character) => character.repeat(64);
const STAGES = [
  "exact_inputs", "motion_consumer_admission", "motion_instance_v3",
  "publication", "parent_exact_readback",
];

function run(status, options = {}) {
  const stage = options.stage || (status === "queued" ? "queued"
    : status === "running" ? "motion_instance_v3"
      : status === "completed" ? "completed" : "failed");
  const failed = status.startsWith("failed_");
  const attempt = options.attempt || 1;
  return {
    run_id: options.runId || RUN, status, stage,
    progress: { current: options.current || 0, total: options.total || 6 },
    failure_code: failed ? options.failureCode || "compile_failed" : null,
    event_count: options.eventCount || 2, head_event_sha256: SHA("f"),
    terminal: ["completed", "failed_retryable", "failed_terminal"].includes(status),
    retryable: status === "failed_retryable", attempt,
    previous_run_id: attempt === 1 ? null : PREVIOUS,
  };
}

function entry(status, options = {}) {
  return {
    ok: true, status, job_id: JOB, safety_run_id: SAFETY,
    dynamic_run_id: DYNAMIC,
    ...(status === "ready" ? {} : { run: run(status, options) }),
  };
}

function resultFixture() {
  return {
    ...entry("completed", { current: 1, total: 1 }),
    project_id: "seethrough_output", clip_id: "wave-left-v1",
    address: {
      motion_instance_v3_sha256: SHA("1"), bundle_sha256: SHA("2"),
    },
    run_sha256: SHA("3"), inventory: [...INVENTORY],
    authority: { ...MOTION_INSTANCE_V3_V2_AUTHORITY },
    release_gate: {
      status: "blocked", reason_codes: [
        "attachment_area_overlap_not_assessed",
        "dynamic_seam_safety_unproven",
        "full_attachment_boundary_raster_visual_regression_missing",
        "persistent_current_head_authority_not_granted",
        "publishable_timeline_not_emitted", "raster_visual_quality_unproven",
        "runtime_equivalence_unproven", "spine_adapter_not_emitted",
      ],
    },
    verification: { status: "passed", exact_readback: true },
    reused: false,
  };
}

test("three exact upstream IDs form routes without latest or manual sources", () => {
  const base = `/api/p10/runtime-capture/jobs/${JOB}/visual-review-v2/`
    + `safety-analysis-v2/runs/${SAFETY}/dynamic-seam-v2/runs/${DYNAMIC}`
    + "/motion-instance-v3-v2";
  assert.equal(motionInstanceV3V2Path(JOB, SAFETY, DYNAMIC), base);
  assert.equal(motionInstanceV3V2RunsPath(JOB, SAFETY, DYNAMIC), `${base}/runs`);
  assert.equal(motionInstanceV3V2RunPath(JOB, SAFETY, DYNAMIC, RUN),
    `${base}/runs/${RUN}`);
  assert.equal(motionInstanceV3V2ResultPath(JOB, SAFETY, DYNAMIC, RUN),
    `${base}/runs/${RUN}/result`);
  assert.equal(motionInstanceV3V2Href(JOB, SAFETY, DYNAMIC),
    `./motion-instance-v3-v2.html?job_id=${JOB}&safety_run_id=${SAFETY}`
    + `&dynamic_run_id=${DYNAMIC}`);
  assert.throws(() => motionInstanceV3V2Href("latest", SAFETY, DYNAMIC), /job ID/i);
  assert.throws(() => motionInstanceV3V2Href(JOB, SAFETY, "latest"), /dynamic_run_id/i);
});

test("API auto-start mutation is empty JSON with a dedicated intent", async () => {
  const calls = [];
  const api = createMotionInstanceV3V2Api(
    JOB, SAFETY, DYNAMIC, async (url, options) => {
      calls.push({ url, options });
      return response(entry(options.method === "POST" ? "queued" : "ready"));
    },
  );
  await api.inspect();
  await api.start();
  assert.equal(calls[0].options.method, undefined);
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.body, "{}");
  assert.equal(calls[1].options.credentials, "same-origin");
  assert.equal(calls[1].options.headers["X-Autospine-Intent"],
    MOTION_INSTANCE_V3_V2_INTENT);
});

test("all manager stages normalize and unknown stages fail closed", () => {
  for (const stage of STAGES) {
    const value = normalizeMotionInstanceV3V2Entry(
      entry("running", { stage, current: 2 }), JOB, SAFETY, DYNAMIC,
    );
    assert.equal(value.run.stage, stage);
  }
  assert.throws(() => normalizeMotionInstanceV3V2Entry(
    entry("running", { stage: "future_stage" }), JOB, SAFETY, DYNAMIC,
  ), /stage/);
});

test("first visit auto-starts once while terminal failures require explicit retry", async () => {
  const queue = [
    entry("running", { stage: "exact_inputs", current: 1 }),
    entry("running", { stage: "publication", current: 4 }),
    entry("completed", { current: 1, total: 1 }),
  ];
  let starts = 0;
  const sleeps = [];
  const api = {
    inspect: async () => entry("ready"),
    start: async () => { starts += 1; return entry("queued"); },
    status: async () => queue.shift(), result: async () => resultFixture(),
  };
  const outcome = await runMotionInstanceV3V2({
    api, jobId: JOB, safetyRunId: SAFETY, dynamicRunId: DYNAMIC,
    sleep: async (delay) => sleeps.push(delay),
  });
  assert.equal(outcome.kind, "completed");
  assert.equal(starts, 1);
  assert.deepEqual(sleeps, [350, 600, 900]);
  assert.equal(motionInstanceV3V2PollDelay(99), 3000);

  const failed = entry("failed_retryable", { attempt: 2 });
  const failureApi = {
    inspect: async () => failed,
    start: async () => { starts += 1; return failed; },
  };
  const before = starts;
  const stopped = await runMotionInstanceV3V2({
    api: failureApi, jobId: JOB, safetyRunId: SAFETY, dynamicRunId: DYNAMIC,
  });
  assert.equal(stopped.kind, "failed");
  assert.equal(starts, before);
});

test("completed result requires exact inventory, readback and bounded authority", () => {
  const value = normalizeMotionInstanceV3V2Result(
    resultFixture(), JOB, SAFETY, DYNAMIC, RUN,
  );
  assert.equal(value.inventory.length, 3);
  assert.equal(value.authority.motion_instance_v3_emitted, true);
  assert.equal(value.authority.spine_adapter_emitted, false);
  assert.equal(value.authority.runtime_equivalence, false);
  assert.equal(value.authority.raster_visual_quality, false);
  assert.equal(value.authority.release_authority, false);
  assert.equal(value.verification.exactReadback, true);

  const overclaim = resultFixture();
  overclaim.authority.spine_adapter_emitted = true;
  assert.throws(() => normalizeMotionInstanceV3V2Result(
    overclaim, JOB, SAFETY, DYNAMIC, RUN,
  ), /authority/);
  const wrongInventory = resultFixture();
  wrongInventory.inventory.reverse();
  assert.throws(() => normalizeMotionInstanceV3V2Result(
    wrongInventory, JOB, SAFETY, DYNAMIC, RUN,
  ), /inventory/);
  const unread = resultFixture();
  unread.verification.exact_readback = false;
  assert.throws(() => normalizeMotionInstanceV3V2Result(
    unread, JOB, SAFETY, DYNAMIC, RUN,
  ), /读回/);
  const leaked = resultFixture();
  leaked.output_path = "C:/secret";
  assert.throws(() => normalizeMotionInstanceV3V2Result(
    leaked, JOB, SAFETY, DYNAMIC, RUN,
  ), /路径/);
});

test("renderer emphasizes emission/readback and keeps downstream gates blocked", () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const value = normalizeMotionInstanceV3V2Result(
    resultFixture(), JOB, SAFETY, DYNAMIC, RUN,
  );
  renderMotionInstanceV3V2Result(elements, value);
  assert.equal(elements.motionResult.hidden, false);
  assert.match(elements.motionBadge.textContent, /已发出/);
  assert.equal(elements.motionFacts.children.length, 6);
  assert.equal(elements.motionInventory.children.length, 3);
  assert.equal(elements.motionScopes.children.length, 11);
  assert.equal(elements.motionScopes.children[6].children[1].textContent, "尚未生成");
  assert.match(elements.motionReleaseReasons.children[0].textContent, /附件重叠/);
  assert.match(elements.motionTechnical.textContent, /motion_instance_v3_sha256/);
  assert.doesNotMatch(elements.motionTechnical.textContent, /path/i);

  const failed = normalizeMotionInstanceV3V2Entry(
    entry("failed_retryable", { attempt: 2 }), JOB, SAFETY, DYNAMIC,
  ).run;
  renderMotionInstanceV3V2Failure(elements, failed, failed.failureCode);
  assert.equal(elements.retryMotionBtn.hidden, false);
  assert.match(elements.motionFailureHeading.textContent, /第 2 次/);
});

test("page and P10.5d handoff are nontechnical, accessible and responsive", async () => {
  const root = new URL("../", import.meta.url);
  const [html, css, view, app, seamHtml, seamApp] = await Promise.all([
    readFile(new URL("motion-instance-v3-v2.html", root), "utf8"),
    readFile(new URL("motion-instance-v3-v2.css", root), "utf8"),
    readFile(new URL("modules/motion-instance-v3-v2-view.js", root), "utf8"),
    readFile(new URL("modules/motion-instance-v3-v2-app.js", root), "utf8"),
    readFile(new URL("body-sway-dynamic-seam-v2.html", root), "utf8"),
    readFile(new URL("modules/body-sway-dynamic-seam-v2-app.js", root), "utf8"),
  ]);
  assert.match(html, /无需选择项目、文件或填写 SHA/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /Spine adapter、官方 Runtime、Raster 视觉质量/);
  assert.match(html, /<progress[^>]+id="motionProgress"/);
  assert.doesNotMatch(html, /type="file"|name="sha|id=".*Sha/i);
  assert.match(css, /@media \(max-width:\s*420px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.doesNotMatch(css, /overflow-x:\s*(auto|scroll)/);
  assert.match(app, /globalThis\.confirm/);
  assert.match(app, /全新的 P10\.6b v2 attempt/);
  assert.match(seamHtml, /id="continueMotionLink"/);
  assert.match(seamHtml, /继续生成 MotionInstance v3/);
  assert.match(seamApp, /motionInstanceV3V2Href/);
  assert.doesNotMatch(`${html}\n${view}\n${app}`,
    /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  for (const file of [
    "modules/motion-instance-v3-v2-contract.js",
    "modules/motion-instance-v3-v2-api.js",
    "modules/motion-instance-v3-v2-state.js",
    "modules/motion-instance-v3-v2-view.js",
    "modules/motion-instance-v3-v2-app.js",
  ]) {
    const source = await readFile(new URL(file, root), "utf8");
    assert.ok(source.split(/\r?\n/).length <= 301, `${file} exceeds 300 lines`);
  }
});

function response(payload) {
  return { ok: true, status: 200,
    headers: { get: () => "application/json" }, json: async () => payload };
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
  focus() { this.focused = true; }
}
class FakeDocument { createElement() { return new FakeElement(this); } }
function fakeElements(doc) {
  const ids = [
    "motionBadge", "motionStatus", "motionProgress", "motionProgressText",
    "motionAttempt", "motionAttemptState", "motionAttemptCode",
    "motionResult", "motionResultHeading", "motionFacts", "motionInventory",
    "motionScopes", "motionReleaseReasons", "motionTechnical",
    "motionFailure", "motionFailureHeading", "motionFailureMessage",
    "retryMotionBtn", "returnToSeamLink", "returnToSeamTop",
  ];
  return Object.fromEntries(ids.map((id) => [id, new FakeElement(doc)]));
}
