import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("P10 operator page is visual, automatic, accessible, and keeps one human boundary", async () => {
  const root = new URL("../", import.meta.url);
  const moduleNames = [
    "idle-behavior-review-app.js", "idle-behavior-review-api.js",
    "idle-behavior-canvas-adjustment-contract.js",
    "idle-behavior-canvas-adjustment-view.js",
    "idle-behavior-review-contract.js", "idle-behavior-review-contract-evidence.js",
    "idle-behavior-review-contract-package.js",
    "idle-behavior-review-confirmation.js",
    "idle-behavior-review-loader.js", "idle-behavior-review-model.js",
    "idle-behavior-review-preview.js", "idle-behavior-review-view.js",
  ];
  const [html, css, canvasCss, ...modules] = await Promise.all([
    readFile(new URL("idle-behavior-review.html", root), "utf8"),
    readFile(new URL("idle-behavior-review.css", root), "utf8"),
    readFile(new URL("idle-behavior-canvas-adjustment.css", root), "utf8"),
    ...moduleNames.map((name) => readFile(new URL(`modules/${name}`, root), "utf8")),
  ]);

  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /id="projectSelect"/);
  assert.match(html, /无需选择文件或填写 SHA-256/);
  assert.doesNotMatch(html, /type="file"/);
  assert.doesNotMatch(html, /id="[^"]*Sha[^"]*"[^>]*type="(?:text|file)"/i);
  for (const id of ["cycles", "lowerAmplitude", "headAmplitude", "phaseDelay"]) {
    assert.match(html, new RegExp(`id="${id}" type="range"`));
  }
  assert.match(html, /id="explicitConfirmation" type="checkbox"/);
  assert.match(html, /id="canvasDraftPanel"/);
  assert.match(html, /id="restoreCanvasParameters"/);
  assert.match(html, /未验证草稿/);
  assert.match(html, /保存 P10\.1，下一步运行结构探针/);
  assert.match(html, /id="cycles" type="range" min="1" max="64"/);
  assert.match(html, /id="lowerAmplitude" type="range" min="0" max="10"/);
  assert.match(html, /id="phaseDelay" type="range" min="0" max="0\.333333333333"/);
  assert.match(html, /id="phaseDelay"[^>]*step="any"/);
  assert.doesNotMatch(`${html}\n${modules.join("\n")}`, /送往结构探针|将进入结构探针/);
  assert.match(html, /id="unobservableBodySway"/);
  assert.match(html, /<dialog id="decisionDialog"/);
  assert.match(html, /aria-labelledby="decisionDialogTitle"/);
  assert.match(html, /按 Esc 或点击弹窗外遮罩可取消/);
  assert.match(html, /id="cancelDecision"[^>]*autofocus/);
  assert.match(html, /id="commitDecision"/);
  assert.match(html, /id="receiptProbeLink"/);
  assert.match(html, /打开 P10\.2 自动结构探针/);
  assert.match(html, /不是 Spine Runtime 画面/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /@media \(max-width: 560px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(canvasCss, /@media \(max-width: 560px\)/);
  const app = modules[moduleNames.indexOf("idle-behavior-review-app.js")];
  const cancelGate = app.match(/if \(!confirmed\) \{[\s\S]*?return;\s*\}/)?.[0] ?? "";
  assert.match(cancelGate, /setMutationLocked\(false\)/);
  assert.ok(app.indexOf(cancelGate) < app.indexOf("await submitDecision(identity, request)"));
  assert.doesNotMatch(modules.join("\n"), /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(app, /explicitConfirmation\.checked = false/);
  assert.match(app, /canvasAdjustmentDraft/);
  assert.match(modules.join("\n"), /canvas-adjustment-drafts/);
  for (const [index, source] of modules.entries()) {
    assert.ok(source.split(/\r?\n/).length < 400, `${moduleNames[index]} must stay below 400 lines`);
  }
});
