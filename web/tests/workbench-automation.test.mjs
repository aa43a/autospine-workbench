import assert from "node:assert/strict";
import test from "node:test";
import { createWorkbenchAutomation } from "../modules/workbench-automation-controller.js";
import { readOverview, readJob, reviewTarget } from "../modules/workbench-automation-contract.js";

const SHA = "1".repeat(64), NEXT = "2".repeat(64), JOB = `job-${"a".repeat(32)}`;
const tick = () => new Promise((resolve) => setImmediate(resolve));
function overview(context, ready = true, items = []) {
  const common = { project_id: context.projectId, authority: "none", profile: "production_review",
    source_addresses: { resolved_project_sha256: context.resolvedSha, layer_manifest_sha256: SHA, input_identity_sha256: SHA } };
  return { capabilities: { ...common, schema: "autospine.project-capabilities/v1", can_build_spine_preview: ready },
    review_queue: { ...common, schema: "autospine.review-queue/v1", items } };
}
function job(context, status, extras = {}) {
  return { schema: "autospine.pipeline-web-job/v1", project_id: context.projectId,
    authority: "none", job_id: JOB, status, target_version: "4.3.26",
    ...(!["pending", "running"].includes(status) ? { run: {
      project_id: context.projectId, authority: "none", status,
      source_addresses: { resolved_project_sha256: context.resolvedSha },
      steps: ["resolve-project", "build-region-rig", "compile-spine-preview"].map((id) => ({ id, status })),
    } } : {}), ...extras };
}
function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}
function harness(handler = null, clock = () => 0) {
  const context = { projectId: "sample", resolvedSha: SHA, dirty: false, saving: false,
    loading: false, layerIds: ["layer-1"], jointIds: ["ankle.left"] };
  const requests = [], models = [], selected = [], timers = new Map(), delays = [];
  let sequence = 0;
  const controller = createWorkbenchAutomation(null, {
    context: () => context,
    apiRequest: async (url, options = {}) => {
      requests.push({ url, options });
      return handler ? handler(url, options, context) : overview(context);
    },
    selectLayer: (id) => selected.push(["layer", id]), selectJoint: (id) => selected.push(["joint", id]),
  }, { view: { render: (model) => models.push(model) },
    now: clock,
    schedule: (callback, delay) => { const id = ++sequence; timers.set(id, callback); delays.push(delay); return id; },
    unschedule: (id) => timers.delete(id),
  });
  return { controller, context, requests, selected, timers, delays, model: () => models.at(-1),
    poll: async () => { const [id, callback] = timers.entries().next().value; timers.delete(id); callback(); await tick(); } };
}

test("preview binds saved project automatically, polls asynchronously and exposes verified download", async () => {
  const h = harness((url, options, context) => url.endsWith("/preview") ? job(context, "running")
    : url.includes("/jobs/") ? job(context, "succeeded") : overview(context));
  h.controller.sync(); await tick();
  assert.equal(h.model().canStart, true);
  await h.controller.start();
  const request = h.requests.find((row) => row.options.method === "POST");
  assert.equal(request.options.headers["X-Autospine-Intent"], "pipeline-preview");
  assert.deepEqual(JSON.parse(request.options.body), { profile: "production_review", expected_resolved_sha256: SHA, resume: true, target_version: "4.3.26" });
  assert.equal(h.model().active, true);
  assert.deepEqual(h.model().steps, []);
  await h.poll();
  assert.equal(h.model().downloadUrl, `/api/projects/sample/automation/jobs/${JOB}/download`);
  assert.equal(h.model().active, false);
  assert.equal(h.timers.size, 0);
  h.controller.dispose();
});

test("long builds explain polling, back off and stop for every terminal status", async () => {
  for (const terminal of ["succeeded", "needs_review", "blocked", "failed", "canceled"]) {
    let elapsed = 0, status = "pending";
    const h = harness((url, options, context) => url.endsWith("/preview") || url.includes("/jobs/")
      ? job(context, status) : overview(context), () => elapsed);
    h.controller.sync(); await tick(); await h.controller.start();
    assert.match(h.model().message, /正在排队.*0 秒/);
    assert.equal(h.delays.at(-1), 1200);
    elapsed = 12000; status = "running"; await h.poll();
    assert.equal(h.delays.at(-1), 2500);
    elapsed = 45000; await h.poll();
    assert.equal(h.delays.at(-1), 5000);
    assert.match(h.model().message, /45 秒.*状态查询不会重复构建/);
    assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 1);
    status = terminal; await h.poll();
    assert.equal(h.model().active, false);
    assert.equal(h.timers.size, 0);
    assert.equal(h.controller.canDownload(), terminal === "succeeded");
    h.controller.dispose();
  }
});

test("unsaved, saving and loading states block both button actions and download click guard", async () => {
  const h = harness((url, options, context) => url.endsWith("/preview") ? job(context, "succeeded") : overview(context));
  h.controller.sync(); await tick();
  for (const field of ["dirty", "saving", "loading"]) {
    h.context[field] = true; h.controller.sync();
    assert.equal(h.model().canStart, false);
    await h.controller.start();
    assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 0);
    h.context[field] = false;
  }
  await h.controller.start();
  assert.equal(h.controller.canDownload(), true);
  h.context.dirty = true;
  assert.equal(h.controller.canDownload(), false);
  h.controller.sync(); assert.equal(h.model().downloadUrl, null);
});

test("cross-project late overview and job replies never update the new project", async () => {
  const pending = deferred();
  const h = harness((url, options, context) => url.includes("/sample/") ? pending.promise : overview(context));
  h.controller.sync();
  h.context.projectId = "other"; h.controller.sync(); await tick();
  pending.resolve(overview({ projectId: "sample", resolvedSha: SHA }, false)); await tick();
  assert.equal(h.model().canStart, true);
  assert.match(h.model().message, /已就绪/);
  const late = deferred();
  const b = harness((url, options, context) => url.endsWith("/preview") ? late.promise : overview(context));
  b.controller.sync(); await tick();
  const start = b.controller.start();
  b.context.projectId = "other"; b.controller.sync(); await tick();
  late.resolve(job({ projectId: "sample", resolvedSha: SHA }, "succeeded")); await start;
  assert.equal(b.model().downloadUrl, null);
});

test("review completion auto resumes only an explicitly requested preview in the same project", async () => {
  let ready = false;
  const h = harness((url, options, context) => url.endsWith("/preview")
    ? job(context, ready ? "succeeded" : "needs_review") : overview(context, ready));
  h.controller.sync(); await tick();
  h.context.resolvedSha = NEXT; h.controller.sync(); await tick();
  assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 0);
  await h.controller.start();
  ready = true; h.context.resolvedSha = "3".repeat(64); h.context.saving = true;
  h.controller.sync(); await tick();
  assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 1);
  h.context.saving = false; h.controller.sync(); await tick();
  assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 2);
  assert.equal(h.controller.canDownload(), true);
});

test("cancel is intent-bound and a late running poll cannot overwrite the canceled result", async () => {
  const late = deferred();
  const h = harness((url, options, context) => url.endsWith("/preview") ? job(context, "running")
    : url.endsWith("/cancel") ? job(context, "canceled")
    : url.includes("/jobs/") ? late.promise : overview(context));
  h.controller.sync(); await tick(); await h.controller.start();
  const polling = h.poll(); await tick(); await h.controller.cancel();
  late.resolve(job(h.context, "running")); await polling; await tick();
  assert.equal(h.model().active, false);
  assert.match(h.model().message, /取消/);
  const request = h.requests.find((row) => row.url.endsWith("/cancel"));
  assert.equal(request.options.headers["X-Autospine-Intent"], "pipeline-preview");
  assert.equal(request.options.body, "{}");
});

test("polling failure is readable and refresh retries the job rather than silently leaving it running", async () => {
  let fail = true;
  const h = harness((url, options, context) => {
    if (url.endsWith("/preview")) return job(context, "running");
    if (url.includes("/jobs/")) { if (fail) throw new Error("C:/private/state"); return job(context, "succeeded"); }
    return overview(context);
  });
  h.controller.sync(); await tick(); await h.controller.start(); await h.poll();
  assert.match(h.model().message, /刷新/); assert.doesNotMatch(h.model().message, /private/);
  fail = false; await h.controller.refresh(); await h.poll();
  assert.equal(h.controller.canDownload(), true);
});

test("review items only select existing layers/joints and derived children locate their parent", async () => {
  const h = harness(); h.controller.sync(); await tick();
  h.controller.locate({ type: "joint", entity_id: "ankle.left" });
  h.controller.locate({ type: "split", entity_id: "child--left", evidence: [{ kind: "layer_image", url: "/api/projects/sample/layers/layer-1/image" }] });
  h.controller.locate({ type: "joint", entity_id: "missing" });
  assert.deepEqual(h.selected, [["joint", "ankle.left"], ["layer", "layer-1"]]);
  assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 0);
  assert.equal(reviewTarget({ type: "rig", entity_id: "sample" }, h.context), null);
});

test("overview rejects stale identity, crosswired sources and untrusted evidence URLs", () => {
  const context = { projectId: "sample", resolvedSha: SHA };
  assert.throws(() => readOverview(overview(context), { ...context, resolvedSha: NEXT }));
  const wrong = overview(context); wrong.review_queue.source_addresses = { ...wrong.review_queue.source_addresses, input_identity_sha256: NEXT };
  assert.throws(() => readOverview(wrong, context));
  const unsafe = overview(context, false, [{ type: "joint", entity_id: "ankle.left", evidence: [{ kind: "composite_image", url: "javascript:alert(1)" }] }]);
  assert.throws(() => readOverview(unsafe, context));
  assert.throws(() => readJob(job(context, "succeeded"), "other"));
  assert.throws(() => readJob(job(context, "succeeded", { authority: "release" }), "sample"));
});

test("default target is 4.3.26 and selecting 4.2 clears the previous downloadable job without editing the project", async () => {
  const h = harness((url, options, context) => url.endsWith("/preview")
    ? job(context, "succeeded", { target_version: JSON.parse(options.body).target_version }) : overview(context));
  h.controller.sync(); await tick();
  assert.equal(h.model().targetVersion, "4.3.26");
  await h.controller.start(); assert.equal(h.controller.canDownload(), true);
  const savedContext = { ...h.context };
  h.controller.setTarget("4.2");
  assert.equal(h.model().targetVersion, "4.2");
  assert.equal(h.model().downloadUrl, null);
  assert.deepEqual(h.model().steps, []);
  assert.deepEqual(h.context, savedContext);
  await tick();
  assert.equal(h.requests.filter((row) => row.options.method === "POST").length, 1);
  await h.controller.start();
  const requests = h.requests.filter((row) => row.options.method === "POST");
  assert.equal(JSON.parse(requests[1].options.body).target_version, "4.2");
  assert.equal(h.controller.canDownload(), true);
  assert.throws(() => h.controller.setTarget("4.4"));
});

test("switching targets ignores an in-flight job reply and stops polling the old target", async () => {
  const pending = deferred();
  const h = harness((url, options, context) => url.endsWith("/preview") ? pending.promise : overview(context));
  h.controller.sync(); await tick();
  const start = h.controller.start();
  h.controller.setTarget("4.2"); await tick();
  pending.resolve(job(h.context, "succeeded")); await start;
  assert.equal(h.model().downloadUrl, null);
  assert.deepEqual(h.model().steps, []);
  const active = harness((url, options, context) => url.endsWith("/preview") ? job(context, "running") : overview(context));
  active.controller.sync(); await tick(); await active.controller.start();
  assert.equal(active.timers.size, 1);
  active.controller.setTarget("4.2");
  assert.equal(active.timers.size, 0);
  assert.equal(active.model().active, false);
  assert.equal(active.model().canCancel, false);
});

test("legacy jobs without a target can download only with 4.2 selected, and mismatched explicit versions are rejected", async () => {
  const h = harness((url, options, context) => {
    if (!url.endsWith("/preview")) return overview(context);
    const result = job(context, "succeeded"); delete result.target_version; return result;
  });
  h.controller.sync(); await tick(); await h.controller.start();
  assert.equal(h.controller.canDownload(), false);
  assert.equal(h.model().downloadUrl, null);
  h.controller.setTarget("4.2"); await tick(); await h.controller.start();
  assert.equal(h.controller.canDownload(), true);
  const context = { projectId: "sample", resolvedSha: SHA };
  assert.throws(() => readJob(job(context, "succeeded"), "sample", null, "4.2"));
  assert.throws(() => readJob(job(context, "succeeded", { target_version: null }), "sample"));
  assert.throws(() => readJob(job(context, "succeeded", { target_version: "4.4" }), "sample"));
});
