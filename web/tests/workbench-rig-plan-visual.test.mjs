import assert from "node:assert/strict";
import test from "node:test";
import { createRigPlanVisual } from "../modules/workbench-rig-plan-visual.js";

class Element extends EventTarget {
  constructor(tag) { super(); this.tagName = tag; this.children = []; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
}
const descendants = (node) => [node, ...node.children.flatMap(descendants)];
function harness() {
  const calls = [], namespaces = [];
  const document = { createElement: (tag) => new Element(tag), createElementNS: (ns, tag) => {
    namespaces.push(ns); return new Element(tag);
  } };
  const view = createRigPlanVisual(document, { locate: (value) => calls.push(value) });
  const layers = [{ layer_id: "coat", name: "上衣", strategy: "rigid" },
    { layer_id: "sleeve", name: "袖子", strategy: "secondary_motion" }];
  const visual = { canvas: [100, 200], composite_url: "/api/projects/alice/composite?revision=3",
    layers: [{ layer_id: "coat", bbox: [10, 20, 90, 180] }, { layer_id: "sleeve", bbox: [20, 25, 80, 150] }] };
  const model = { visual, layers, canLocate: true };
  const find = (label) => descendants(view.element).find((node) => node.textContent === label || node.attributes["aria-label"] === label);
  view.render(model);
  return { view, model, find, calls, namespaces, all: () => descendants(view.element) };
}

test("visual shows source image, colored layer ranges, names and candidate scope", () => {
  const h = harness(), nodes = h.all();
  assert.equal(nodes.find((e) => e.tagName === "image").attributes.href, h.model.visual.composite_url);
  const boxes = nodes.filter((e) => e.tagName === "rect");
  assert.equal(boxes.length, 2);
  assert.deepEqual([boxes[0].attributes.x, boxes[0].attributes.y, boxes[0].attributes.width, boxes[0].attributes.height], ["10", "20", "80", "160"]);
  assert.notEqual(boxes[0].attributes.stroke, boxes[1].attributes.stroke);
  assert.ok(nodes.some((e) => e.textContent?.includes("不是精确分区或骨骼权重")));
  assert.ok(h.namespaces.every((ns) => ns === "http://www.w3.org/2000/svg"));
  assert.deepEqual(h.calls, []);
});

test("range click, keyboard and overlap dropdown select locally until explicit locate", () => {
  const h = harness(), sleeve = h.find("袖子 · 次级运动");
  sleeve.dispatchEvent(new Event("click"));
  assert.equal(h.find("选择规划图层").value, "sleeve");
  assert.equal(sleeve.attributes["aria-pressed"], "true");
  assert.deepEqual(h.calls, []);
  h.find("定位选中图层复核").dispatchEvent(new Event("click"));
  assert.deepEqual(h.calls, [{ type: "binding", layer_id: "sleeve" }]);
  const select = h.find("选择规划图层"); select.value = "coat"; select.dispatchEvent(new Event("change"));
  assert.equal(sleeve.attributes["aria-pressed"], "false");
  const event = new Event("keydown", { cancelable: true }); event.key = "Enter"; sleeve.dispatchEvent(event);
  assert.equal(select.value, "sleeve"); assert.equal(event.defaultPrevented, true);
  assert.equal(h.calls.length, 1);
});

test("category filter only renders its rows and source changes clear stale selection", () => {
  const h = harness(); h.find("袖子 · 次级运动").dispatchEvent(new Event("click"));
  h.view.render({ ...h.model, layers: [h.model.layers[0]] });
  assert.equal(h.all().filter((e) => e.tagName === "rect").length, 1);
  assert.equal(h.find("选择规划图层").value, "coat");
  h.view.render(h.model); h.find("袖子 · 次级运动").dispatchEvent(new Event("click"));
  h.view.render({ ...h.model, visual: { ...h.model.visual, composite_url: "/api/projects/other/composite" } });
  assert.equal(h.find("选择规划图层").value, "coat");
  h.view.render({ ...h.model, layers: [] });
  assert.equal(h.find("定位选中图层复核").disabled, true);
  h.find("定位选中图层复核").dispatchEvent(new Event("click")); assert.deepEqual(h.calls, []);
});

test("readonly blocks callbacks; missing images and invalid geometry degrade without remote loading", () => {
  const h = harness(); h.view.render({ ...h.model, canLocate: false });
  h.find("定位选中图层复核").dispatchEvent(new Event("click")); assert.deepEqual(h.calls, []);
  h.view.render({ ...h.model, visual: { ...h.model.visual, composite_url: "https://example.org/image.png" } });
  assert.equal(h.all().filter((e) => e.tagName === "image").length, 0);
  assert.ok(h.all().some((e) => e.textContent?.includes("暂无可视化底图")));
  h.view.render({ ...h.model, visual: { ...h.model.visual, layers: [
    { layer_id: "coat", bbox: [-10, 5, 110, 205] }, { layer_id: "sleeve", bbox: [20, NaN, 80, 150] },
  ] } });
  const box = h.all().find((e) => e.tagName === "rect");
  assert.equal(box.attributes.width, "100"); assert.equal(box.attributes.height, "195");
  assert.equal(h.all().filter((e) => e.tagName === "rect").length, 1);
  assert.equal(h.model.layers.length, 2);
});
