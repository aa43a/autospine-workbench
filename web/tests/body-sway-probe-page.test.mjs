import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const moduleNames = [
  "body-sway-probe-api.js",
  "body-sway-probe-app.js",
  "body-sway-probe-contract.js",
  "body-sway-probe-contract-utils.js",
  "body-sway-probe-inventory-contract.js",
  "body-sway-probe-loader.js",
  "body-sway-probe-preview-contract.js",
  "body-sway-probe-preview.js",
  "body-sway-probe-result-contract.js",
  "body-sway-probe-view.js",
];

test("P10.2 page is automatic, visual, accessible, and non-authoritative", async () => {
  const [html, css, ...modules] = await Promise.all([
    readFile(new URL("body-sway-probe.html", root), "utf8"),
    readFile(new URL("body-sway-probe.css", root), "utf8"),
    ...moduleNames.map((name) => readFile(new URL(`modules/${name}`, root), "utf8")),
  ]);
  const source = `${html}\n${modules.join("\n")}`;
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /id="projectSelect"/);
  assert.match(html, /无需选择文件、填写路径或输入 SHA-256/);
  assert.doesNotMatch(html, /type="file"/);
  assert.doesNotMatch(html, /id="[^"]*Sha[^"]*"[^>]*type="(?:text|file)"/i);
  assert.match(html, /id="sampleTimeline" type="range"/);
  assert.match(html, /角色合成图/);
  assert.match(html, /不是官方 Spine Runtime 画面/);
  assert.match(html, /越界方向（投影到边缘，最多显示 16 个）/);
  assert.match(html, /id="returnToP10"/);
  assert.match(html, /id="visualNext"/);
  assert.match(html, /how-to-capture-body-sway-runtime\.md/);
  assert.doesNotMatch(html, /id="visualNext"[^>]+body-sway-review\.html/);
  assert.match(html, /正常流程不依赖下载文件/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i);
  for (const label of [
    "循环首尾闭合", "骨骼计算稳定", "网格变形稳定", "画布范围完整",
    "网格内部连续", "图层接缝", "视觉质量",
  ]) assert.match(modules.join("\n"), new RegExp(label));
  assert.match(modules.join("\n"), /canEnterVisual/);
  assert.match(modules.join("\n"), /failure-markers/);
  assert.match(modules.join("\n"), /aria-valuetext/);
  assert.match(modules.join("\n"), /previewSvgTitle/);
  assert.match(modules.join("\n"), /projectFailureMarker/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /@media \(max-width:\s*680px\)/);
  assert.match(css, /@media \(max-width:\s*400px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /\.legend \.failure-key/);
  for (const [index, module] of modules.entries()) {
    assert.ok(module.split(/\r?\n/).length <= 300, `${moduleNames[index]} must stay <= 300 lines`);
  }
  assert.ok(css.split(/\r?\n/).length <= 300, "page CSS must stay <= 300 lines");
});

test("download uses one collision-resistant operator filename and no workflow input", async () => {
  const [contract, app] = await Promise.all([
    readFile(new URL("modules/body-sway-probe-contract.js", root), "utf8"),
    readFile(new URL("modules/body-sway-probe-app.js", root), "utf8"),
  ]);
  assert.match(contract, /\$\{project\}\.\$\{clip\}\.p10-2\.\$\{digest\.slice\(0, 12\)\}\.json/);
  assert.match(app, /link\.download = currentDownload\.filename/);
  assert.match(app, /normal flow|正常流程|服务端精确结果/);
  assert.doesNotMatch(app, /FileReader|showOpenFilePicker|webkitdirectory/);
});

test("direct P10.1 handoff is loaded before the expensive inventory", async () => {
  const loader = await readFile(new URL("modules/body-sway-probe-loader.js", root), "utf8");
  const direct = loader.indexOf("await api.entry(packageId)");
  const inventory = loader.indexOf("await hydrateInventory(current, packageId, loadedEntry)");
  assert.ok(direct >= 0 && inventory > direct);
  assert.match(loader, /queryPackageId\(search\)/);
  assert.match(loader, /current !== generation|current === generation/);
});
