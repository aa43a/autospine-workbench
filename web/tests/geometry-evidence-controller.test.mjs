import assert from "node:assert/strict";
import test from "node:test";

import { createGeometryEvidenceController } from "../modules/geometry-evidence-controller.js";
import {
  geometryDocument,
  reviewWithReference,
  SHA_A,
  SHA_B,
} from "./geometry-evidence-fixture.mjs";

const pathRef = (sha) => `alpha-geometry-evidence:${sha}#paths/arm.left.path.000`;
const tick = () => new Promise((resolve) => setImmediate(resolve));

function elementsFixture() {
  const handlers = {};
  const retry = {
    hidden: true,
    addEventListener: (type, handler) => { handlers[type] = handler; },
  };
  const group = {
    clearCount: 0,
    replaceChildren() { this.clearCount += 1; },
  };
  return {
    handlers,
    elements: {
      geometryEvidenceRetryBtn: retry,
      geometryEvidenceStatus: { dataset: {}, textContent: "" },
      geometryEvidenceGroup: group,
    },
  };
}

test("controller loads pinned geometry and renders the referenced fragment", async () => {
  const fixture = elementsFixture();
  const requests = [];
  const rendered = [];
  const controller = createGeometryEvidenceController({
    elements: fixture.elements,
    request: async (url) => { requests.push(url); return geometryDocument(); },
    renderEvidence: (_group, targets) => rendered.push(targets),
  });
  controller.sync(reviewWithReference(pathRef(SHA_A)));
  await tick();
  assert.equal(requests[0], `/api/projects/fixture/geometry-evidence/${SHA_A}`);
  assert.equal(rendered[0][0].item.path_id, "arm.left.path.000");
  assert.equal(fixture.elements.geometryEvidenceStatus.dataset.kind, "ready");
  assert.match(fixture.elements.geometryEvidenceStatus.textContent, /最大 residual/);
});

test("no reference is explicit and performs no request", () => {
  const fixture = elementsFixture();
  let requests = 0;
  const review = reviewWithReference("pose-observations:fixture", "pose_heatmap");
  const controller = createGeometryEvidenceController({
    elements: fixture.elements,
    request: async () => { requests += 1; },
    renderEvidence: () => {},
  });
  controller.sync(review);
  assert.equal(requests, 0);
  assert.match(fixture.elements.geometryEvidenceStatus.textContent, /没有固定/);
  assert.equal(fixture.elements.geometryEvidenceRetryBtn.hidden, true);
});

test("404 exposes retry and retry can recover", async () => {
  const fixture = elementsFixture();
  let attempt = 0;
  const controller = createGeometryEvidenceController({
    elements: fixture.elements,
    request: async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("HTTP 404");
      return geometryDocument();
    },
    renderEvidence: () => {},
  });
  controller.sync(reviewWithReference(pathRef(SHA_A)));
  await tick();
  assert.equal(fixture.elements.geometryEvidenceStatus.dataset.kind, "error");
  assert.equal(fixture.elements.geometryEvidenceRetryBtn.hidden, false);
  fixture.handlers.click();
  await tick();
  assert.equal(attempt, 2);
  assert.equal(fixture.elements.geometryEvidenceStatus.dataset.kind, "ready");
  assert.equal(fixture.elements.geometryEvidenceRetryBtn.hidden, true);
});

test("stale request completion cannot replace the current candidate evidence", async () => {
  const fixture = elementsFixture();
  const pending = new Map();
  const renderedShas = [];
  const controller = createGeometryEvidenceController({
    elements: fixture.elements,
    request: (url) => new Promise((resolve) => pending.set(url.split("/").at(-1), resolve)),
    renderEvidence: (_group, targets) => renderedShas.push(targets[0].sha256),
  });
  controller.sync(reviewWithReference(pathRef(SHA_A), "layer_alpha", "a"));
  controller.sync(reviewWithReference(pathRef(SHA_B), "layer_alpha", "b"));
  pending.get(SHA_B)(geometryDocument());
  await tick();
  pending.get(SHA_A)(geometryDocument());
  await tick();
  assert.deepEqual(renderedShas, [SHA_B]);
});

test("missing referenced fragment is a retryable corrupt-document error", async () => {
  const fixture = elementsFixture();
  const corrupt = geometryDocument();
  corrupt.paths = [];
  const controller = createGeometryEvidenceController({
    elements: fixture.elements,
    request: async () => corrupt,
    renderEvidence: () => assert.fail("corrupt evidence must not render"),
  });
  controller.sync(reviewWithReference(pathRef(SHA_A)));
  await tick();
  assert.equal(fixture.elements.geometryEvidenceStatus.dataset.kind, "error");
  assert.match(fixture.elements.geometryEvidenceStatus.textContent, /不存在/);
  assert.equal(fixture.elements.geometryEvidenceRetryBtn.hidden, false);
});
