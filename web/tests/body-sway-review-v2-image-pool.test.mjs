import assert from "node:assert/strict";
import test from "node:test";

import {
  createTimelineImagePool, waitForVisibleTimelineGroup,
} from "../modules/body-sway-review-v2-image-pool.js";

const SHA = (value) => value.repeat(64);

function row(caseId, digest, animation = "p10.base") {
  return {
    case_id: caseId, animation, time_seconds: 0,
    image: { png_sha256: SHA(digest), width: 640, height: 640 },
  };
}

function fakeDocument() {
  const images = [];
  return {
    images,
    createElement(tag) {
      assert.equal(tag, "img");
      const listeners = new Map();
      const image = {
        dataset: {}, assignments: 0,
        addEventListener(type, listener) { listeners.set(type, listener); },
        fire(type) { listeners.get(type)?.(); },
        set src(value) { this._src = value; this.assignments += 1; },
        get src() { return this._src; },
      };
      images.push(image);
      return image;
    },
  };
}

test("one exact URL receives one img and one src assignment for the page lifetime", async () => {
  const doc = fakeDocument();
  const url = (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`;
  const pool = createTimelineImagePool({ doc, imageUrl: url });
  const setup = row("setup", "1", null);
  const [image] = pool.focus([setup]);
  assert.equal(image.assignments, 1);
  image.fire("load");
  assert.deepEqual(await pool.waitFor([setup]), ["loaded"]);
  assert.equal(pool.focus([setup])[0], image);
  assert.equal(image.assignments, 1);
  assert.equal(doc.images.length, 1);
});

test("current pair is bounded to two requests and adjacent work stays queued", () => {
  const doc = fakeDocument();
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`,
  });
  const current = [row("base-0", "1"), row("sway-0", "2", "p10.body-sway")];
  const next = [row("base-1", "3"), row("sway-1", "4", "p10.body-sway")];
  pool.focus(current);
  pool.prime(next);
  assert.deepEqual(pool.stats(), { entries: 4, active: 2, queued: 2 });
  doc.images[0].fire("load");
  assert.deepEqual(pool.stats(), { entries: 4, active: 2, queued: 1 });
});

test("a failed image gets one controlled revisit retry and never loops", async () => {
  const doc = fakeDocument();
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`,
  });
  const sample = row("base-0", "1");
  const [image] = pool.focus([sample]);
  image.fire("error");
  assert.deepEqual(await pool.waitFor([sample]), ["error"]);
  const retry = pool.focus([sample])[0];
  assert.notEqual(retry, image);
  assert.equal(retry.assignments, 1);
  retry.fire("error");
  assert.deepEqual(await pool.waitFor([sample]), ["error"]);
  assert.equal(pool.focus([sample])[0], retry);
  assert.equal(retry.assignments, 1);
});

test("different candidate URLs never alias even when case and PNG match", () => {
  const doc = fakeDocument();
  let candidate = "candidate-a";
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/${candidate}/${item.case_id}/${item.image.png_sha256}`,
  });
  const sample = row("base-0", "1");
  pool.focus([sample]);
  candidate = "candidate-b";
  pool.focus([sample]);
  assert.equal(doc.images.length, 2);
  assert.equal(doc.images[0].assignments, 1);
  assert.equal(doc.images[1].assignments, 1);
});

test("focus supersedes stale queued prefetch instead of draining a backlog", async () => {
  const doc = fakeDocument();
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`,
  });
  const first = [row("base-0", "1"), row("sway-0", "2", "p10.body-sway")];
  const stale = [row("base-1", "3"), row("sway-1", "4", "p10.body-sway")];
  const target = [row("base-2", "5"), row("sway-2", "6", "p10.body-sway")];
  pool.focus(first);
  pool.prime(stale);
  const staleReady = pool.waitFor(stale);
  pool.focus(target);
  assert.deepEqual(await staleReady, ["superseded", "superseded"]);
  assert.deepEqual(pool.stats(), { entries: 4, active: 2, queued: 2 });
  doc.images[0].fire("load");
  doc.images[1].fire("load");
  assert.deepEqual(pool.stats(), { entries: 4, active: 2, queued: 0 });
});

test("loaded waits for decode and visibility waits for paint plus dwell", async () => {
  const doc = fakeDocument();
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`,
  });
  const sample = row("base-0", "1");
  const [image] = pool.focus([sample]);
  let finishDecode;
  image.decode = () => new Promise((resolve) => { finishDecode = resolve; });
  image.fire("load");
  let settled = false;
  const ready = pool.waitFor([sample]).then((value) => { settled = true; return value; });
  await Promise.resolve();
  assert.equal(settled, false);
  finishDecode();
  assert.deepEqual(await ready, ["loaded"]);

  const view = {
    requestAnimationFrame(callback) { callback(); },
    setTimeout(callback) { callback(); },
  };
  const container = {
    isConnected: true,
    ownerDocument: { defaultView: view, visibilityState: "visible" },
  };
  assert.equal(await waitForVisibleTimelineGroup(container, 0), true);
  container.ownerDocument.visibilityState = "hidden";
  assert.equal(await waitForVisibleTimelineGroup(container, 0), false);
});

test("dispose resolves queued and loading waiters without starting more work", async () => {
  const doc = fakeDocument();
  const pool = createTimelineImagePool({
    doc, imageUrl: (item) => `/candidate-a/${item.case_id}/${item.image.png_sha256}`,
  });
  const current = [row("base-0", "1"), row("sway-0", "2", "p10.body-sway")];
  const next = [row("base-1", "3"), row("sway-1", "4", "p10.body-sway")];
  pool.focus(current);
  pool.prime(next);
  const currentReady = pool.waitFor(current);
  const nextReady = pool.waitFor(next);
  pool.dispose();
  assert.deepEqual(await currentReady, ["disposed", "disposed"]);
  assert.deepEqual(await nextReady, ["disposed", "disposed"]);
  assert.deepEqual(pool.stats(), { entries: 0, active: 0, queued: 0 });
});
