import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildSeriesPath,
  createMotionPolicyEvidenceView,
} from "../modules/motion-policy-evidence-view.js";

const SVG_NS = "http://www.w3.org/2000/svg";

class FakeElement extends EventTarget {
  constructor(ownerDocument, tagName, namespace = null) {
    super();
    this.ownerDocument = ownerDocument;
    this.tagName = tagName;
    this.namespace = namespace;
    this.attributes = {};
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.value = "";
    this.naturalWidth = 0;
    this.naturalHeight = 0;
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; if (name === "src") this.src = ""; }
  getBoundingClientRect() { return { left: 0, width: 1000 }; }
}

function fixture() {
  const document = {
    createElement: (tag) => new FakeElement(document, tag),
    createElementNS: (namespace, tag) => new FakeElement(document, tag, namespace),
  };
  const elements = Object.fromEntries([
    "evidenceSummary", "frameLabel", "metricChart", "frameScrubber", "attentionList",
    "metricTableBody", "characterComposite", "footOverlay", "overlayEmpty", "frameState",
    "frameFacts", "observationBody",
  ].map((key) => [key, new FakeElement(document, key === "characterComposite" ? "img" : "div")]));
  elements.metricChart = new FakeElement(document, "svg", SVG_NS);
  elements.footOverlay = new FakeElement(document, "svg", SVG_NS);
  return elements;
}

function model() {
  return {
    projectId: "sample A/角色",
    samples: [
      {
        sampleIndex: 0,
        sourceFrameIndex: 20,
        tick: 666667,
        state: "candidate",
        supportState: "dual_support",
        activeContactIds: ["contact-left"],
        candidateId: "foot-20",
        correctionX: 2,
        correctionY: -1,
        maximumResidualPx: 1,
        correctionReferenceRatio: 0.1,
        observations: [{
          contact_id: "contact-left",
          limb: "left_foot",
          current_endpoint_px: [10, 20],
          desired_correction_px: [3, -1],
          residual_magnitude_px: 1,
        }],
      },
      {
        sampleIndex: 1,
        sourceFrameIndex: 21,
        tick: 700000,
        state: "unconstrained",
        supportState: "none",
        activeContactIds: [],
        candidateId: null,
        correctionX: null,
        correctionY: null,
        maximumResidualPx: null,
        correctionReferenceRatio: null,
        observations: [],
      },
      {
        sampleIndex: 2,
        sourceFrameIndex: 22,
        tick: 733333,
        state: "candidate",
        supportState: "single_support",
        activeContactIds: ["contact-right"],
        candidateId: "foot-22",
        correctionX: -2,
        correctionY: 0.5,
        maximumResidualPx: 2,
        correctionReferenceRatio: 0.2,
        observations: [{
          contactId: "contact-right",
          limb: "right_foot",
          currentEndpointPx: [30, 40],
          desiredCorrectionPx: [-1, 2],
          residualMagnitudePx: 2,
        }],
      },
    ],
    metrics: {
      correctionX: { minimum: -2, maximum: 2 },
      correctionY: { minimum: -1, maximum: 0.5 },
      maximumResidualPx: { minimum: 1, maximum: 2 },
      correctionReferenceRatio: { minimum: 0.1, maximum: 0.2 },
    },
    contractLimits: { maximumResidualPx: 8, correctionReferenceRatio: 0.25 },
    attentionWindows: [{
      startSampleIndex: 2,
      endSampleIndex: 2,
      startFrame: 22,
      endFrame: 22,
      reasons: ["p95:maximumResidualPx"],
    }],
  };
}

function descendants(element) {
  return [element, ...element.children.flatMap((child) => descendants(child))];
}

test("module owns SVG namespace and never uses unsafe HTML", async () => {
  const source = await readFile(new URL("../modules/motion-policy-evidence-view.js", import.meta.url), "utf8");
  assert.match(source, /const SVG_NS = "http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);

  const elements = fixture();
  createMotionPolicyEvidenceView(elements).load(model());
  const svgNodes = descendants(elements.metricChart).filter((item) => item !== elements.metricChart);
  assert.ok(svgNodes.length > 5);
  assert.ok(svgNodes.every((item) => item.namespace === SVG_NS));
});

test("a null sample breaks every timeline instead of becoming a zero point", () => {
  const path = buildSeriesPath([1, null, -1], (index) => index * 10, (value) => 50 - value * 10);
  assert.equal(path, "M0,40 M20,60");
  assert.doesNotMatch(path, /L20/);
});

test("load URL-encodes project identity and renders an accessible numeric table", () => {
  const elements = fixture();
  createMotionPolicyEvidenceView(elements).load(model());

  assert.equal(elements.characterComposite.src, "/api/projects/sample%20A%2F%E8%A7%92%E8%89%B2/composite");
  assert.equal(elements.metricTableBody.children.length, 4);
  assert.deepEqual(
    elements.metricTableBody.children.map((row) => row.children[0].textContent),
    ["Correction X (px)", "Correction Y (px)", "Maximum residual (px)", "Correction / reference"],
  );
  assert.equal(elements.metricTableBody.children[2].children[3].textContent, "25.0%");
});

test("frame selection updates facts, table, overlay, scrubber, and candidate callback", () => {
  const elements = fixture();
  const focused = [];
  const view = createMotionPolicyEvidenceView(elements, {
    onFrameCandidate: (candidateId) => focused.push(candidateId),
  });
  view.load(model());
  elements.characterComposite.naturalWidth = 100;
  elements.characterComposite.naturalHeight = 200;
  elements.characterComposite.dispatchEvent(new Event("load"));

  assert.equal(elements.footOverlay.attributes.viewBox, "0 0 100 200");
  assert.equal(elements.observationBody.children[0].children[2].textContent, "12.000, 19.000");
  assert.equal(elements.observationBody.children[0].children[3].textContent, "13.000, 19.000");
  assert.ok(descendants(elements.footOverlay).some((item) => item.attributes.class === "foot-residual-line"));

  view.selectFrame(1);
  assert.equal(elements.frameLabel.textContent, "frame 21 · tick 700000");
  assert.equal(elements.overlayEmpty.hidden, false);
  assert.match(elements.overlayEmpty.textContent, /没有可绘制/);
  assert.equal(elements.observationBody.children[0].children[0].attributes.colspan, "5");
  assert.deepEqual(focused, []);

  elements.frameScrubber.value = "2";
  elements.frameScrubber.dispatchEvent(new Event("input"));
  assert.equal(elements.frameLabel.textContent, "frame 22 · tick 733333");
  assert.deepEqual(focused, ["foot-22"]);
});

test("attention button locates its window and clear returns the view to a waiting state", () => {
  const elements = fixture();
  const focused = [];
  const view = createMotionPolicyEvidenceView(elements, { onFrameCandidate: (id) => focused.push(id) });
  view.load(model());
  elements.attentionList.children[0].dispatchEvent(new Event("click"));
  assert.equal(elements.frameScrubber.value, "2");
  assert.deepEqual(focused, ["foot-22"]);

  view.clear();
  assert.equal(elements.metricChart.children.length, 0);
  assert.equal(elements.frameLabel.textContent, "frame —");
  assert.equal(elements.frameScrubber.disabled, true);
  assert.match(elements.overlayEmpty.textContent, /等待角色图/);
});
