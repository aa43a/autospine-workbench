import assert from "node:assert/strict";
import test from "node:test";

import {
  createCaptureFramingConfirmation, describeCaptureFramingDecision,
} from "../modules/body-sway-capture-framing-confirmation.js";
import { probeEntryFixture } from "./body-sway-probe-fixtures.mjs";

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.disabled = false;
    this.focused = false;
    this.isConnected = true;
    this.returnValue = "";
    this.textContent = "";
  }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close(value = "") {
    this.returnValue = value;
    this.open = false;
    this.dispatchEvent(new Event("close"));
  }
}

function setup() {
  const ids = [
    "captureFramingDialog", "captureFramingDialogProject", "captureFramingDialogMotion",
    "captureFramingDialogAction", "captureFramingDialogConsequence",
    "cancelCaptureFraming", "commitCaptureFraming",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement()]));
  return { elements, controller: createCaptureFramingConfirmation({ elements }) };
}

test("all framing actions explain their project, action, and consequence", () => {
  const entry = probeEntryFixture();
  for (const action of ["accept", "reject", "unobservable"]) {
    const summary = describeCaptureFramingDecision(entry, action);
    assert.equal(summary.project, "seethrough_output_5");
    assert.match(summary.motion, /wave-left-v1/);
    assert.ok(summary.action.length >= 4);
    assert.match(summary.consequence, /记录|预览|发布权/);
  }
  assert.throws(() => describeCaptureFramingDecision(entry, "adjust"), /缺少/);
});

test("cancel sends nothing and confirm resolves only through the custom dialog", async () => {
  const first = setup();
  const invoker = new FakeElement();
  const cancelled = first.controller.request({
    entry: probeEntryFixture(), action: "accept", invoker,
  });
  first.elements.cancelCaptureFraming.dispatchEvent(new Event("click"));
  assert.equal(await cancelled, false);
  await Promise.resolve();
  assert.equal(invoker.focused, true);

  const second = setup();
  const confirmed = second.controller.request({
    entry: probeEntryFixture(), action: "reject",
  });
  second.elements.commitCaptureFraming.dispatchEvent(new Event("click"));
  assert.equal(await confirmed, true);
  assert.equal(second.elements.commitCaptureFraming.disabled, true);
});

test("Escape and backdrop both cancel without confirmation", async () => {
  for (const kind of ["cancel", "click"]) {
    const { elements, controller } = setup();
    const result = controller.request({ entry: probeEntryFixture(), action: "unobservable" });
    const event = new Event(kind, { cancelable: true });
    elements.captureFramingDialog.dispatchEvent(event);
    assert.equal(await result, false);
  }
});
