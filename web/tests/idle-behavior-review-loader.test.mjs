import assert from "node:assert/strict";
import test from "node:test";

import { createIdleBehaviorReviewLoader } from "../modules/idle-behavior-review-loader.js";
import {
  DIGESTS, entryDocument, packageList, packageSummary,
} from "./idle-behavior-review-fixtures.mjs";

const PACKAGE_B = "8".repeat(64);
const PREFIX_PACKAGE_A = `abcdef12a${"1".repeat(55)}`;
const PREFIX_PACKAGE_B = `abcdef12b${"2".repeat(55)}`;

class FakeElement extends EventTarget {
  constructor(ownerDocument = null) {
    super();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.disabled = false;
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

function ui() {
  const document = { createElement: () => new FakeElement(document) };
  return Object.fromEntries(["panel", "projectSelect", "reloadButton", "status"]
    .map((key) => [key, new FakeElement(document)]));
}

function storage(initial = null) {
  const values = new Map();
  if (initial) values.set("autospine.idle-behavior.last-package.v1", initial);
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    selected: () => values.get("autospine.idle-behavior.last-package.v1"),
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function eventually(predicate) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("condition not reached");
}

test("loader restores a saved package and loads it without files or SHA input", async () => {
  const elements = ui();
  const saved = storage(PACKAGE_B);
  const rows = [
    packageSummary(),
    packageSummary({ package_id: PACKAGE_B, project_id: "sample-b" }),
  ];
  const loaded = [];
  const loader = createIdleBehaviorReviewLoader(elements, {
    storage: saved,
    api: {
      list: async () => packageList(rows, DIGESTS.package),
      entry: async (packageId) => entryDocument({
        package: { ...entryDocument().package, ...rows.find((row) => row.package_id === packageId) },
      }),
    },
    onLoad: async (entry) => loaded.push(entry.package.package_id),
  });
  await loader.start();

  assert.equal(elements.projectSelect.children.length, 2);
  assert.equal(elements.projectSelect.value, PACKAGE_B);
  assert.deepEqual(loaded, [PACKAGE_B]);
  assert.equal(saved.selected(), PACKAGE_B);
  assert.equal(elements.status.dataset.tone, "success");
  assert.match(elements.status.textContent, /无需选择文件或填写 SHA/);
});

test("explicit package handoff wins over a previously saved selection", async () => {
  const elements = ui();
  const rows = [
    packageSummary(),
    packageSummary({ package_id: PACKAGE_B, project_id: "sample-b" }),
  ];
  const loaded = [];
  const loader = createIdleBehaviorReviewLoader(elements, {
    requestedPackageId: PACKAGE_B,
    storage: storage(DIGESTS.package),
    api: {
      list: async () => packageList(rows, DIGESTS.package),
      entry: async (packageId) => entryDocument({
        package: {
          ...entryDocument().package,
          ...rows.find((row) => row.package_id === packageId),
        },
      }),
    },
    onLoad: async (entry) => loaded.push(entry.package.package_id),
  });
  await loader.start();

  assert.equal(elements.projectSelect.value, PACKAGE_B);
  assert.deepEqual(loaded, [PACKAGE_B]);
});

test("loader does not guess when multiple valid packages have no recommendation", async () => {
  const elements = ui();
  const rows = [packageSummary(), packageSummary({ package_id: PACKAGE_B })];
  let loads = 0;
  const loader = createIdleBehaviorReviewLoader(elements, {
    storage: storage(),
    api: {
      list: async () => packageList(rows, null),
      entry: async () => { loads += 1; return entryDocument(); },
    },
  });
  await loader.start();

  assert.equal(loads, 0);
  assert.equal(elements.status.dataset.tone, "warning");
  assert.match(elements.status.textContent, /请先选择/);
  assert.equal(elements.projectSelect.disabled, false);
  assert.match(elements.projectSelect.children[1].textContent, /版本/);
  assert.notEqual(
    elements.projectSelect.children[1].textContent,
    elements.projectSelect.children[2].textContent,
  );
});

test("ambiguous labels use deterministic version numbers and shortest unique package prefixes", async () => {
  const elements = ui();
  const rows = [
    packageSummary({ package_id: PREFIX_PACKAGE_A }),
    packageSummary({ package_id: PREFIX_PACKAGE_B }),
  ];
  const loader = createIdleBehaviorReviewLoader(elements, {
    storage: storage(),
    api: {
      list: async () => packageList(rows, null),
      entry: async () => { throw new Error("must remain selection-only"); },
    },
  });
  await loader.start();

  const labels = elements.projectSelect.children.slice(1).map((row) => row.textContent);
  assert.deepEqual(labels, [
    "seethrough_output · kimodo-idle · idle-001 · 版本 1 · abcdef12a",
    "seethrough_output · kimodo-idle · idle-001 · 版本 2 · abcdef12b",
  ]);
});

test("mutation lock prevents project switching until a receipt is resolved", async () => {
  const elements = ui();
  const rows = [packageSummary(), packageSummary({
    package_id: PACKAGE_B, project_id: "sample-b",
  })];
  let requests = 0;
  const loader = createIdleBehaviorReviewLoader(elements, {
    storage: storage(),
    api: {
      list: async () => packageList(rows, DIGESTS.package),
      entry: async () => { requests += 1; return entryDocument(); },
    },
  });
  await loader.start();
  loader.setMutationLocked(true);
  assert.equal(elements.projectSelect.disabled, true);
  assert.equal(elements.reloadButton.disabled, true);

  elements.projectSelect.value = PACKAGE_B;
  elements.projectSelect.dispatchEvent(new Event("change"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(elements.projectSelect.value, DIGESTS.package);
  assert.equal(requests, 1);

  loader.setMutationLocked(false);
  assert.equal(elements.projectSelect.disabled, false);
  assert.equal(elements.projectSelect.value, DIGESTS.package);
});

test("loader discards a late detail after the operator switches packages", async () => {
  const elements = ui();
  const rows = [packageSummary(), packageSummary({ package_id: PACKAGE_B })];
  const first = deferred();
  const second = deferred();
  const loaded = [];
  let requests = 0;
  const loader = createIdleBehaviorReviewLoader(elements, {
    storage: storage(),
    api: {
      list: async () => packageList(rows, DIGESTS.package),
      entry: async (packageId) => {
        requests += 1;
        return packageId === DIGESTS.package ? first.promise : second.promise;
      },
    },
    onLoad: async (entry) => loaded.push(entry.package.package_id),
  });

  const starting = loader.start();
  await eventually(() => requests === 1);
  elements.projectSelect.value = PACKAGE_B;
  elements.projectSelect.dispatchEvent(new Event("change"));
  await eventually(() => requests === 2);
  second.resolve(entryDocument({
    package: { ...entryDocument().package, package_id: PACKAGE_B },
  }));
  await eventually(() => loaded.length === 1);
  first.resolve(entryDocument());
  await starting;

  assert.deepEqual(loaded, [PACKAGE_B]);
  assert.equal(elements.projectSelect.value, PACKAGE_B);
});
