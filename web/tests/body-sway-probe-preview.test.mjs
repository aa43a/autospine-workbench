import assert from "node:assert/strict";
import test from "node:test";

import {
  projectFailureMarker, sampleAriaText,
} from "../modules/body-sway-probe-preview.js";

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

test("timeline accessible text explains time and overflow without relying on color", () => {
  assert.equal(sampleAriaText({
    tick: 1_950_000, failureCount: 334, markers: Array(16).fill({}),
  }, 1, 3, 1_000_000),
  "第 2 个，共 3 个代表样本，时间 1.95 秒，发现 334 个越界顶点，图中投影 16 个方向标记");
});
