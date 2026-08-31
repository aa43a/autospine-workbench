import assert from "node:assert/strict";
import test from "node:test";

import { CaptureFramingApiError } from "../modules/body-sway-capture-framing-api.js";
import { createCaptureFramingController } from "../modules/body-sway-capture-framing-controller.js";
import { normalizeProbeEntry } from "../modules/body-sway-probe-contract.js";
import { PACKAGE_B, probeEntryFixture } from "./body-sway-probe-fixtures.mjs";

class FakeElement extends EventTarget {
  constructor(ownerDocument) {
    super();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.attributes = {};
  }
  replaceChildren(...nodes) { this.children = nodes; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  toggleAttribute(name, force) { this.attributes[name] = Boolean(force); }
}

function setup({ confirmed = true, submit = null } = {}) {
  const document = { createElement: () => new FakeElement(document) };
  const ids = [
    "captureFramingPanel", "captureFramingBadge", "captureFramingMessage",
    "captureFramingCoverage", "captureFramingWitnesses", "captureFramingStatus",
    "acceptCaptureFraming", "rejectCaptureFraming", "unobservableCaptureFraming",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement(document)]));
  const calls = [];
  const reloads = [];
  const controller = createCaptureFramingController({
    elements,
    confirmation: { request: async (request) => { calls.push(["confirm", request.action]); return confirmed; } },
    api: { submit: submit || (async (packageId, payload) => {
      calls.push(["submit", packageId, payload]);
      return {
        format: "autospine-capture-framing-receipt", format_version: 1,
        status: "recorded", package_id: packageId,
        candidate_sha256: payload.candidate_sha256, action: payload.action, revision: 1,
      };
    }) },
    onReload: async (prefix) => { reloads.push(prefix); },
  });
  return { controller, elements, calls, reloads };
}

function entry() {
  return normalizeProbeEntry(probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  }), PACKAGE_B);
}

test("framing view presents three covered domains and at most four readable witnesses", () => {
  const { controller, elements } = setup();
  controller.load(entry());
  assert.equal(elements.captureFramingPanel.hidden, false);
  assert.deepEqual(elements.captureFramingCoverage.children.map((card) =>
    card.children[1].textContent), ["已覆盖", "已覆盖", "已覆盖"]);
  assert.equal(elements.captureFramingWitnesses.children.length, 4);
  for (const card of elements.captureFramingWitnesses.children) {
    assert.match(card.children[1].textContent, /责任附件/);
    assert.match(card.children[2].textContent, /时刻/);
    assert.doesNotMatch(card.textContent, /SHA|坐标/);
  }
});

test("cancel never posts; confirmed acceptance posts the proposal and reloads", async () => {
  const cancelled = setup({ confirmed: false });
  cancelled.controller.load(entry());
  assert.equal(await cancelled.controller.submit("accept"), false);
  assert.deepEqual(cancelled.calls, [["confirm", "accept"]]);

  const accepted = setup();
  accepted.controller.load(entry());
  assert.equal(await accepted.controller.submit("accept"), true);
  const post = accepted.calls.find((row) => row[0] === "submit");
  assert.equal(post[1], PACKAGE_B);
  assert.equal(post[2].explicit_confirmation, true);
  assert.equal(post[2].action, "accept");
  assert.ok(post[2].world_viewport.width > 0);
  assert.equal(accepted.reloads.length, 1);
});

test("revision conflict refreshes exact history automatically", async () => {
  const reloaded = setup({
    submit: async () => {
      throw new CaptureFramingApiError("stale", 409, { error: "conflict" });
    },
  });
  reloaded.controller.load(entry());
  assert.equal(await reloaded.controller.submit("reject"), false);
  assert.equal(reloaded.reloads.length, 1);
  assert.match(reloaded.reloads[0], /历史已变化/);
});
