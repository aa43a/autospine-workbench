import assert from "node:assert/strict";
import test from "node:test";

import {
  projectFailureMarker, sampleAriaText,
} from "../modules/body-sway-probe-preview.js";
import {
  placeFailureMarker,
} from "../modules/body-sway-probe-markers.js";

test("off-canvas witnesses become visible directional edge markers", () => {
  const right = projectFailureMarker({
    attachmentId: "layer-007", vertexIndex: 12,
    point: { x: 1040, y: 488 }, sides: ["right"],
  }, { width: 1024, height: 1024 });
  assert.deepEqual(right, {
    x: 1010, y: 488, glyph: "→",
    label: "layer-007 顶点 12 位于画布右侧",
  });

  const corner = projectFailureMarker({
    attachmentId: "hair", vertexIndex: 3,
    point: { x: -20, y: -8 }, sides: ["left", "top"],
  }, { width: 1024, height: 1024 });
  assert.deepEqual({ x: corner.x, y: corner.y, glyph: corner.glyph }, {
    x: 14, y: 14, glyph: "↖",
  });
});

test("markers use world positions inside the view and edge indicators outside it", () => {
  const marker = {
    attachmentId: "layer-007-handwear-l", vertexIndex: 4,
    point: { x: 1040, y: 488 }, sides: ["right"],
  };
  const canvas = { width: 1024, height: 1024 };

  const fitted = placeFailureMarker(marker, canvas, {
    x: -160, y: -160, width: 1344, height: 1344,
  });
  assert.equal(fitted.edge, false);
  assert.deepEqual({ x: fitted.x, y: fitted.y, glyph: fitted.glyph }, {
    x: 1040, y: 488, glyph: "→",
  });

  const source = placeFailureMarker(marker, canvas, {
    x: 0, y: 0, width: 1024, height: 1024,
  });
  assert.equal(source.edge, true);
  assert.equal(source.x, 1010);
  assert.match(source.label, /当前视口右侧.*边缘标记/);

  const panned = placeFailureMarker(marker, canvas, {
    x: -500, y: 0, width: 1024, height: 1024,
  });
  assert.equal(panned.edge, true);
  assert.equal(panned.x, 510);

  const zoomed = placeFailureMarker(marker, canvas, {
    x: 100, y: 100, width: 512, height: 512,
  });
  assert.equal(zoomed.edge, true);
  assert.equal(zoomed.x, 605);
  assert.equal(zoomed.scale, 0.5);
});

test("timeline accessible text explains time and overflow without relying on color", () => {
  assert.equal(sampleAriaText({
    tick: 1_950_000, failureCount: 334, markers: Array(16).fill({}),
  }, 1, 3, 1_000_000),
  "第 2 个，共 3 个代表样本，时间 1.95 秒，发现 334 个越界顶点，图中投影 16 个方向标记");
});
