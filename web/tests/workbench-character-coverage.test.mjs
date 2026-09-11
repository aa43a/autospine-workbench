import test from "node:test";
import assert from "node:assert/strict";
import { createCharacterCoverage } from "../modules/workbench-character-coverage.js";

const document = { createElement(tag) { return {
  tag, children: [], events: {}, append(...nodes) { this.children.push(...nodes); },
  replaceChildren(...nodes) { this.children = nodes; }, setAttribute() {},
  addEventListener(name, handler) { this.events[name] = handler; },
}; } };
const result = { document: { schema: "autospine.character-coverage/v1",
  summary: { source_layers: 1, output_regions: 2 },
  layers: [{ layer_id: "legs", name: "双腿", state: "partial",
    regions: [{ region_id: "left", state: "weighted_candidate" }, { region_id: "rest", state: "static_reference" }],
    reason_codes: ["residual_binding_required"] }],
} };
const response = { ok: true, json: async () => result };

test("coverage shows partial binding, locates source and avoids repeat requests", async () => {
  const calls = [], selected = [];
  const view = createCharacterCoverage(document, value => selected.push(value), async url => { calls.push(url); return response; });
  await view.load("/jobs/one/download"); await view.load("/jobs/one/download");
  assert.deepEqual(calls, ["/jobs/one/coverage"]);
  const row = view.element.children[2].children[0];
  assert.match(row.children[0].textContent, /部分处理/);
  assert.match(row.children[1].textContent, /静态参考/);
  row.children[0].events.click(); assert.equal(selected[0].layer_id, "legs");
});

test("switching project discards late response and hides stale coverage", async () => {
  let release;
  const view = createCharacterCoverage(document, () => {}, () => new Promise(resolve => { release = resolve; }));
  const pending = view.load("/jobs/old/download");
  await view.load(null); release(response); await pending;
  assert.equal(view.element.hidden, true);
  assert.equal(view.element.children[2].children.length, 0);
});

test("failed coverage can retry without claiming completion", async () => {
  let attempts = 0;
  const view = createCharacterCoverage(document, () => {}, async () => ++attempts === 1 ? { ok: false } : response);
  await view.load("/jobs/one/download");
  assert.match(view.element.children[1].textContent, /暂不可用/);
  await view.load("/jobs/one/download"); assert.equal(attempts, 2);
  assert.match(view.element.children[1].textContent, /不计作完成绑定/);
});
