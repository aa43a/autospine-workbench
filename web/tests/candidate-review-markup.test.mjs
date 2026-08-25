import assert from "node:assert/strict";
import test from "node:test";

import {
  CANDIDATE_REVIEW_ELEMENT_IDS,
  mountCandidateReview,
} from "../modules/candidate-review-markup.js";

class FakeElement {
  constructor(ownerDocument, tagName) {
    this.ownerDocument = ownerDocument;
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.hidden = false;
    this.textContent = "";
    this.replacement = null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === "id") this.ownerDocument.elements.set(String(value), this);
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceWith(element) {
    this.replacement = element;
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
  }

  createElement(tagName) {
    return new FakeElement(this, tagName);
  }

  createElementNS(_namespace, tagName) {
    return this.createElement(tagName);
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

test("candidate review mounts a complete static and accessible subtree", () => {
  const doc = new FakeDocument();
  const mount = doc.createElement("div");
  mount.setAttribute("id", "candidateReviewMount");

  const section = mountCandidateReview(doc);

  assert.equal(mount.replacement, section);
  assert.equal(section.tagName, "SECTION");
  assert.equal(section.getAttribute("aria-labelledby"), "candidateReviewHeading");
  assert.deepEqual(
    CANDIDATE_REVIEW_ELEMENT_IDS.filter((id) => !doc.getElementById(id)),
    [],
  );
  assert.equal(doc.getElementById("candidateLoadState").getAttribute("aria-live"), "polite");
  assert.equal(doc.getElementById("candidateDecisionStatus").getAttribute("role"), "status");
  assert.equal(doc.getElementById("candidateRetryBtn").hidden, true);
  assert.equal(doc.getElementById("candidateReason").getAttribute("maxlength"), "1000");
});

test("mount is idempotent and leaves an existing review untouched", () => {
  const existing = {};
  const root = { getElementById: (id) => id === "candidateReview" ? existing : null };
  assert.equal(mountCandidateReview(root), existing);
  assert.equal(new Set(CANDIDATE_REVIEW_ELEMENT_IDS).size, CANDIDATE_REVIEW_ELEMENT_IDS.length);
});
