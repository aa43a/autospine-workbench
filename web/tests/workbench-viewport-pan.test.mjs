import assert from "node:assert/strict";
import test from "node:test";

import {
  createWorkbenchViewportPan,
  shouldStartViewportPan,
} from "../modules/workbench-viewport-pan.js";

class FakeViewport extends EventTarget {
  constructor() {
    super();
    this.dataset = {};
    this.clientWidth = 300;
    this.clientHeight = 200;
    this.scrollLeft = 40;
    this.scrollTop = 50;
    this.captured = null;
    this.space = { style: {} };
    this.surface = { style: {} };
    this.style = {
      cursor: "",
      removeProperty: () => { this.style.cursor = ""; },
    };
  }

  setPointerCapture(pointerId) { this.captured = pointerId; }
  hasPointerCapture(pointerId) { return this.captured === pointerId; }
  releasePointerCapture() { this.captured = null; }
  querySelector(selector) { return selector === "#canvasSpace" ? this.space : this.surface; }
  scrollTo({ left, top }) { this.scrollLeft = left; this.scrollTop = top; }
}

function pointerEvent(type, values) {
  const event = new Event(type, { cancelable: true });
  Object.assign(event, values);
  return event;
}

test("left drag starts only on canvas background while middle drag works anywhere", () => {
  const viewport = {};
  assert.equal(shouldStartViewportPan({ button: 0, target: viewport }, viewport), true);
  assert.equal(shouldStartViewportPan({ button: 0, target: { id: "canvasSurface" } }, viewport), true);
  assert.equal(shouldStartViewportPan({ button: 0, target: { id: "layerStack" } }, viewport), true);
  assert.equal(shouldStartViewportPan({ button: 0, target: { id: "skeletonSvg" } }, viewport), true);
  assert.equal(shouldStartViewportPan({ button: 0, target: { id: "joint-handle" } }, viewport), false);
  assert.equal(shouldStartViewportPan({ button: 1, target: { id: "joint-handle" } }, viewport), true);
});

test("pointer drag pans the workbench and cancel releases capture", () => {
  const viewport = new FakeViewport();
  const controller = createWorkbenchViewportPan(viewport);

  viewport.dispatchEvent(pointerEvent("pointerdown", {
    button: 0,
    pointerId: 7,
    clientX: 100,
    clientY: 100,
  }));
  viewport.dispatchEvent(pointerEvent("pointermove", {
    pointerId: 7,
    clientX: 70,
    clientY: 80,
  }));

  assert.equal(viewport.scrollLeft, 70);
  assert.equal(viewport.scrollTop, 70);
  assert.equal(viewport.dataset.panning, "true");
  assert.equal(viewport.captured, 7);

  controller.cancel();
  assert.equal(viewport.dataset.panning, "false");
  assert.equal(viewport.captured, null);
});

test("fit-sized content keeps a full viewport of scroll room for free panning", () => {
  const viewport = new FakeViewport();
  const controller = createWorkbenchViewportPan(viewport);
  controller.layout(150, 100);
  assert.equal(viewport.space.style.width, "750px");
  assert.equal(viewport.space.style.height, "500px");
  assert.equal(viewport.surface.style.left, "300px");
  assert.equal(viewport.surface.style.top, "200px");
  assert.equal(viewport.scrollLeft, 225);
  assert.equal(viewport.scrollTop, 150);
});

test("viewport resize rebuilds full pan margins and preserves the prior content focus", () => {
  const viewport = new FakeViewport();
  const observer = new FakeResizeObserver();
  const controller = createWorkbenchViewportPan(viewport, {
    ResizeObserverClass: class {
      constructor(callback) { observer.callback = callback; }
      observe(target) { observer.target = target; }
      disconnect() { observer.disconnected = true; }
    },
  });
  controller.layout(150, 100);
  viewport.scrollLeft = 255;
  viewport.scrollTop = 130;

  viewport.clientWidth = 500;
  viewport.clientHeight = 120;
  observer.callback([{ target: viewport }]);

  assert.equal(observer.target, viewport);
  assert.equal(viewport.space.style.width, "1150px");
  assert.equal(viewport.space.style.height, "340px");
  assert.equal(viewport.surface.style.left, "500px");
  assert.equal(viewport.surface.style.top, "120px");
  assert.equal(viewport.scrollLeft, 355);
  assert.equal(viewport.scrollTop, 90);
  controller.disconnect();
  assert.equal(observer.disconnected, true);
});

class FakeResizeObserver {
  callback = null;
  target = null;
  disconnected = false;
}
