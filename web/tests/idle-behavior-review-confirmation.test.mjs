import assert from "node:assert/strict";
import test from "node:test";

import {
  createIdleDecisionConfirmation, describeIdleDecision,
} from "../modules/idle-behavior-review-confirmation.js";
import { entryDocument } from "./idle-behavior-review-fixtures.mjs";

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.disabled = false;
    this.focused = false;
    this.isConnected = true;
    this.open = false;
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
  const elements = Object.fromEntries([
    "decisionDialog", "decisionDialogProject", "decisionDialogMotion",
    "decisionDialogAction", "decisionDialogConsequence",
    "cancelDecision", "commitDecision",
  ].map((id) => [id, new FakeElement()]));
  return { elements, controller: createIdleDecisionConfirmation({ elements }) };
}

test("all decisions expose project, motion, type, and consequence", () => {
  const entry = entryDocument();
  for (const action of ["adjust", "reject", "unobservable"]) {
    const summary = describeIdleDecision(entry, action);
    assert.equal(summary.project, "seethrough_output");
    assert.equal(summary.motion, "kimodo-idle · idle-001");
    assert.ok(summary.action.length > 4);
    assert.match(summary.consequence, /revision|证据/);
  }
  assert.throws(() => describeIdleDecision(entry, "accept"), /未知/);
});

test("cancel sends no confirmation and restores the invoking button focus", async () => {
  const { elements, controller } = setup();
  const invoker = new FakeElement();
  const result = controller.request({ entry: entryDocument(), action: "adjust", invoker });
  assert.equal(elements.cancelDecision.focused, true);
  assert.equal(elements.decisionDialogProject.textContent, "seethrough_output");
  elements.cancelDecision.dispatchEvent(new Event("click"));
  assert.equal(await result, false);
  await Promise.resolve();
  assert.equal(invoker.focused, true);
});

test("Escape and backdrop cancel, while confirm resolves once", async () => {
  for (const cancelWith of ["escape", "backdrop"]) {
    const { elements, controller } = setup();
    const result = controller.request({ entry: entryDocument(), action: "reject" });
    if (cancelWith === "escape") {
      const event = new Event("cancel", { cancelable: true });
      elements.decisionDialog.dispatchEvent(event);
      assert.equal(event.defaultPrevented, true);
    } else {
      elements.decisionDialog.dispatchEvent(new Event("click"));
    }
    assert.equal(await result, false);
  }

  const { elements, controller } = setup();
  const result = controller.request({ entry: entryDocument(), action: "unobservable" });
  const duplicate = controller.request({ entry: entryDocument(), action: "adjust" });
  elements.commitDecision.dispatchEvent(new Event("click"));
  elements.commitDecision.dispatchEvent(new Event("click"));
  assert.equal(await result, true);
  assert.equal(await duplicate, false);
  assert.equal(elements.commitDecision.disabled, true);
});
