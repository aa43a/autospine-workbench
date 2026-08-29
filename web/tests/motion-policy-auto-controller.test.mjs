import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyAutoController } from "../modules/motion-policy-auto-controller.js";

const PACKAGE_A = "a".repeat(64);
const PACKAGE_B = "b".repeat(64);

class FakeElement extends EventTarget {
  constructor(ownerDocument = null) {
    super();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.checked = false;
    this.disabled = false;
    this.open = false;
    this.textContent = "";
    this.value = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  toggleAttribute(name, force) {
    if (force) this.attributes[name] = "";
    else delete this.attributes[name];
  }
}

function elements() {
  const document = { createElement: () => new FakeElement(document) };
  const result = Object.fromEntries([
    "autoProjectSelect", "autoReloadProject", "autoApplySafe", "autoLoadStatus",
    "autoStartPanel", "expertInputs",
  ].map((key) => [key, new FakeElement(document)]));
  result.autoApplySafe.checked = true;
  return result;
}

function packageRow(packageId, projectId) {
  return {
    package_id: packageId,
    project_id: projectId,
    motion_id: "kimodo-wave",
    inventory: { total_count: 119 },
  };
}

function packageList(rows, recommended = rows[0]?.package_id ?? null) {
  return { packages: rows, recommended_package_id: recommended };
}

function storage(initial = null) {
  const values = new Map();
  if (initial !== null) values.set("autospine.motion-policy.last-project.v1", initial);
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    value: () => values.get("autospine.motion-policy.last-project.v1") ?? null,
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("condition was not reached");
}

test("automatic controller restores the last exact package and loads it without file selection", async () => {
  const ui = elements();
  const saved = storage(PACKAGE_B);
  const rows = [packageRow(PACKAGE_A, "sample-a"), packageRow(PACKAGE_B, "sample-b")];
  const loaded = [];
  const api = {
    list: async () => packageList(rows, PACKAGE_A),
    package: async (packageId) => ({ ...rows.find((row) => row.package_id === packageId) }),
  };

  const controller = createMotionPolicyAutoController(ui, {
    api,
    storage: saved,
    onLoad: async (detail, options) => loaded.push({ detail, options }),
  });
  await controller.start();

  assert.equal(ui.autoProjectSelect.children.length, 2);
  assert.equal(ui.autoProjectSelect.value, PACKAGE_B);
  assert.equal(ui.autoProjectSelect.children[1].textContent, "sample-b · kimodo-wave · 119 项");
  assert.equal(loaded.length, 1);
  assert.deepEqual(loaded[0].detail, rows[1]);
  assert.equal(loaded[0].options.applySafe, true);
  assert.equal(loaded[0].options.isCurrent(), true);
  assert.equal(saved.value(), PACKAGE_B);
  assert.equal(ui.autoProjectSelect.disabled, false);
  assert.equal(ui.autoStartPanel.attributes["aria-busy"], undefined);
  assert.equal(ui.autoLoadStatus.dataset.tone, "success");
  assert.match(ui.autoLoadStatus.textContent, /文件、SHA 与来源校验/);
});

test("automatic controller discards stale package responses after a project switch", async () => {
  const ui = elements();
  const rows = [packageRow(PACKAGE_A, "sample-a"), packageRow(PACKAGE_B, "sample-b")];
  const first = deferred();
  const second = deferred();
  const requested = [];
  const loaded = [];
  const api = {
    list: async () => packageList(rows, PACKAGE_A),
    package: async (packageId) => {
      requested.push(packageId);
      return packageId === PACKAGE_A ? first.promise : second.promise;
    },
  };
  const saved = storage();
  const controller = createMotionPolicyAutoController(ui, {
    api,
    storage: saved,
    onLoad: async (detail) => loaded.push(detail.package_id),
  });

  const starting = controller.start();
  await waitFor(() => requested.length === 1);
  ui.autoProjectSelect.value = PACKAGE_B;
  ui.autoProjectSelect.dispatchEvent(new Event("change"));
  await waitFor(() => requested.length === 2);
  second.resolve({ ...rows[1] });
  await waitFor(() => loaded.length === 1);
  first.resolve({ ...rows[0] });
  await starting;
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(requested, [PACKAGE_A, PACKAGE_B]);
  assert.deepEqual(loaded, [PACKAGE_B]);
  assert.equal(saved.value(), PACKAGE_B);
  assert.equal(ui.autoProjectSelect.value, PACKAGE_B);
});

test("a project switch invalidates an older load already inside secondary preflight", async () => {
  const ui = elements();
  const rows = [packageRow(PACKAGE_A, "sample-a"), packageRow(PACKAGE_B, "sample-b")];
  const releaseOldPreflight = deferred();
  const entered = [];
  const committed = [];
  const currency = [];
  const controller = createMotionPolicyAutoController(ui, {
    api: {
      list: async () => packageList(rows, PACKAGE_A),
      package: async (packageId) => ({ ...rows.find((row) => row.package_id === packageId) }),
    },
    storage: storage(),
    onReset: () => {},
    onLoad: async (detail, context) => {
      entered.push(detail.package_id);
      currency.push([detail.package_id, "before", context.isCurrent()]);
      if (detail.package_id === PACKAGE_A) await releaseOldPreflight.promise;
      currency.push([detail.package_id, "after", context.isCurrent()]);
      if (context.isCurrent()) committed.push(detail.package_id);
    },
  });

  const starting = controller.start();
  await waitFor(() => entered.includes(PACKAGE_A));
  ui.autoProjectSelect.value = PACKAGE_B;
  ui.autoProjectSelect.dispatchEvent(new Event("change"));
  await waitFor(() => committed.includes(PACKAGE_B));
  releaseOldPreflight.resolve();
  await starting;

  assert.deepEqual(entered, [PACKAGE_A, PACKAGE_B]);
  assert.deepEqual(committed, [PACKAGE_B]);
  assert.deepEqual(currency, [
    [PACKAGE_A, "before", true],
    [PACKAGE_B, "before", true],
    [PACKAGE_B, "after", true],
    [PACKAGE_A, "after", false],
  ]);
  assert.equal(ui.autoProjectSelect.value, PACKAGE_B);
  assert.equal(ui.autoLoadStatus.dataset.tone, "success");
});

test("automatic controller falls back to expert inputs when no complete package exists", async () => {
  const ui = elements();
  let loadCount = 0;
  const controller = createMotionPolicyAutoController(ui, {
    api: {
      list: async () => packageList([], null),
      package: async () => { throw new Error("must not run"); },
    },
    storage: storage(),
    onLoad: async () => { loadCount += 1; },
  });

  await controller.start();

  assert.equal(loadCount, 0);
  assert.equal(ui.expertInputs.open, true);
  assert.equal(ui.autoLoadStatus.dataset.tone, "error");
  assert.match(ui.autoLoadStatus.textContent, /没有发现完整的自动复核包/);
  assert.equal(ui.autoProjectSelect.disabled, true);
});

test("assist toggle explains the next automatic behavior without approving anything", () => {
  const ui = elements();
  createMotionPolicyAutoController(ui, {
    api: {}, storage: storage(), onLoad: async () => {},
  });

  ui.autoApplySafe.checked = false;
  ui.autoApplySafe.dispatchEvent(new Event("change"));
  assert.equal(ui.autoLoadStatus.dataset.tone, "warning");
  assert.match(ui.autoLoadStatus.textContent, /只预览，不会自动采用/);

  ui.autoApplySafe.checked = true;
  ui.autoApplySafe.dispatchEvent(new Event("change"));
  assert.match(ui.autoLoadStatus.textContent, /安全建议已开启/);
});
