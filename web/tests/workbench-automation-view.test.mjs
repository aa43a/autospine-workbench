import assert from "node:assert/strict";
import test from "node:test";
import { createAutomationView } from "../modules/workbench-automation-view.js";
import { renderWorkbenchStatusbar } from "../modules/workbench-statusbar.js";

class Element extends EventTarget {
  constructor(tag) { super(); this.tagName = tag; this.children = []; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
}
function fakeDocument() {
  const mount = new Element("div");
  return { mount, createElement: (tag) => new Element(tag), getElementById: (id) => id === "automationMount" ? mount : null };
}
function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }

test("automation view uses accessible text, preserves evidence links and never approves suggestions", () => {
  const doc = fakeDocument(), selected = [];
  const view = createAutomationView(doc, { canLocate: () => true, locate: (row) => selected.push(row.entity_id),
    start() {}, refresh() {}, cancel() {}, canDownload: () => false });
  const item = { type: "joint", entity_id: "<img onerror=alert(1)>", risk: "high", blocking: true,
    reason_code: "joint_review_required", evidence: [{ kind: "composite_image", url: "/api/projects/sample/composite" }] };
  view.render({ hasProject: true, canStart: false, fetching: false, active: false, canCancel: false,
    canceling: false, downloadUrl: null, message: "请先保存校正。", items: [item], steps: [] });
  const all = descendants(doc.mount);
  assert.ok(all.some((node) => node.attributes["aria-live"] === "polite"));
  assert.ok(all.some((node) => node.textContent?.includes(item.entity_id)));
  assert.equal(all.some((node) => node.tagName === "img"), false);
  assert.equal(all.some((node) => /采用|批准/.test(node.textContent || "")), false);
  const locate = all.find((node) => node.textContent === "定位并复核");
  locate.dispatchEvent(new Event("click"));
  assert.deepEqual(selected, [item.entity_id]);
  const download = all.find((node) => node.textContent === "下载 JSON / Atlas / PNG / QA");
  assert.equal(download.hidden, true);
  assert.equal(download.attributes.href, undefined);
  const event = new Event("click", { cancelable: true }); download.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true);
});

test("extracted workbench statusbar preserves selection and override counts", () => {
  const dom = { canvasStatus: {}, selectionStatus: {}, overrideStatus: {} };
  const state = { project: {}, zoom: 1.5, editMode: "joints", baseRevision: 3,
    jointOverrides: { a: {} }, jointDecisions: { b: {} }, splitDecisions: {}, layerOverrides: { c: {} } };
  renderWorkbenchStatusbar(dom, state, { width: 100, height: 200 }, null, { id: "ankle.left", x: 3, y: 4 });
  assert.equal(dom.canvasStatus.textContent, "100×200 · 150%");
  assert.equal(dom.selectionStatus.textContent, "关节 ankle.left · 3.0, 4.0");
  assert.equal(dom.overrideStatus.textContent, "3 项校正 · r3");
  renderWorkbenchStatusbar(dom, { ...state, project: null }, {}, null, null);
  assert.equal(dom.selectionStatus.textContent, "未选择对象");
});

test("version selector defaults to 4.3.26, remains labeled and updates the preview description", () => {
  const doc = fakeDocument(), versions = [];
  const view = createAutomationView(doc, { setTarget: (version) => versions.push(version) });
  const all = descendants(doc.mount);
  const select = all.find((node) => node.id === "automationTargetVersion");
  assert.equal(select.value, "4.3.26");
  assert.deepEqual(select.children.map((node) => node.value), ["4.3.26", "4.2"]);
  assert.ok(all.some((node) => node.tagName === "label" && node.attributes.for === select.id));
  select.value = "4.2"; select.dispatchEvent(new Event("change"));
  assert.deepEqual(versions, ["4.2"]);
  view.render({ targetVersion: "4.2", hasProject: true, canStart: true, fetching: false,
    active: false, canCancel: false, downloadUrl: null, message: "已就绪", items: [], steps: [] });
  assert.ok(all.some((node) => node.textContent === "从已保存的图层构建 Spine 4.2 静态预览。"));
});
