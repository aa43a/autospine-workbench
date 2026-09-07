// Optional Playwright smoke against a separately started, reviewed test project.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");

function spineVersionFromStoredZip(raw) {
  let offset = 0;
  while (offset + 30 <= raw.length && raw.readUInt32LE(offset) === 0x04034b50) {
    assert.equal(raw.readUInt16LE(offset + 8), 0, "preview entries must be stored");
    assert.equal(raw.readUInt16LE(offset + 6) & 8, 0, "unexpected ZIP data descriptor");
    const size = raw.readUInt32LE(offset + 18);
    const nameLength = raw.readUInt16LE(offset + 26), extraLength = raw.readUInt16LE(offset + 28);
    const name = raw.subarray(offset + 30, offset + 30 + nameLength).toString("utf8");
    const start = offset + 30 + nameLength + extraLength;
    assert.ok(start + size <= raw.length, "truncated ZIP entry");
    if (name === "skeleton.json") return JSON.parse(raw.subarray(start, start + size)).skeleton.spine;
    offset = start + size;
  }
  throw new Error("preview ZIP has no skeleton.json");
}

async function main() {
  const base = new URL(process.argv[2]);
  assert.equal(base.protocol, "http:");
  assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
  const output = path.resolve(process.argv[3]);
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base.href);
    const panel = page.locator(".automation-panel");
    const build = panel.getByRole("button", { name: "构建 Spine 预览", exact: true });
    const target = panel.getByLabel("Spine 版本", { exact: true });
    assert.equal(await target.inputValue(), "4.3.26");
    async function buildAndDownload(version, filename) {
      assert.equal(await target.inputValue(), version);
      await page.waitForFunction(() => {
        const button = document.querySelector(".automation-actions button");
        return button && !button.disabled;
      });
      await build.click();
      await page.waitForFunction(() => document.querySelector(".automation-status")?.textContent.includes("预览已就绪"),
        null, { timeout: 45000 });
      const download = page.waitForEvent("download");
      await panel.getByRole("link", { name: "下载 JSON / Atlas / PNG / QA" }).click();
      await (await download).saveAs(path.join(output, filename));
      const raw = await fs.readFile(path.join(output, filename));
      assert.equal(spineVersionFromStoredZip(raw), version);
      return { version, filename, bytes: raw.length };
    }
    const targets = [await buildAndDownload("4.3.26", "browser-preview.zip")];
    const desktopOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    await page.screenshot({ path: path.join(output, "desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await panel.scrollIntoViewIfNeeded();
    const mobileBounds = await page.evaluate(() => ({
      height: document.documentElement.scrollHeight,
      canvas: document.querySelector(".canvas-panel").getBoundingClientRect().height,
    }));
    assert.ok(mobileBounds.height < 20000 && mobileBounds.canvas < 1000,
      `unbounded mobile layout: ${JSON.stringify(mobileBounds)}`);
    await page.screenshot({ path: path.join(output, "mobile.png"), fullPage: true });
    const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    await target.selectOption("4.2");
    assert.equal(await panel.getByRole("link", { name: "下载 JSON / Atlas / PNG / QA" }).count(), 0);
    targets.push(await buildAndDownload("4.2", "browser-preview-4.2.zip"));
    await page.locator("#overrideNotes").fill("Unsaved browser smoke edit; never submitted.");
    assert.equal(await build.isDisabled(), true);
    assert.equal(await panel.getByRole("link", { name: "下载 JSON / Atlas / PNG / QA" }).count(), 0);
    assert.deepEqual(errors, []);
    assert.equal(desktopOverflow, false);
    assert.equal(mobileOverflow, false);
    console.log(JSON.stringify({ pageErrors: errors, desktopOverflow, mobileOverflow,
      dirtyBuildDisabled: true, targets, downloadedBytes: targets[0].bytes }));
  } finally {
    await browser.close();
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
