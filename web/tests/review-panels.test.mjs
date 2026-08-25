import assert from "node:assert/strict";
import test from "node:test";

import {
  collectQaFlags,
  flattenCapabilities,
  formatCapabilityValue,
  layerQaFlags,
  normalizeQaFlags,
  renderCapabilitiesPanel,
  renderQaPanel,
} from "../modules/review-panels.js";


class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.classList = {
      add: (...names) => {
        this.className = [this.className, ...names].filter(Boolean).join(" ");
      },
    };
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  addEventListener(name, listener) {
    this.listeners[name] = listener;
  }
}


function fakeDocument() {
  const doc = {
    createElement: (name) => new FakeElement(name, doc),
    createElementNS: (_namespace, name) => new FakeElement(name, doc),
  };
  return doc;
}


test("QA normalization preserves explicit fields and supplies stable fallbacks", () => {
  assert.deepEqual(normalizeQaFlags("RAW_FLAG"), [{
    code: "RAW_FLAG",
    message: "RAW_FLAG",
    severity: "warning",
  }]);
  assert.deepEqual(normalizeQaFlags([{ id: "DETAIL", detail: "复核", level: "ERROR", source: 7 }]), [{
    id: "DETAIL",
    detail: "复核",
    level: "ERROR",
    source: 7,
    code: "DETAIL",
    message: "复核",
    severity: "error",
  }]);
  assert.equal(normalizeQaFlags([{}])[0].code, "QA-1");
});


test("layer QA adds each derived warning once", () => {
  const flags = layerQaFlags({
    qa_flags: ["EMPTY_LAYER"],
    empty: true,
    disposition: "review",
  });
  assert.deepEqual(flags.map((flag) => flag.code), ["EMPTY_LAYER", "LAYER_REVIEW"]);
});


test("QA collection keeps audit, project, layer, and unresolved evidence ordering", () => {
  const project = {
    qa_flags: ["PROJECT_FLAG"],
    workflow: { audit_warnings: { high_composite_error: true, empty_layer_count: 2 } },
    resolved: { qa: { unresolved_joint_ids: ["wrist_l"] } },
  };
  const layers = [{ id: 4, name: "袖子" }];
  const flags = collectQaFlags({
    project,
    layers,
    joints: [],
    resolveLayer: () => ({
      qa_flags: [{ id: "LAYER_FLAG", detail: "图层问题", level: "ERROR" }],
      empty: true,
      disposition: "review",
    }),
  });
  assert.deepEqual(flags.map((flag) => flag.code), [
    "EMPTY_LAYERS",
    "COMPOSITE_ERROR",
    "PROJECT_FLAG",
    "LAYER_FLAG",
    "EMPTY_LAYER",
    "LAYER_REVIEW",
    "UNRESOLVED_JOINTS",
  ]);
  assert.equal(flags[3].layerId, "4");
  assert.equal(flags[3].layerName, "袖子");
});


test("QA panel preserves empty markup and caps rendered evidence at 30", () => {
  const doc = fakeDocument();
  const elements = {
    qaCounter: doc.createElement("span"),
    qaList: doc.createElement("div"),
  };
  renderQaPanel(elements, [], () => {});
  assert.equal(elements.qaCounter.textContent, "0");
  assert.equal(elements.qaList.children[0].className, "selection-empty");
  assert.equal(elements.qaList.children[0].textContent, "当前项目没有 QA 警告。");

  const selected = [];
  const flags = Array.from({ length: 35 }, (_value, index) => ({
    code: `FLAG_${index}`,
    message: `问题 ${index}`,
    severity: "warning",
    layerId: index === 0 ? "layer-1" : null,
    layerName: index === 0 ? "手臂" : undefined,
  }));
  renderQaPanel(elements, flags, (id) => selected.push(id));
  assert.equal(elements.qaCounter.textContent, "35");
  assert.equal(elements.qaList.children.length, 30);
  const first = elements.qaList.children[0];
  assert.equal(first.tagName, "button");
  assert.equal(first.type, "button");
  assert.equal(first.className, "qa-item");
  assert.equal(first.dataset.severity, "warning");
  assert.equal(first.children[0].children[0].attributes.href, "#icon-warning");
  assert.equal(first.children[1].children[0].textContent, "问题 0");
  assert.equal(first.children[1].children[1].textContent, "FLAG_0 · 手臂");
  first.listeners.click();
  assert.deepEqual(selected, ["layer-1"]);
  assert.equal(elements.qaList.children[1].tagName, "div");
});


test("capabilities flatten nested contracts and preserve display state", () => {
  assert.deepEqual(flattenCapabilities({
    tracking: { state: "ready", confidence: 0.954 },
    attempts: 2,
    formats: ["rigir", "spine"],
  }), [
    { key: "tracking", value: "ready · 95%", state: "ready" },
    { key: "attempts", value: 2 },
    { key: "formats", value: ["rigir", "spine"] },
  ]);
  assert.deepEqual(flattenCapabilities({ a: { b: { c: { d: { e: { f: true } } } } } }), []);
  assert.equal(formatCapabilityValue(true), "ready");
  assert.equal(formatCapabilityValue(false), "missing");
  assert.equal(formatCapabilityValue(1.234), "1.23");
  assert.equal(formatCapabilityValue(null), "—");
});


test("capabilities panel preserves empty and populated DOM contracts", () => {
  const doc = fakeDocument();
  const elements = { capabilityList: doc.createElement("div") };
  renderCapabilitiesPanel(elements, null);
  assert.equal(elements.capabilityList.children[0].className, "selection-empty");
  assert.equal(elements.capabilityList.children[0].textContent, "暂无能力数据。");

  renderCapabilitiesPanel(elements, {
    tracking: { available: true, confidence: 0.8 },
    score: 1.25,
  });
  assert.equal(elements.capabilityList.children.length, 2);
  const [tracking, score] = elements.capabilityList.children;
  assert.equal(tracking.className, "capability-row");
  assert.equal(tracking.children[0].textContent, "tracking");
  assert.equal(tracking.children[0].title, "tracking");
  assert.equal(tracking.children[1].className, "capability-state");
  assert.equal(tracking.children[1].dataset.state, "true");
  assert.equal(tracking.children[1].textContent, "true · 80%");
  assert.equal(score.children[1].dataset.state, "1.25");
  assert.equal(score.children[1].textContent, "1.25");
});
