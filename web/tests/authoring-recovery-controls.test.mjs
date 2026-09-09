import test from "node:test";
import assert from "node:assert/strict";
import { removeLayerBoneOverride, installAuthoringRecoveryControls } from "../modules/authoring-recovery-controls.js";

test("undo affects only selected layer candidate bone, preserving all other authored data", () => {
  const overrides = { neck: { candidate_bone: "neck-head", pivot_xy: [660, 274], side: "center" }, hair: { visible: true } };
  assert.equal(removeLayerBoneOverride(overrides, "neck"), true);
  assert.deepEqual(overrides, { neck: { pivot_xy: [660, 274], side: "center" }, hair: { visible: true } });
  assert.equal(removeLayerBoneOverride(overrides, "neck"), false);
});
test("same-value coordinates can be explicitly confirmed without change event; loading blocks clicks", () => {
  const nodes = [], make = () => { const node = { events: {}, before() {}, after() {}, addEventListener(k, fn) { this.events[k] = fn; } }; nodes.push(node); return node; };
  const dom = { resetJointBtn: make(), candidateBoneSelect: { closest: () => ({ parentNode: make() }) }, jointXInput: make(), jointYInput: make() };
  let calls = 0, busy = false;
  installAuthoringRecoveryControls({ createElement: make }, dom, { confirmJoint: () => calls++, busy: () => busy });
  const button = nodes.find(n => n.textContent === "确认当前关节坐标");
  assert.equal(calls, 0); button.events.click(); assert.equal(calls, 1);
  busy = true; button.events.click(); assert.equal(calls, 1);
});
