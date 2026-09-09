import assert from "node:assert/strict";
import test from "node:test";
import { createAnimatedBindings } from "../modules/workbench-animated-bindings.js";

class Element extends EventTarget {
  constructor(tag) { super(); this.tagName = tag; this.children = []; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  scrollIntoView() { this.scrolled = true; }
}
const descendants = (node) => [node, ...node.children.flatMap(descendants)];
function harness() {
  const saves = [], dirty = [], doc = { createElement: (tag) => new Element(tag) };
  const view = createAnimatedBindings(doc, { save: (rows) => saves.push(rows), changed: (value) => dirty.push(value), locate() {} });
  const bindingReview = { bindings: [{ layer_id: "sleeve", suggested_option_id: "three-bones",
    options: [{ id: "three-bones", mode: "weighted_mesh", bone_ids: ["upperarm", "forearm", "hand"] }] }],
    records: [{ layer_id: "sleeve", action: "pending", option_id: null, notes: "" },
      { layer_id: "other", action: "pending", option_id: null, notes: "preserved" }] };
  view.render({ bindingReview, reviewIdentity: "first", canReview: true });
  const find = (label) => descendants(view.element).find((node) => node.attributes["aria-label"] === label || node.textContent === label);
  const change = (label, value, event = "change") => { const node = find(label); node.value = value; node.dispatchEvent(new Event(event)); };
  return { view, bindingReview, saves, dirty, find, change };
}
test("suggested binding stays pending until explicit selection and save; all records survive", () => {
  const h = harness();
  assert.equal(h.find("sleeve 处理方式").value, "pending"); assert.equal(h.find("sleeve 绑定方案").value, "");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click")); assert.equal(h.saves.length, 0);
  h.change("sleeve 绑定方案", "three-bones");
  assert.equal(h.find("sleeve 处理方式").value, "bind"); assert.equal(h.saves.length, 0);
  h.view.render({ bindingReview: h.bindingReview, reviewIdentity: "first", canReview: true });
  assert.equal(h.find("sleeve 绑定方案").value, "three-bones");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click"));
  assert.equal(h.saves[0][0].action, "bind"); assert.deepEqual(h.saves[0][1], h.bindingReview.records[1]);
  assert.equal(h.bindingReview.records[0].action, "pending");
});
test("split requires notes; undo restores saved decisions without API requests", () => {
  const h = harness(); h.change("sleeve 处理方式", "requires_split");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click")); assert.equal(h.saves.length, 0);
  h.change("sleeve 复核说明", "包含左右两侧", "input");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click")); assert.equal(h.saves[0][0].notes, "包含左右两侧");
  h.find("撤销未保存修改").dispatchEvent(new Event("click"));
  assert.equal(h.find("sleeve 处理方式").value, "pending"); assert.equal(h.dirty.at(-1), false);
});
test("project switch clears local changes and read-only state blocks save", () => {
  const h = harness(); h.change("sleeve 绑定方案", "three-bones");
  h.view.render({ bindingReview: h.bindingReview, reviewIdentity: "second", canReview: false });
  assert.equal(h.find("sleeve 处理方式").value, "pending");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click")); assert.equal(h.saves.length, 0);
});

test("planner navigation opens and focuses a different category without losing unsaved records", () => {
  const h = harness();
  h.bindingReview.bindings.push({ layer_id: "face", suggested_option_id: "rigid:head",
    options: [{ id: "rigid:head", mode: "rigid", bone_ids: ["head"] }] });
  h.bindingReview.records.push({ layer_id: "face", action: "pending", option_id: null, notes: "keep" });
  h.view.render({ bindingReview: h.bindingReview, reviewIdentity: "navigation", canReview: true });
  h.change("sleeve 绑定方案", "three-bones"); h.change("sleeve 复核说明", "local choice", "input");
  h.view.element.open = false;
  const notifications = h.dirty.length;
  assert.equal(h.view.focusLayer("face"), true);
  assert.equal(h.view.element.open, true);
  assert.equal(h.find("face 处理方式").focused, true);
  assert.equal(h.find("sleeve 处理方式"), undefined);
  assert.equal(h.dirty.length, notifications); assert.equal(h.saves.length, 0);
  assert.equal(h.view.focusLayer("missing"), false);
  assert.equal(h.view.focusLayer("sleeve"), true);
  assert.equal(h.find("sleeve 绑定方案").value, "three-bones");
  assert.equal(h.find("sleeve 复核说明").value, "local choice");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click"));
  assert.equal(h.saves[0].length, 3);
  assert.deepEqual(h.saves[0][2], h.bindingReview.records[2]);
});

test("filtered batch stays local, preserves hidden records, and can be undone", () => {
  const h = harness();
  h.bindingReview.bindings.push({ layer_id: "face", suggested_option_id: "rigid:head",
    options: [{ id: "rigid:head", mode: "rigid", bone_ids: ["head"] }] });
  h.bindingReview.records.push({ layer_id: "face", action: "pending", option_id: null, notes: "keep notes" });
  h.view.render({ bindingReview: h.bindingReview, reviewIdentity: "batch", canReview: true });
  h.change("绑定复核分类", "rigid");
  assert.equal(h.find("sleeve 处理方式"), undefined);
  h.find("预填待复核的单骨刚性建议").dispatchEvent(new Event("click"));
  assert.equal(h.saves.length, 0);
  assert.equal(h.find("face 绑定方案").value, "rigid:head");
  h.find("保存绑定复核并重建").dispatchEvent(new Event("click"));
  assert.equal(h.saves[0].length, 3);
  assert.deepEqual(h.saves[0].slice(0, 2), h.bindingReview.records.slice(0, 2));
  assert.equal(h.saves[0][2].notes, "keep notes");
  h.find("撤销未保存修改").dispatchEvent(new Event("click"));
  assert.equal(h.find("face 处理方式").value, "pending");
  assert.equal(h.dirty.at(-1), false);
  h.view.render({ bindingReview: h.bindingReview, reviewIdentity: "readonly", canReview: false });
  h.find("预填待复核的单骨刚性建议").dispatchEvent(new Event("click"));
  assert.equal(h.find("face 处理方式").value, "pending");
});
