import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyEvidenceView } from "../modules/motion-policy-evidence-view.js";

class FakeElement extends EventTarget {
  constructor(ownerDocument, tagName = "div") {
    super();
    this.ownerDocument = ownerDocument;
    this.tagName = tagName;
    this.attributes = {};
    this.children = [];
    this.dataset = {};
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
  removeAttribute(name) { delete this.attributes[name]; }
  getBoundingClientRect() { return { left: 0, width: 1000 }; }
}

function elements() {
  const document = {
    createElement: (tag) => new FakeElement(document, tag),
    createElementNS: (_namespace, tag) => new FakeElement(document, tag),
  };
  return Object.fromEntries([
    "evidenceSummary", "frameLabel", "metricChart", "frameScrubber", "attentionList",
    "metricTableBody", "characterComposite", "footOverlay", "overlayEmpty", "frameState",
    "frameFacts", "observationBody",
  ].map((key) => [key, new FakeElement(document, key === "characterComposite" ? "img" : "div")]));
}

function model() {
  const samples = Array.from({ length: 5 }, (_, index) => ({
    sampleIndex: index,
    sourceFrameIndex: 10 + index,
    tick: index * 100,
    state: "candidate",
    supportState: "single_support",
    activeContactIds: [`contact-${index}`],
    candidateId: `foot-${index}`,
    correctionX: index,
    correctionY: -index,
    maximumResidualPx: 1,
    correctionReferenceRatio: 0.1,
    observations: [],
  }));
  return {
    projectId: "sample-a",
    samples,
    metrics: {
      correctionX: { minimum: 0, maximum: 4 },
      correctionY: { minimum: -4, maximum: 0 },
      maximumResidualPx: { minimum: 1, maximum: 1 },
      correctionReferenceRatio: { minimum: 0.1, maximum: 0.1 },
    },
    contractLimits: { maximumResidualPx: 8, correctionReferenceRatio: 0.5 },
    attentionWindows: [],
  };
}

test("many timeline input events commit one closed range only when the gesture ends", () => {
  const ui = elements();
  const candidates = [];
  const ranges = [];
  const view = createMotionPolicyEvidenceView(ui, {
    onFrameCandidate: (id) => candidates.push(id),
    onFrameRange: (start, end, detail) => ranges.push({ start, end, detail }),
  });
  view.load(model());

  ui.frameScrubber.dispatchEvent(new Event("pointerdown"));
  ui.frameScrubber.value = "2";
  ui.frameScrubber.dispatchEvent(new Event("input"));
  ui.frameScrubber.value = "4";
  ui.frameScrubber.dispatchEvent(new Event("input"));

  assert.equal(ui.frameLabel.textContent, "frame 14 · tick 400");
  assert.deepEqual(ranges, []);
  assert.deepEqual(candidates, []);

  ui.frameScrubber.dispatchEvent(new Event("change"));
  assert.deepEqual(ranges, [{ start: 0, end: 4, detail: { trigger: "timeline" } }]);
  assert.deepEqual(candidates, []);
});

test("programmatic frame selection is non-authoritative and a reverse keyboard gesture keeps both endpoints", () => {
  const ui = elements();
  const ranges = [];
  const view = createMotionPolicyEvidenceView(ui, {
    onFrameRange: (start, end) => ranges.push([start, end]),
  });
  view.load(model());

  view.selectFrame(4);
  assert.deepEqual(ranges, []);
  ui.frameScrubber.dispatchEvent(new Event("keydown"));
  ui.frameScrubber.value = "1";
  ui.frameScrubber.dispatchEvent(new Event("input"));
  ui.frameScrubber.dispatchEvent(new Event("change"));

  assert.deepEqual(ranges, [[4, 1]]);
  assert.equal(ui.frameScrubber.value, "1");
});
