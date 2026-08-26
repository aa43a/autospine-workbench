import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { createCaseInteractions } from "../modules/body-sway-review-cases.js";
import { reviewKeyboardIntent } from "../modules/body-sway-review-keyboard.js";
import {
  appendTextElement, restoreCaseFocus,
} from "../modules/body-sway-review-markup.js";
import { createReviewState } from "../modules/body-sway-review-state.js";
import { setDraftControlsDisabled } from "../modules/body-sway-review-view.js";


function keyEvent(key, target = { tagName: "DIV" }, extra = {}) {
  return { key, target, defaultPrevented: false, isComposing: false,
    keyCode: 0, ctrlKey: false, altKey: false, metaKey: false, ...extra };
}

test("keyboard shortcuts are guarded in editable and IME contexts", () => {
  for (const tagName of ["INPUT", "TEXTAREA", "SELECT"]) {
    assert.equal(reviewKeyboardIntent(keyEvent("1", { tagName })), null);
  }
  assert.equal(reviewKeyboardIntent(keyEvent("ArrowRight", {
    tagName: "DIV", isContentEditable: true,
  })), null);
  assert.equal(reviewKeyboardIntent(keyEvent("1", { tagName: "DIV" }, {
    isComposing: true,
  })), null);
  assert.deepEqual(reviewKeyboardIntent(keyEvent("ArrowDown")), { type: "move", delta: 1 });
  assert.deepEqual(reviewKeyboardIntent(keyEvent("2")), { type: "decide", action: "reject" });
  assert.deepEqual(reviewKeyboardIntent(keyEvent("Enter", { tagName: "TEXTAREA" }, {
    ctrlKey: true,
  })), { type: "submit" });
});

test("case navigation restores focus by case_id and respects reduced motion", () => {
  const cards = ["setup", "combined-t001000000"].map((caseId) => ({
    dataset: { caseId }, focused: false, scrolled: null,
    focus() { this.focused = true; },
    scrollIntoView(options) { this.scrolled = options; },
    querySelector: () => null,
  }));
  const container = { querySelectorAll: () => cards };
  assert.equal(restoreCaseFocus(container, "combined-t001000000"), true);
  assert.equal(cards[1].focused, true);

  let state = { ...createReviewState(), candidate: { cases: [] }, currentCaseId: "setup" };
  const interactions = createCaseInteractions({
    container, submitButton: { disabled: true }, getState: () => state,
    setState: (next) => { state = next; }, onChange: () => {},
    onAnnounce: () => {}, onError: assert.fail, onSubmit: assert.fail,
    prefersReducedMotion: () => true,
  });
  const event = keyEvent("ArrowRight");
  event.preventDefault = () => {};
  interactions.handleKeyboard(event);
  assert.equal(state.currentCaseId, "combined-t001000000");
  assert.deepEqual(cards[1].scrolled, { block: "nearest", behavior: "auto" });
});

test("mutation lock blocks synthetic shortcuts and draft changes", () => {
  let locked = true;
  let clicks = 0;
  let changes = 0;
  const card = {
    dataset: { caseId: "setup" }, focus: () => {}, scrollIntoView: () => {},
    querySelector: () => ({ click: () => { clicks += 1; } }),
  };
  const container = {
    querySelectorAll(selector) {
      return selector === ".review-case" ? [card] : [];
    },
  };
  let state = { ...createReviewState(), candidate: { cases: [] }, currentCaseId: "setup" };
  const interactions = createCaseInteractions({
    container, submitButton: { disabled: false }, getState: () => state,
    setState: (next) => { state = next; }, onChange: () => { changes += 1; },
    onAnnounce: () => {}, onError: assert.fail, onSubmit: assert.fail,
    isLocked: () => locked,
  });
  const event = keyEvent("2");
  event.preventDefault = () => { event.defaultPrevented = true; };
  interactions.handleKeyboard(event);
  interactions.updateDraft({
    dataset: { caseNotes: "setup" }, value: "must stay frozen",
  });
  assert.equal(event.defaultPrevented, false);
  assert.equal(clicks, 0);
  assert.equal(changes, 0);

  locked = false;
  interactions.handleKeyboard(event);
  assert.equal(event.defaultPrevented, true);
  assert.equal(clicks, 1);
});

test("DOM helper assigns untrusted labels through textContent", () => {
  class FakeElement {
    constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; }
    append(child) { this.children.push(child); }
  }
  const parent = new FakeElement("div");
  const doc = { createElement: (tag) => new FakeElement(tag) };
  const malicious = "<img src=x onerror=alert(1)>";
  const child = appendTextElement(doc, parent, "span", "label", malicious);
  assert.equal(child.textContent, malicious);
  assert.equal(child.children.length, 0);
  assert.equal(parent.children[0], child);
});

test("submission freezes every user-authored draft control", () => {
  const elements = {
    reviewCases: { inert: false },
    reviewerId: { disabled: false },
    reviewNotes: { disabled: false },
  };
  setDraftControlsDisabled(elements, true);
  assert.equal(elements.reviewCases.inert, true);
  assert.equal(elements.reviewerId.disabled, true);
  assert.equal(elements.reviewNotes.disabled, true);
  setDraftControlsDisabled(elements, false);
  assert.equal(elements.reviewCases.inert, false);
  assert.equal(elements.reviewerId.disabled, false);
  assert.equal(elements.reviewNotes.disabled, false);
});

test("static contracts cover semantic controls, narrow screens, and reduced motion", async () => {
  const root = new URL("../", import.meta.url);
  const [html, css, markup] = await Promise.all([
    readFile(new URL("body-sway-review.html", root), "utf8"),
    readFile(new URL("body-sway-review.css", root), "utf8"),
    readFile(new URL("modules/body-sway-review-markup.js", root), "utf8"),
  ]);
  assert.match(html, /<meta name="viewport"/);
  assert.match(html, /<label>/);
  assert.match(html, /id="reviewCases"[^>]*tabindex="-1"/);
  assert.match(markup, /createElement\("fieldset"\)/);
  assert.match(markup, /appendTextElement\(doc, fieldset, "legend"/);
  assert.equal(markup.includes("innerHTML"), false);
  assert.match(markup, /\.textContent =/);
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.match(css, /\[hidden\] \{ display: none !important; \}/);
  assert.match(css, /minmax\(0, 1fr\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /:focus-visible/);
});
