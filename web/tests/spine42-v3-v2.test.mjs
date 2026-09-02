import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  SPINE42_V3_V2_INTENT, createSpine42V3V2Api,
} from "../modules/spine42-v3-v2-api.js";
import {
  SPINE42_V3_V2_AUTHORITY, SPINE42_V3_V2_INVENTORY,
  SPINE42_V3_V2_RELEASE_REASONS, normalizeSpine42V3V2Entry,
  normalizeSpine42V3V2Result, spine42V3V2Href, spine42V3V2Path,
  spine42V3V2ResultPath, spine42V3V2RunPath, spine42V3V2RunsPath,
} from "../modules/spine42-v3-v2-contract.js";
import {
  runSpine42V3V2, spine42V3V2PollDelay,
} from "../modules/spine42-v3-v2-state.js";
import {
  renderSpine42V3V2Failure, renderSpine42V3V2Result,
} from "../modules/spine42-v3-v2-view.js";

const JOB = "a".repeat(64);
const SAFETY = "b".repeat(64);
const DYNAMIC = "c".repeat(64);
const MOTION = "d".repeat(64);
const RUN = "e".repeat(64);
const PREVIOUS = "f".repeat(64);
const SHA = (character) => character.repeat(64);

function run(status, options = {}) {
  const stage = options.stage || (status === "queued" ? "queued"
    : status === "running" ? "spine_adapter"
      : status === "completed" ? "completed" : "failed");
  const failed = status.startsWith("failed_");
  const attempt = options.attempt || 1;
  return {
    run_id: options.runId || RUN, status, stage,
    progress: { current: options.current || 0, total: options.total || 1 },
    failure_code: failed ? options.failureCode || "compile_failed" : null,
    event_count: options.eventCount || 2, head_event_sha256: SHA("1"),
    terminal: ["completed", "failed_retryable", "failed_terminal"].includes(status),
    retryable: status === "failed_retryable", attempt,
    previous_run_id: attempt === 1 ? null : PREVIOUS,
  };
}

function entry(status, options = {}) {
  return {
    ok: true, status, job_id: JOB, safety_run_id: SAFETY,
    dynamic_run_id: DYNAMIC, motion_run_id: MOTION,
    ...(status === "ready" ? {} : { run: run(status, options) }),
  };
}

function resultFixture() {
  return {
    ...entry("completed", { current: 1, total: 1 }),
    project_id: "seethrough_output", clip_id: "wave-left-v1",
    address: { skeleton_json_sha256: SHA("2"), bundle_sha256: SHA("3") },
    inventory: [...SPINE42_V3_V2_INVENTORY],
    authority: { ...SPINE42_V3_V2_AUTHORITY },
    release_gate: {
      status: "blocked", reason_codes: [...SPINE42_V3_V2_RELEASE_REASONS],
    },
    verification: { status: "passed", exact_readback: true },
    reused: false,
  };
}

test("four exact upstream IDs form automatic routes and href", () => {
  const base = `/api/p10/runtime-capture/jobs/${JOB}/visual-review-v2/`
    + `safety-analysis-v2/runs/${SAFETY}/dynamic-seam-v2/runs/${DYNAMIC}`
    + `/motion-instance-v3-v2/runs/${MOTION}/spine42-v3-v2`;
  assert.equal(spine42V3V2Path(JOB, SAFETY, DYNAMIC, MOTION), base);
  assert.equal(spine42V3V2RunsPath(JOB, SAFETY, DYNAMIC, MOTION), `${base}/runs`);
  assert.equal(spine42V3V2RunPath(JOB, SAFETY, DYNAMIC, MOTION, RUN),
    `${base}/runs/${RUN}`);
  assert.equal(spine42V3V2ResultPath(JOB, SAFETY, DYNAMIC, MOTION, RUN),
    `${base}/runs/${RUN}/result`);
  assert.equal(spine42V3V2Href(JOB, SAFETY, DYNAMIC, MOTION),
    `./spine42-v3-v2.html?job_id=${JOB}&safety_run_id=${SAFETY}`
    + `&dynamic_run_id=${DYNAMIC}&motion_run_id=${MOTION}`);
  assert.throws(() => spine42V3V2Href(JOB, SAFETY, DYNAMIC, "latest"),
    /motion_run_id/);
});

test("auto-start sends empty JSON and dedicated same-origin intent", async () => {
  const calls = [];
  const api = createSpine42V3V2Api(
    JOB, SAFETY, DYNAMIC, MOTION, async (url, options) => {
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
    SPINE42_V3_V2_INTENT);
});

test("first visit auto-starts once and failed attempt waits for user", async () => {
  const queue = [
    entry("running", { stage: "exact_motion_instance" }),
    entry("running", { stage: "publication" }),
    entry("completed", { current: 1 }),
  ];
  let starts = 0;
  const api = {
    inspect: async () => entry("ready"),
    start: async () => { starts += 1; return entry("queued"); },
    status: async () => queue.shift(), result: async () => resultFixture(),
  };
  const outcome = await runSpine42V3V2({
    api, jobId: JOB, safetyRunId: SAFETY, dynamicRunId: DYNAMIC,
    motionRunId: MOTION, sleep: async () => {},
  });
  assert.equal(outcome.kind, "completed");
  assert.equal(starts, 1);
  assert.equal(spine42V3V2PollDelay(99), 3000);
  const failed = entry("failed_retryable", { attempt: 2 });
  const before = starts;
  const stopped = await runSpine42V3V2({
    api: { inspect: async () => failed,
      start: async () => { starts += 1; return failed; } },
    jobId: JOB, safetyRunId: SAFETY, dynamicRunId: DYNAMIC,
    motionRunId: MOTION,
  });
  assert.equal(stopped.kind, "failed");
  assert.equal(starts, before);
});

test("result fixes five files and refuses authority overclaim or paths", () => {
  const value = normalizeSpine42V3V2Result(
    resultFixture(), JOB, SAFETY, DYNAMIC, MOTION, RUN,
  );
  assert.equal(value.inventory.length, 5);
  assert.equal(value.authority.spine_adapter_emitted, true);
  assert.equal(value.authority.official_runtime_loaded, false);
  assert.equal(value.authority.release_authority, false);
  const overclaim = resultFixture();
  overclaim.authority.official_runtime_loaded = true;
  assert.throws(() => normalizeSpine42V3V2Result(
    overclaim, JOB, SAFETY, DYNAMIC, MOTION, RUN,
  ), /authority/);
  const leaked = resultFixture();
  leaked.output_path = "C:/secret";
  assert.throws(() => normalizeSpine42V3V2Result(
    leaked, JOB, SAFETY, DYNAMIC, MOTION, RUN,
  ), /路径/);
});

test("renderer reports adapter only and keeps runtime bridge blocked", () => {
  const doc = new FakeDocument();
  const elements = fakeElements(doc);
  const value = normalizeSpine42V3V2Result(
    resultFixture(), JOB, SAFETY, DYNAMIC, MOTION, RUN,
  );
  renderSpine42V3V2Result(elements, value);
  assert.equal(elements.spineResult.hidden, false);
  assert.match(elements.spineBadge.textContent, /adapter 已发出/);
  assert.equal(elements.spineInventory.children.length, 5);
  assert.equal(elements.spineScopes.children.length, 8);
  assert.match(elements.spineScopes.children[5].children[0].textContent,
    /P10\.7b v2/);
  assert.match(elements.spineScopes.children[6].children[1].textContent,
    /不会自动运行/);
  const failed = normalizeSpine42V3V2Entry(
    entry("failed_retryable", { attempt: 2 }), JOB, SAFETY, DYNAMIC, MOTION,
  ).run;
  renderSpine42V3V2Failure(elements, failed, failed.failureCode);
  assert.equal(elements.retrySpineBtn.hidden, false);
});

test("page is nontechnical and P10.6b handoff carries current motion run", async () => {
  const root = new URL("../", import.meta.url);
  const [html, view, app, motionHtml, motionApp] = await Promise.all([
    readFile(new URL("spine42-v3-v2.html", root), "utf8"),
    readFile(new URL("modules/spine42-v3-v2-view.js", root), "utf8"),
    readFile(new URL("modules/spine42-v3-v2-app.js", root), "utf8"),
    readFile(new URL("motion-instance-v3-v2.html", root), "utf8"),
    readFile(new URL("modules/motion-instance-v3-v2-app.js", root), "utf8"),
  ]);
  assert.match(html, /无需选择项目、文件或填写技术摘要/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /P10\.7b v2 Runtime source bridge 尚未进入/);
  assert.match(html, /不会自动运行外部或授权 Runtime/);
  assert.doesNotMatch(html, /type="file"|name="sha|id=".*Sha/i);
  assert.match(app, /globalThis\.confirm/);
  assert.doesNotMatch(`${html}\n${view}\n${app}`,
    /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(motionHtml, /id="continueSpineLink"/);
  assert.match(motionApp, /outcome\.result\.run\.runId/);
  for (const file of [
    "modules/spine42-v3-v2-contract.js", "modules/spine42-v3-v2-api.js",
    "modules/spine42-v3-v2-state.js", "modules/spine42-v3-v2-view.js",
    "modules/spine42-v3-v2-app.js",
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
    this.dataset = {}; this.children = []; this.hidden = false;
    this.disabled = false; this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  focus() { this.focused = true; }
}
class FakeDocument { createElement() { return new FakeElement(this); } }
function fakeElements(doc) {
  const ids = [
    "spineBadge", "spineStatus", "spineProgress", "spineProgressText",
    "spineAttempt", "spineAttemptState", "spineAttemptCode",
    "spineResult", "spineResultHeading", "spineFacts", "spineInventory",
    "spineScopes", "spineReleaseReasons", "spineFailure",
    "spineFailureHeading", "spineFailureMessage", "retrySpineBtn",
    "returnToMotionLink", "returnToMotionTop",
  ];
  return Object.fromEntries(ids.map((id) => [id, new FakeElement(doc)]));
}
