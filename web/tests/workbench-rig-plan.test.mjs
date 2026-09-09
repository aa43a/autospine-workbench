import assert from "node:assert/strict";
import test from "node:test";
import { createWorkbenchRigPlan, readRigPlan } from "../modules/workbench-rig-plan.js";
import { createRigPlanView } from "../modules/workbench-rig-plan-view.js";

const SHA = "1".repeat(64), INPUT = "2".repeat(64);
const tick = () => new Promise((resolve) => setImmediate(resolve));
const layer = (strategy = "secondary_motion", id = "sleeve") => ({ layer_id: id, name: id, strategy, existing_action: "pending",
  evidence: { component_count: 2, bone_alpha_samples: [{ bone_id: "forearm", opaque_samples: 14, samples: 21 }] },
  reason_codes: ["secondary_name_or_semantic_cue", "disconnected_alpha_does_not_authorize_split"], next_action: "review_roots_and_future_chain_requirements" });
const response = (status = "ready", input = INPUT) => ({ schema: "autospine.project-rig-plan-status/v1", project_id: "alice",
  input_identity_sha256: input, authority: "none", status, ...(status === "ready" ? { plan_sha256: SHA,
    plan: { schema: "autospine.rig-plan/v1", authority: "none", production_authorized: false, status: "needs_review", scope: ["sleeve"], layers: [layer()] } } : {}) });
function harness(handler) {
  const context = { projectId: "alice", resolvedSha: SHA }, requests = [], locks = []; let latest;
  const ui = createWorkbenchRigPlan(null, { context: () => context, busyChanged: (value) => locks.push(value),
    apiRequest: async (url, options) => { requests.push({ url, options }); return handler ? handler(options) : response(options.method ? "ready" : "missing"); } },
  { view: { render: (model) => { latest = model; } } });
  const sync = (extra = {}) => ui.sync({ inputIdentitySha: INPUT, preparationEditable: true, ...extra });
  return { ui, sync, context, requests, locks, model: () => latest };
}
test("planning reads once, requires explicit analysis, and never calls a decision endpoint", async () => {
  const h = harness(); h.sync(); await tick(); h.sync(); assert.equal(h.requests.length, 1);
  assert.equal(h.model().canAnalyze, true); assert.equal(h.model().layers.length, 0);
  await h.ui.analyze();
  assert.deepEqual(JSON.parse(h.requests[1].options.body), { expected_resolved_sha256: SHA, expected_input_sha256: INPUT });
  assert.deepEqual(h.locks, [true, false]); assert.equal(h.model().layers.length, 1);
  assert.ok(h.requests.every((r) => r.url.endsWith("/animated/rig-plan")));
});
test("unsaved changes and active work hide plans and prevent analysis", async () => {
  const h = harness(() => response()); h.sync(); await tick(); assert.equal(h.model().layers.length, 1);
  for (const flag of ["dirty", "saving", "loading"]) {
    h.context[flag] = true; h.sync(); await h.ui.analyze();
    assert.equal(h.model().canAnalyze, false); assert.equal(h.model().layers.length, 0); h.context[flag] = false;
  }
  h.sync({ preparationEditable: false }); await h.ui.analyze();
  assert.equal(h.requests.length, 1); assert.equal(h.model().canLocate, false);
});
test("late old-source responses cannot reappear after a project source changes", async () => {
  let resolve; const delayed = new Promise((done) => { resolve = done; });
  const h = harness((options) => options.method ? delayed : response("missing")); h.sync(); await tick();
  const running = h.ui.analyze(); h.sync({ inputIdentitySha: "3".repeat(64), preparationEditable: false });
  resolve(response()); await running;
  assert.equal(h.model().layers.length, 0); assert.equal(h.model().busy, false);
});
test("stale, approved, malformed and unsupported plans fail closed", () => {
  const context = { projectId: "alice" }; const bad = [];
  bad.push(response("ready", SHA), { ...response(), authority: "production" }, { ...response(), plan_sha256: "bad" });
  for (const edit of [(p) => { p.production_authorized = true; }, (p) => { p.layers[0].strategy = "auto_approved"; },
    (p) => { p.layers[0].evidence.bone_alpha_samples[0].opaque_samples = 30; }, (p) => { p.scope = []; }]) {
    const value = response(); edit(value.plan); bad.push(value);
  }
  for (const value of bad) assert.throws(() => readRigPlan(value, context, INPUT));
});
class Element extends EventTarget {
  constructor(tag) { super(); this.tagName = tag; this.children = []; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
}
const descendants = (node) => [node, ...node.children.flatMap(descendants)];
test("strategy filters only change presentation and locating never confirms a binding", () => {
  const located = [], view = createRigPlanView({ createElement: (tag) => new Element(tag) }, { locate: (row) => located.push(row) });
  const layers = [layer(), layer("rigid", "face")], before = structuredClone(layers);
  view.render({ visible: true, canAnalyze: true, canLocate: true, layers, message: "ready", busy: false });
  const filter = descendants(view.element).find((e) => e.tagName === "select"); filter.value = "secondary_motion"; filter.dispatchEvent(new Event("change"));
  const all = descendants(view.element);
  assert.ok(all.some((e) => e.textContent.includes?.("forearm 14/21")));
  assert.equal(all.filter((e) => e.textContent === "定位图层复核").length, 1);
  all.find((e) => e.textContent === "定位图层复核").dispatchEvent(new Event("click"));
  assert.deepEqual(located, [{ type: "binding", layer_id: "sleeve" }]); assert.deepEqual(layers, before);
  assert.ok(!all.some((e) => /批准|保存绑定/.test(e.textContent || "")));
});
