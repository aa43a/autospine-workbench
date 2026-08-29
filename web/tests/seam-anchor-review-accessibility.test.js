import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { appendTextElement, restoreSeamFocus } from "../modules/seam-anchor-review-markup.js";
import { seamReviewKeyboardIntent } from "../modules/seam-anchor-review-keyboard.js";
import { createSeamReviewInteractions } from "../modules/seam-anchor-review-interactions.js";
import { createSeamReviewState } from "../modules/seam-anchor-review-state.js";
import { setSeamDraftDisabled } from "../modules/seam-anchor-review-view.js";

function keyEvent(key, target = { tagName: "DIV" }, extra = {}) {
  return {
    key, target, defaultPrevented: false, isComposing: false, keyCode: 0,
    ctrlKey: false, altKey: false, metaKey: false, ...extra,
  };
}

test("keyboard shortcuts are guarded in editable and IME contexts", () => {
  for (const tagName of ["INPUT", "TEXTAREA", "SELECT"]) {
    assert.equal(seamReviewKeyboardIntent(keyEvent("1", { tagName })), null);
  }
  for (const tagName of ["A", "BUTTON", "DETAILS", "SUMMARY"]) {
    assert.equal(seamReviewKeyboardIntent(keyEvent("ArrowDown", { tagName })), null);
  }
  assert.equal(seamReviewKeyboardIntent(keyEvent("4", {
    tagName: "DIV", isContentEditable: true,
  })), null);
  assert.equal(seamReviewKeyboardIntent(keyEvent("2", { tagName: "DIV" }, {
    isComposing: true,
  })), null);
  assert.deepEqual(seamReviewKeyboardIntent(keyEvent("ArrowDown")), {
    type: "move", delta: 1,
  });
  assert.deepEqual(seamReviewKeyboardIntent(keyEvent("2")), {
    type: "decide", action: "adjust",
  });
  assert.deepEqual(seamReviewKeyboardIntent(keyEvent(
    "Enter", { tagName: "TEXTAREA" }, { ctrlKey: true },
  )), { type: "submit" });
});

test("relationship navigation restores focus and honors reduced motion", () => {
  const cards = ["a", "b"].map((relationshipId) => ({
    dataset: { relationshipId }, focused: false, scrolled: null,
    focus() { this.focused = true; },
    scrollIntoView(options) { this.scrolled = options; },
    querySelector: () => null,
  }));
  const container = { querySelectorAll: () => cards };
  assert.equal(restoreSeamFocus(container, "b"), true);
  assert.equal(cards[1].focused, true);
  let state = {
    ...createSeamReviewState(), candidate: { relationships: [] },
    currentRelationshipId: "a",
  };
  const interactions = createSeamReviewInteractions({
    container, submitButton: { disabled: true }, getState: () => state,
    setState: (next) => { state = next; }, onChange: () => {}, onRender: () => {},
    onAnchorValidity: () => {}, onAnnounce: () => {}, onError: assert.fail,
    onSubmit: assert.fail, prefersReducedMotion: () => true,
  });
  const event = keyEvent("ArrowRight");
  event.preventDefault = () => {};
  interactions.handleKeyboard(event);
  assert.equal(state.currentRelationshipId, "b");
  assert.deepEqual(cards[1].scrolled, { block: "nearest", behavior: "auto" });
});

test("mutation lock freezes every authored control and synthetic shortcut", () => {
  const elements = {
    reviewRelationships: { inert: false }, reviewerId: { disabled: false },
    reviewNotes: { disabled: false },
  };
  setSeamDraftDisabled(elements, true);
  assert.equal(elements.reviewRelationships.inert, true);
  assert.equal(elements.reviewerId.disabled, true);
  assert.equal(elements.reviewNotes.disabled, true);

  let clicked = 0;
  const card = {
    dataset: { relationshipId: "a" }, focus: () => {}, scrollIntoView: () => {},
    querySelector: () => ({ disabled: false, click: () => { clicked += 1; } }),
  };
  const container = { querySelectorAll: () => [card] };
  const state = {
    ...createSeamReviewState(), candidate: { relationships: [] },
    currentRelationshipId: "a",
  };
  const interactions = createSeamReviewInteractions({
    container, submitButton: { disabled: false }, getState: () => state,
    setState: () => {}, onChange: () => {}, onRender: () => {},
    onAnchorValidity: () => {}, onAnnounce: () => {}, onError: assert.fail,
    onSubmit: assert.fail, isLocked: () => true,
  });
  const event = keyEvent("1");
  event.preventDefault = () => { event.defaultPrevented = true; };
  interactions.handleKeyboard(event);
  assert.equal(event.defaultPrevented, false);
  assert.equal(clicked, 0);
});

test("DOM helper treats untrusted labels only as text", () => {
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
});

test("static page exposes structured evidence, semantic controls, and responsive guards", async () => {
  const root = new URL("../", import.meta.url);
  const [html, baseCss, entryCss, markup, evidence, entryView, entryContract, entryFlow] = await Promise.all([
    readFile(new URL("seam-anchor-review.html", root), "utf8"),
    readFile(new URL("seam-anchor-review.css", root), "utf8"),
    readFile(new URL("seam-anchor-review-entry.css", root), "utf8"),
    readFile(new URL("modules/seam-anchor-review-markup.js", root), "utf8"),
    readFile(new URL("modules/seam-anchor-review-evidence.js", root), "utf8"),
    readFile(new URL("modules/seam-anchor-review-entry-view.js", root), "utf8"),
    readFile(new URL("modules/seam-anchor-review-entry.js", root), "utf8"),
    readFile(new URL("modules/seam-anchor-review-entry-flow.js", root), "utf8"),
  ]);
  const css = `${baseCss}\n${entryCss}`;
  assert.match(html, /<meta name="viewport"/);
  assert.match(html, /id="entryStatus"[^>]*role="status"/s);
  assert.match(html, /id="entryBlockers"/);
  assert.match(html, /<details id="expertAddressDetails"[^>]*class="expert-address"/);
  assert.match(html, /专业模式：手动输入项目与四项 exact 地址/);
  assert.match(html, /id="reviewRelationships"[^>]*tabindex="-1"/s);
  assert.match(html, /<label>/);
  assert.match(markup, /createElement\("fieldset"\)/);
  assert.match(markup, /完整 final_anchors JSON/);
  assert.match(markup, /aria-describedby/);
  assert.match(evidence, /Contact evidence/);
  assert.match(evidence, /parent_attachment_type/);
  assert.match(evidence, /anchorTable/);
  assert.match(evidence, /setup alpha 证据/);
  assert.match(evidence, /选择 \$\{option\.option_id\}/);
  assert.equal(markup.includes("innerHTML"), false);
  assert.equal(evidence.includes("innerHTML"), false);
  assert.equal(entryView.includes("innerHTML"), false);
  assert.equal(entryContract.includes("innerHTML"), false);
  assert.equal(entryFlow.includes("innerHTML"), false);
  assert.match(entryView, /不会自动 accept 或生成 fallback/);
  assert.match(css, /min-height: 44px/);
  assert.match(css, /\.entry-blockers/);
  assert.match(css, /@media \(max-width: 420px\)/);
  assert.match(css, /minmax\(0, 1fr\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /:focus-visible/);
});
