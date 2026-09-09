import assert from "node:assert/strict";
import test from "node:test";
import { createWorkbenchAnimated } from "../modules/workbench-animated-controller.js";
import { readAnimatedJob, readAnimatedOverview, animatedLayerTarget } from "../modules/workbench-animated-contract.js";
import { readPlayback, samplePlayback } from "../modules/workbench-animated-player.js";
import { expandedCanvasWidth } from "../modules/workbench-animated-expand.js";

const SHA = "1".repeat(64), JOB = `job-${"a".repeat(32)}`, tick = () => new Promise((resolve) => setImmediate(resolve));
const overview = (ctx) => ({ schema: "autospine.animated-overview/v1", project_id: ctx.projectId,
  resolved_project_sha256: ctx.resolvedSha, input_identity_sha256: SHA, can_build: true,
  clips: [{ id: "wave", label: "挥手" }, { id: "idle", label: "待机" }], review_items: [],
  binding_review: { bindings: [], records: [] } });
const result = (ctx, status, preview = false) => ({ schema: "autospine.animated-web-job/v1", authority: "none", job_id: JOB, project_id: ctx.projectId, status,
  ...(!["running", "pending"].includes(status) ? { run: { schema: "autospine.animated-pipeline-run/v1",
    run_id: "run-test", status, preview_available: preview, project_id: ctx.projectId,
    source_addresses: { resolved_project_sha256: ctx.resolvedSha }, steps: [], review_items: [] } } : {}) });
function harness(handler) {
  const context = { projectId: "sample", resolvedSha: SHA, layerIds: [] }, models = [], calls = [], timers = new Map();
  let count = 0, clock = 0;
  const controller = createWorkbenchAnimated(null, { context: () => context,
    apiRequest: async (url, options = {}) => { calls.push({ url, options }); return handler(url, options, context); },
  }, { view: { render: (model) => models.push(model) }, now: () => clock,
    schedule: (fn, delay) => { const id = ++count; timers.set(id, { fn, delay }); return id; }, unschedule: (id) => timers.delete(id) });
  return { controller, context, calls, timers, model: () => models.at(-1), time: (v) => { clock = v; },
    poll: async () => { const [id, { fn }] = timers.entries().next().value; timers.delete(id); fn(); await tick(); } };
}
test("animated candidate with needs_review downloads without automatic adoption and stops polling", async () => {
  const h = harness((url, opts, ctx) => url.endsWith("/preview") ? result(ctx, "running")
    : url.includes("/jobs/") ? result(ctx, "needs_review", true) : overview(ctx));
  h.controller.sync(); await tick(); await h.controller.start(); await h.poll();
  assert.equal(h.timers.size, 0); assert.equal(h.model().active, false);
  assert.match(h.model().downloadUrl, /animated\/jobs\/job-.+\/download$/);
  assert.match(h.model().playbackUrl, /files\/playback.json$/);
  const post = h.calls.filter((call) => call.options.method === "POST");
  assert.equal(post.length, 1);
  assert.deepEqual(JSON.parse(post[0].options.body), { expected_resolved_sha256: SHA, clip: "wave", resume: true });
  assert.equal(post[0].options.headers["X-Autospine-Intent"], "pipeline-preview");
});
test("polling backs off and every terminal state stops; only usable candidates download", async () => {
  for (const status of ["succeeded", "needs_review", "blocked", "failed", "canceled"]) {
    let next = "running";
    const h = harness((url, opts, ctx) => /preview$|\/jobs\//.test(url) ? result(ctx, next, true) : overview(ctx));
    h.controller.sync(); await tick(); await h.controller.start();
    h.time(31000); await h.poll(); assert.equal([...h.timers.values()][0].delay, 5000);
    next = status; await h.poll(); assert.equal(h.timers.size, 0);
    assert.equal(h.controller.canDownload(), ["succeeded", "needs_review"].includes(status));
  }
});
test("saved source change clears stale playback and resumes an explicitly waiting run", async () => {
  const h = harness((url, opts, ctx) => url.endsWith("/preview") ? result(ctx, "needs_review", true) : overview(ctx));
  h.controller.sync(); await tick(); await h.controller.start();
  h.context.resolvedSha = "2".repeat(64); h.context.saving = true; h.controller.sync(); await tick();
  assert.equal(h.model().playbackUrl, null); assert.equal(h.model().downloadUrl, null);
  assert.equal(h.calls.filter((call) => call.options.method === "POST").length, 1);
  h.context.saving = false; h.controller.sync(); await tick();
  assert.equal(h.calls.filter((call) => call.options.method === "POST").length, 2);
});
test("switching project or clip never carries previous playback forward", async () => {
  const h = harness((url, opts, ctx) => url.endsWith("/preview") ? result(ctx, "succeeded", true) : overview(ctx));
  h.controller.sync(); await tick(); await h.controller.start(); h.controller.setClip("idle");
  assert.equal(h.model().downloadUrl, null); await h.controller.start();
  h.context.projectId = "other"; h.controller.sync(); await tick();
  assert.equal(h.model().playbackUrl, null);
  assert.equal(h.calls.filter((call) => call.options.method === "POST").length, 2);
});
test("a concurrent binding-source change cannot expose an unrefreshed animation", async () => {
  const h = harness((url, opts, ctx) => {
    if (!url.endsWith("/preview")) return overview(ctx);
    const job = result(ctx, "needs_review", true);
    job.run.source_addresses.input_identity_sha256 = "2".repeat(64);
    return job;
  });
  h.controller.sync(); await tick(); await h.controller.start();
  assert.equal(h.model().downloadUrl, null); assert.equal(h.model().playbackUrl, null);
  assert.match(h.model().message, /变化/);
});
test("cancel invalidates a running poll and never restores a canceled preview", async () => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const h = harness((url, opts, ctx) => url.endsWith("/preview") ? result(ctx, "running")
    : url.endsWith("/cancel") ? result(ctx, "canceled") : url.includes("/jobs/") ? pending : overview(ctx));
  h.controller.sync(); await tick(); await h.controller.start(); const polling = h.poll();
  await h.controller.cancel(); resolve(result(h.context, "running")); await polling;
  assert.equal(h.timers.size, 0); assert.equal(h.model().active, false); assert.equal(h.model().downloadUrl, null);
});
test("explicit binding save submits complete records with both source identities then rebuilds", async () => {
  const h = harness((url, opts, ctx) => url.endsWith("/review") ? { ok: true }
    : url.endsWith("/preview") ? result(ctx, "needs_review", true) : overview(ctx));
  h.controller.sync(); await tick();
  const records = [{ layer_id: "layer-a", action: "pending", option_id: null, notes: "" }];
  await h.controller.saveReview(records);
  const posts = h.calls.filter((call) => call.options.method === "POST");
  assert.equal(posts.length, 2); assert.ok(posts[0].url.endsWith("/review"));
  assert.deepEqual(JSON.parse(posts[0].options.body), { expected_resolved_sha256: SHA, expected_input_sha256: SHA, records });
  assert.ok(posts[1].url.endsWith("/preview"));
});
test("untrusted job and overview cannot cross source, project, run or authority boundaries", () => {
  const ctx = { projectId: "sample", resolvedSha: SHA };
  const job = result(ctx, "succeeded", true);
  assert.throws(() => readAnimatedJob(job, { ...ctx, projectId: "other" }));
  assert.throws(() => readAnimatedJob(job, { ...ctx, resolvedSha: "2".repeat(64) }));
  assert.throws(() => readAnimatedJob({ ...job, run: { ...job.run, authority: "release" } }, ctx));
  assert.throws(() => readAnimatedOverview(overview(ctx), { ...ctx, resolvedSha: "2".repeat(64) }));
  const actual = overview(ctx);
  actual.binding_review.bindings.push({ layer_id: "layer-003", options: [{ id: "mesh_chain:r:arm", mode: "mesh_chain", bone_ids: ["upperarm_r", "forearm_r", "hand_r"] }] });
  assert.equal(readAnimatedOverview(actual, ctx).binding_review.bindings[0].options[0].id, "mesh_chain:r:arm");
});
test("benchmark source-layer IDs locate only one matching workbench layer", () => {
  const context = { layerIds: ["layer-003-handwear-r", "layer-004-handwear-l"] };
  assert.equal(animatedLayerTarget("layer-003", context), "layer-003-handwear-r");
  assert.equal(animatedLayerTarget("layer-003--left", context), "layer-003-handwear-r");
  assert.equal(animatedLayerTarget("layer-009", context), null);
  assert.equal(animatedLayerTarget("layer-003", { layerIds: ["layer-003-a", "layer-003-b"] }), null);
});
function playback() {
  return { canvas: [100, 100], fps: 30, duration: 1,
    layers: [{ id: "arm", image: "images/arm.png", uvs: [[0, 0], [1, 0], [0, 1]], triangles: [[0, 1, 2]] }],
    frames: [{ time: 0, vertices: { arm: [[0, 0], [10, 0], [0, 10]] } },
      { time: 1, vertices: { arm: [[10, 0], [20, 0], [10, 10]] } }] };
}
test("CPU playback interpolates canvas vertices and rejects invalid topology or asset paths", () => {
  const data = readPlayback(playback());
  assert.deepEqual(samplePlayback(data, 0.5).arm, [[5, 0], [15, 0], [5, 10]]);
  for (const mutate of [
    (v) => { v.layers[0].image = "images/../../private.png"; },
    (v) => { v.layers[0].triangles[0][2] = 9; },
    (v) => { v.frames[1].vertices.arm[1][1] = NaN; },
    (v) => { v.frames[1].time = 0; },
  ]) { const invalid = playback(); mutate(invalid); assert.throws(() => readPlayback(invalid)); }
});
test("expanded canvas fits both viewport axes while preserving source aspect ratio", () => {
  const canvas = { width: 1000, height: 1500 }, viewport = { width: 1200, height: 900 };
  const width = expandedCanvasWidth(canvas, viewport);
  assert.equal(width, 390); assert.equal(width * canvas.height / canvas.width, viewport.height * 0.65);
  assert.ok(expandedCanvasWidth({ width: 2000, height: 1000 }, { width: 500, height: 900 }) <= 436);
});
