import assert from "node:assert/strict";
import test from "node:test";

import { createMeshEvidenceBrowser } from "../modules/mesh-evidence-browser.js";
import {
  clearMeshEvidence,
  mountMeshEvidenceBrowser,
  renderMeshEvidenceDetail,
} from "../modules/mesh-evidence-markup.js";
import {
  meshBundleDetailUrl,
  meshBundleImageUrl,
  meshBundlesForRig,
  meshRigOptions,
  normalizeMeshBundleDetail,
  normalizeMeshBundleIndex,
} from "../modules/mesh-evidence-state.js";

const RIG_A = "a".repeat(64);
const RIG_B = "b".repeat(64);
const BUNDLE_A = "c".repeat(64);
const BUNDLE_B = "d".repeat(64);
const PNG = "e".repeat(64);
const tick = () => new Promise((resolve) => setImmediate(resolve));

function indexPayload() {
  return {
    format: "autospine-mesh-bundle-evidence-index",
    format_version: 1,
    project_id: "fixture",
    count: 3,
    items: [
      { rig_sha256: RIG_B, bundle_sha256: BUNDLE_B },
      { rig_sha256: RIG_A, bundle_sha256: BUNDLE_B },
      { rig_sha256: RIG_A, bundle_sha256: BUNDLE_A },
    ],
  };
}

function detailPayload({ noop = false } = {}) {
  const image = { path: "weights/leg-left.png", png_sha256: PNG,
    width: 32, height: 80, angle_deg: null };
  return {
    format: "autospine-mesh-bundle-evidence",
    format_version: 1,
    project_id: "fixture",
    source: {
      base_rig_sha256: "1".repeat(64), base_bundle_sha256: "2".repeat(64),
      layer_manifest_sha256: "6".repeat(64),
      resolved_project_sha256: "7".repeat(64),
      rig_sha256: RIG_A, run_sha256: "3".repeat(64),
      probes_sha256: "4".repeat(64), visuals_sha256: "5".repeat(64),
      bundle_sha256: BUNDLE_A,
    },
    status: noop ? "reviewed-noop" : "converted",
    summary: noop ? "reviewed-noop" : "converted=1",
    hinges: noop ? [] : [{
      attachment_id: "leg-left", source_layer_id: "leg-left", side: "left",
      proximal_bone_id: "thigh.left", distal_bone_id: "calf.left",
      vertex_count: 55, triangle_count: 80,
      continuous_safe_angle_deg: { minimum: -40, maximum: 60 },
      images: {
        heatmap: image,
        setup: { ...image, path: "poses/leg-left.setup.png", width: 160,
          height: 100, angle_deg: 0 },
        widest_safe: { ...image, path: "poses/leg-left.widest-safe-p060.png",
          width: 160, height: 100, angle_deg: 60 },
      },
    }],
  };
}

class FakeElement {
  constructor(ownerDocument, tagName) {
    this.ownerDocument = ownerDocument;
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.dataset = {};
    this.handlers = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.value = "";
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === "id") this.ownerDocument.elements.set(String(value), this);
    if (name === "value") this.value = String(value);
  }

  getAttribute(name) { return this.attributes.get(name) ?? null; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  addEventListener(type, handler) { this.handlers[type] = handler; }
  dispatch(type) { this.handlers[type]?.({ target: this }); }
}

class FakeDocument {
  constructor() { this.elements = new Map(); }
  createElement(tagName) { return new FakeElement(this, tagName); }
  getElementById(id) { return this.elements.get(id) || null; }
}

function descendants(element, tagName) {
  const result = [];
  for (const child of element.children) {
    if (child.tagName === tagName) result.push(child);
    result.push(...descendants(child, tagName));
  }
  return result;
}

test("index normalization is deterministic but never chooses a latest item", () => {
  const items = normalizeMeshBundleIndex(indexPayload(), "fixture");
  assert.deepEqual(meshRigOptions(items), [RIG_A, RIG_B]);
  assert.deepEqual(meshBundlesForRig(items, RIG_A), [BUNDLE_A, BUNDLE_B]);
  assert.equal(items.some((item) => "latest" in item), false);
  assert.throws(
    () => normalizeMeshBundleIndex({ ...indexPayload(), items: [{
      rig_sha256: "latest", bundle_sha256: BUNDLE_A,
    }] }, "fixture"),
    /SHA-256/,
  );
});

test("detail and image URLs require exact hashes and encoded project identity", () => {
  const detail = meshBundleDetailUrl("/api/projects/", "角色/a", RIG_A, BUNDLE_A);
  assert.equal(detail,
    `/api/projects/%E8%A7%92%E8%89%B2%2Fa/mesh-bundles/${RIG_A}/${BUNDLE_A}`);
  assert.equal(meshBundleImageUrl(
    "/api/projects", "fixture", RIG_A, BUNDLE_A, PNG,
  ), `/api/projects/fixture/mesh-bundles/${RIG_A}/${BUNDLE_A}/images/${PNG}`);
  assert.throws(() => meshBundleDetailUrl("/api/projects", "fixture", "latest", BUNDLE_A));

  const detailPayloadValue = detailPayload();
  assert.equal(normalizeMeshBundleDetail(detailPayloadValue, {
    projectId: "fixture", rigSha: RIG_A, bundleSha: BUNDLE_A,
  }), detailPayloadValue);
  assert.throws(() => normalizeMeshBundleDetail(detailPayloadValue, {
    projectId: "fixture", rigSha: RIG_B, bundleSha: BUNDLE_A,
  }), /双 SHA/);
});

test("mounted browser is semantic, keyboard reachable, and has an explicit empty state", () => {
  const doc = new FakeDocument();
  const mount = doc.createElement("div");
  const elements = mountMeshEvidenceBrowser(mount);
  assert.equal(elements.section.tagName, "SECTION");
  assert.equal(elements.section.getAttribute("aria-labelledby"), "meshEvidenceHeading");
  assert.equal(elements.status.getAttribute("role"), "status");
  assert.equal(elements.status.getAttribute("aria-live"), "polite");
  assert.equal(elements.loadBtn.tagName, "BUTTON");
  assert.equal(elements.loadBtn.getAttribute("type"), "button");
  assert.equal(elements.loadBtn.disabled, true);
  assert.match(elements.empty.textContent, /尚未选择/);

  clearMeshEvidence(elements, "没有已发布 bundle");
  assert.equal(elements.empty.hidden, false);
  assert.equal(elements.empty.textContent, "没有已发布 bundle");
  assert.equal(elements.hinges.children.length, 0);
});

test("no-op stays explicit and converted evidence gives every image useful alt text", () => {
  const doc = new FakeDocument();
  const mount = doc.createElement("div");
  const elements = mountMeshEvidenceBrowser(mount);
  renderMeshEvidenceDetail(elements, detailPayload({ noop: true }), () => "unused");
  assert.equal(elements.empty.hidden, false);
  assert.match(elements.empty.textContent, /no-op/);
  assert.equal(elements.hinges.children.length, 0);

  renderMeshEvidenceDetail(elements, detailPayload(), () => "/verified.png");
  const images = descendants(elements.hinges, "IMG");
  assert.equal(images.length, 3);
  assert.equal(images.every((image) => image.getAttribute("alt").includes("leg-left")), true);
  assert.equal(images.every((image) => image.getAttribute("loading") === "lazy"), true);
  assert.equal(elements.empty.hidden, true);
});

test("controller discovers only; detail request waits for both user selections and click", async () => {
  const doc = new FakeDocument();
  const mount = doc.createElement("div");
  const requests = [];
  const browser = createMeshEvidenceBrowser({
    mount,
    request: async (url) => {
      requests.push(url);
      return requests.length === 1 ? indexPayload() : detailPayload();
    },
  });
  browser.syncProject("fixture");
  await tick();
  assert.deepEqual(requests, ["/api/projects/fixture/mesh-bundles"]);
  assert.equal(browser.elements.rigSelect.value, "");
  assert.equal(browser.elements.loadBtn.disabled, true);

  browser.elements.rigSelect.value = RIG_A;
  browser.elements.rigSelect.dispatch("change");
  browser.elements.bundleSelect.value = BUNDLE_A;
  browser.elements.bundleSelect.dispatch("change");
  assert.equal(requests.length, 1);
  browser.elements.loadBtn.dispatch("click");
  await tick();
  assert.equal(requests[1],
    `/api/projects/fixture/mesh-bundles/${RIG_A}/${BUNDLE_A}`);
  assert.equal(browser.elements.status.dataset.kind, "ready");
});
