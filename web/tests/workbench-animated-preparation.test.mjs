import assert from "node:assert/strict";
import test from "node:test";
import { createAnimatedPreparation, readPreparation } from "../modules/workbench-animated-preparation.js";

const SHA = "1".repeat(64), ID = `job-${"a".repeat(32)}`;
const tick = () => new Promise((resolve) => setImmediate(resolve));
function harness(overrides = {}) {
  const context = { projectId: "alice", resolvedSha: SHA }, requests = [], timers = new Map();
  let latest, completed = 0, index = 0;
  const capability = { schema: "autospine.input-preparation-overview/v1", authority: "none", project_id: "alice",
    resolved_project_sha256: SHA, status: "ready", can_prepare: true, source_registered: false, ...overrides.capability };
  const job = (status = "pending", registered = false) => ({ schema: "autospine.input-preparation-job/v1", authority: "none",
    project_id: "alice", expected_resolved_sha256: SHA, job_id: ID, status, source_registered: registered,
    progress: [{ id: "run-pose", status }] });
  const ui = createAnimatedPreparation(null, { context: () => context, completed: async () => { completed++; },
    apiRequest: async (url, request = {}) => {
      requests.push({ url, request });
      if (overrides.request) { const value = await overrides.request(url, request, job); if (value) return value; }
      if (url.endsWith("/cancel")) return job("canceled");
      if (url.includes("/jobs/")) return job("needs_review", true);
      return request.method === "POST" ? job() : capability;
    },
  }, { view: { render: (model) => { latest = model; } },
    schedule: (fn) => { timers.set(++index, fn); return index; }, unschedule: (id) => timers.delete(id) });
  const sync = (sourceMissing = true) => ui.sync({ sourceMissing, preparationEditable: true });
  return { ui, context, requests, timers, job, sync, model: () => latest, completed: () => completed };
}
test("source preparation requires explicit action and exact project identity; completion never approves points", async () => {
  const h = harness(); h.sync(); await tick();
  assert.equal(h.requests.length, 1); assert.equal(h.model().canStart, true);
  await h.ui.start();
  const post = h.requests.find((row) => row.request.method === "POST");
  assert.deepEqual(JSON.parse(post.request.body), { expected_resolved_sha256: SHA });
  assert.equal(post.request.headers["X-Autospine-Intent"], "pipeline-preview");
  assert.equal(h.timers.size, 1); await h.ui.refresh();
  assert.equal(h.completed(), 1); assert.equal(h.timers.size, 0);
  assert.equal(h.requests.filter((row) => row.request.method === "POST").length, 1);
  assert.ok(h.requests.every((row) => !/\/review|\/joints|\/preview/.test(row.url)));
});
test("runner unavailable, unsaved changes and registered sources cannot start inference", async () => {
  for (const status of ["runner_unavailable", "unsupported", "already_prepared"]) {
    const h = harness({ capability: { status, can_prepare: false } }); h.sync(); await tick(); await h.ui.start();
    assert.equal(h.model().canStart, false); assert.equal(h.requests.length, 1);
  }
  const h = harness(); h.sync(); await tick(); h.context.dirty = true; h.sync(); await h.ui.start();
  assert.equal(h.requests.length, 1); h.sync(false); assert.equal(h.model().visible, false);
});
test("late preparation completion cannot populate a different project", async () => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const h = harness({ request: async (_url, request) => request.method === "POST" ? pending : null });
  h.sync(); await tick(); const running = h.ui.start();
  h.context.projectId = "crino"; h.sync(false); resolve(h.job("needs_review", true)); await running;
  assert.equal(h.completed(), 0); assert.equal(h.timers.size, 0); assert.equal(h.model().visible, false);
});
test("cancel invalidates in-flight polling and does not deliver a late registered result", async () => {
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const h = harness({ request: async (url) => url.includes("/jobs/") && !url.endsWith("/cancel") ? pending : null });
  h.sync(); await tick(); await h.ui.start(); const poll = h.ui.refresh();
  await h.ui.cancel(); resolve(h.job("needs_review", true)); await poll;
  assert.equal(h.completed(), 0); assert.equal(h.timers.size, 0); assert.match(h.model().message, /取消/);
});
test("malformed and stale job identities fail closed", () => {
  const h = harness(); const value = h.job();
  assert.throws(() => readPreparation({ ...value, expected_resolved_sha256: "2".repeat(64) }, h.context));
  assert.throws(() => readPreparation({ ...value, job_id: "../../private" }, h.context));
  assert.throws(() => readPreparation({ ...value, progress: [{ id: "run-pose", status: "approved" }] }, h.context));
  assert.throws(() => readPreparation({ ...value, authority: "production" }, h.context));
});
