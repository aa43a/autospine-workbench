import assert from "node:assert/strict";
import test from "node:test";

import { renderLayerSelection } from "../modules/layer-selection-renderer.js";

const SVG_NS = "http://www.w3.org/2000/svg";

class FakeElement {
  constructor(ownerDocument, tagName, namespace = null) {
    this.ownerDocument = ownerDocument;
    this.tagName = tagName;
    this.namespace = namespace;
    this.attributes = {};
    this.children = [];
    this.className = "";
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
}

function fixture() {
  const document = {
    createElementNS: (namespace, tagName) => new FakeElement(document, tagName, namespace),
  };
  return new FakeElement(document, "g", SVG_NS);
}

test("selected layer renders one SVG box and four corner markers", () => {
  const group = fixture();
  renderLayerSelection(group, { bbox: [10, 20, 30, 40] }, { width: 1000, height: 1000 });

  assert.equal(group.children.length, 5);
  const [box, ...corners] = group.children;
  assert.equal(box.namespace, SVG_NS);
  assert.equal(box.tagName, "rect");
  assert.equal(box.className, "selected-layer-box");
  assert.deepEqual(box.attributes, { x: "10", y: "20", width: "30", height: "40" });
  assert.deepEqual(
    corners.map(({ namespace, tagName, className, attributes }) => ({
      namespace, tagName, className, attributes,
    })),
    [
      { namespace: SVG_NS, tagName: "circle", className: "selected-layer-corner", attributes: { cx: "10", cy: "20", r: "3.5" } },
      { namespace: SVG_NS, tagName: "circle", className: "selected-layer-corner", attributes: { cx: "40", cy: "20", r: "3.5" } },
      { namespace: SVG_NS, tagName: "circle", className: "selected-layer-corner", attributes: { cx: "10", cy: "60", r: "3.5" } },
      { namespace: SVG_NS, tagName: "circle", className: "selected-layer-corner", attributes: { cx: "40", cy: "60", r: "3.5" } },
    ],
  );
});

test("missing selection clears stale overlay without creating SVG elements", () => {
  const group = fixture();
  group.children.push({ stale: true });

  renderLayerSelection(group, null, { width: 100, height: 100 });

  assert.deepEqual(group.children, []);
});
