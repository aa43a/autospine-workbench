import assert from "node:assert/strict";
import test from "node:test";

import {
  coverAspect, createBodySwayProbeViewport, meetContentRect,
  normalizedContentPoint,
} from "../modules/body-sway-probe-viewport.js";

function element() {
  return {
    dataset: {}, disabled: false, value: "", textContent: "",
    listeners: {},
    addEventListener(type, listener) { this.listeners[type] = listener; },
    setAttribute(name, value) { this[name] = String(value); },
  };
}

function controls() {
  return {
    previewStage: {
      ...element(),
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 500, height: 500 }),
    },
    previewSvg: element(),
    viewportZoomOut: element(), viewportZoom: element(),
    viewportZoomValue: element(), viewportZoomIn: element(),
    viewportFitMotion: element(), viewportReset: element(),
    viewportStatus: element(),
  };
}

test("automatic motion fit is wider than the source canvas when evidence leaves it", () => {
  const elements = controls();
  const changes = [];
  const controller = createBodySwayProbeViewport(elements, {
    onViewChange: (view) => changes.push(view),
  });
  controller.load({ width: 1024, height: 1024 }, {
    document: { motion_envelope: { min_xy: [-30, -155], max_xy: [1050, 1024] } },
  });
  const view = controller.currentView();
  assert.ok(view.x < 0);
  assert.ok(view.y < -155);
  assert.ok(view.x + view.width > 1050);
  assert.ok(view.y + view.height > 1024);
  assert.equal(view.width, view.height);
  assert.equal(elements.previewSvg.viewBox,
    [view.x, view.y, view.width, view.height].join(" "));
  assert.match(elements.viewportStatus.textContent, /完整动作包络/);

  controller.resetSource();
  assert.deepEqual(controller.currentView(), { x: 0, y: 0, width: 1024, height: 1024 });
  assert.deepEqual(changes.at(-1), { x: 0, y: 0, width: 1024, height: 1024 });

  elements.viewportZoomIn.listeners.click();
  assert.ok(controller.currentView().width < 1024);
  assert.deepEqual(changes.at(-1), controller.currentView());

  elements.previewStage.listeners.pointerdown({
    button: 0, pointerId: 7, clientX: 250, clientY: 250,
  });
  elements.previewStage.listeners.pointermove({
    pointerId: 7, clientX: 300, clientY: 250,
  });
  assert.ok(controller.currentView().x < 0);
  assert.deepEqual(changes.at(-1), controller.currentView());
});

test("aspect fitting expands the shorter axis without clipping", () => {
  assert.deepEqual(coverAspect({ x: 0, y: 0, width: 200, height: 100 }, 1), {
    x: 0, y: -50, width: 200, height: 200,
  });
});

test("non-square stages use the rendered SVG content rect for zoom and pan", () => {
  const rect = { left: 10, top: 20, width: 800, height: 400 };
  assert.deepEqual(meetContentRect(rect, 1), {
    left: 210, top: 20, width: 400, height: 400,
  });
  assert.deepEqual(normalizedContentPoint(rect, 1, 210, 220), { x: 0, y: 0.5 });
  assert.deepEqual(normalizedContentPoint(rect, 1, 410, 220), { x: 0.5, y: 0.5 });
  assert.deepEqual(normalizedContentPoint(rect, 1, 10, 220), { x: 0, y: 0.5 });
});
