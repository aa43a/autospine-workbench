import assert from "node:assert/strict";
import test from "node:test";

import { createBodySwayProbeLoader, queryPackageId } from "../modules/body-sway-probe-loader.js";
import { normalizeProbeEntry } from "../modules/body-sway-probe-contract.js";
import {
  PACKAGE_A, PACKAGE_B, inventoryFixture, packageRow, probeEntryFixture,
} from "./body-sway-probe-fixtures.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((next) => { resolve = next; });
  return { promise, resolve };
}

function fakeElements() {
  const listeners = new Map();
  const document = {
    createElement: () => ({ value: "", textContent: "", disabled: false }),
  };
  const select = {
    value: "", disabled: false, ownerDocument: document, children: [],
    addEventListener(type, handler) { listeners.set(`select:${type}`, handler); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    append(node) { this.children.push(node); },
  };
  const button = {
    disabled: false,
    addEventListener(type, handler) { listeners.set(`button:${type}`, handler); },
  };
  return {
    elements: {
      panel: { toggleAttribute() {} },
      projectSelect: select,
      reloadButton: button,
      status: { textContent: "", dataset: {} },
    },
    listeners,
  };
}

test("valid package query loads detail before the slower inventory request", async () => {
  const list = deferred();
  const calls = [];
  const loaded = [];
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: `?package_id=${PACKAGE_B}`,
    storage: null,
    api: {
      async entry(id) { calls.push(`entry:${id}`); return probeEntryFixture(); },
      async list() { calls.push("list"); return list.promise; },
    },
    onLoad(payload) {
      loaded.push(payload.package.package_id);
      return normalizeProbeEntry(payload, PACKAGE_B);
    },
  });
  const started = loader.start();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(loaded, [PACKAGE_B]);
  assert.deepEqual(calls, [`entry:${PACKAGE_B}`, "list"]);
  list.resolve(inventoryFixture());
  assert.equal(await started, true);
  assert.equal(elements.projectSelect.value, PACKAGE_B);
});

test("without query, the only probe-ready package is selected automatically", async () => {
  const calls = [];
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: "",
    storage: null,
    api: {
      async list() {
        return inventoryFixture([
          packageRow(PACKAGE_A, "not_applicable", "seethrough_output"),
          packageRow(PACKAGE_B, "probe_ready"),
        ], PACKAGE_B);
      },
      async entry(id) { calls.push(id); return probeEntryFixture(); },
    },
  });
  assert.equal(await loader.start(), true);
  assert.deepEqual(calls, [PACKAGE_B]);
  assert.equal(elements.projectSelect.value, PACKAGE_B);
});

test("incomplete inventory never treats its only ready row as unambiguous", async () => {
  const calls = [];
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: "",
    storage: null,
    api: {
      async list() {
        return inventoryFixture([packageRow(PACKAGE_B, "probe_ready")], null, 1);
      },
      async entry(id) { calls.push(id); return probeEntryFixture(); },
    },
  });
  assert.equal(await loader.start(), false);
  assert.deepEqual(calls, []);
  assert.equal(elements.projectSelect.value, "");
  assert.match(elements.status.textContent, /1 个版本校验失败/);
  assert.equal(elements.projectSelect.children[0].textContent, "请选择项目与动作");
});

test("an all-skipped inventory explains validation failure instead of blaming P10.1", async () => {
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: "", storage: null,
    api: {
      async list() { return inventoryFixture([], null, 2); },
      async entry() { throw new Error("must not load"); },
    },
  });
  assert.equal(await loader.start(), false);
  assert.match(elements.status.textContent, /2 个项目.*全部版本校验失败/);
});

test("direct result is invalidated when the hydrated current head has changed", async () => {
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: `?package_id=${PACKAGE_B}`,
    storage: null,
    api: {
      async entry() { return probeEntryFixture(); },
      async list() {
        const changed = packageRow(PACKAGE_B, "probe_ready");
        changed.current_revision = 3;
        changed.decision_sha256 = "f".repeat(64);
        return inventoryFixture([changed], PACKAGE_B);
      },
    },
    onLoad(payload) { return normalizeProbeEntry(payload, PACKAGE_B); },
  });
  assert.equal(await loader.start(), true);
  assert.equal(elements.projectSelect.value, "");
  assert.match(elements.status.textContent, /旧结果已停用/);
});

test("a superseded detail response cannot overwrite the latest selection", async () => {
  const slowA = deferred();
  const loaded = [];
  const { elements } = fakeElements();
  const loader = createBodySwayProbeLoader(elements, {
    locationSearch: "",
    storage: null,
    api: {
      async list() {
        return inventoryFixture([
          packageRow(PACKAGE_A, "probe_ready", "seethrough_output"),
          packageRow(PACKAGE_B, "probe_ready"),
        ], null);
      },
      async entry(id) {
        if (id === PACKAGE_A) return slowA.promise;
        return probeEntryFixture();
      },
    },
    onLoad(_payload, context) { loaded.push(context.packageRow.package_id); },
  });
  assert.equal(await loader.start(), false);
  elements.projectSelect.value = PACKAGE_A;
  const first = loader.reload();
  elements.projectSelect.value = PACKAGE_B;
  const second = loader.reload();
  assert.equal(await second, true);
  slowA.resolve(probeEntryFixture({ packageId: PACKAGE_A }));
  assert.equal(await first, false);
  assert.deepEqual(loaded, [PACKAGE_B]);
});

test("query parser admits only one canonical lowercase package digest", () => {
  assert.equal(queryPackageId(`?package_id=${PACKAGE_B}`), PACKAGE_B);
  assert.equal(queryPackageId("?package_id=../latest"), null);
  assert.equal(queryPackageId(`?package_id=${"B".repeat(64)}`), null);
  assert.equal(queryPackageId(`?package_id=${PACKAGE_A}&package_id=${PACKAGE_B}`), null);
});
