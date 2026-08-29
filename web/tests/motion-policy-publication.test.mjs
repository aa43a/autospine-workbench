import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyPageLock } from "../modules/motion-policy-page-lock.js";
import { createMotionPolicyPublicationController } from "../modules/motion-policy-publication-controller.js";

const PACKAGE_A = "a".repeat(64);
const PACKAGE_B = "b".repeat(64);

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.attributes = {};
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  click() { this.dispatchEvent(new Event("click")); }
  querySelector(selector) {
    return selector === "small" ? this.small || null : null;
  }
  querySelectorAll(selector) {
    return selector === "[data-publish-phase]" ? this.children : [];
  }
  removeAttribute(name) { delete this.attributes[name]; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  toggleAttribute(name, force) {
    if (force) this.attributes[name] = "";
    else delete this.attributes[name];
  }
}

function uiDocument() {
  const ids = [
    "p9PublishPanel", "p9PublishBadge", "p9PublishSteps", "p9PublishStatus",
    "p9PublishReceipt", "p9ReceiptReuse", "p9ReceiptProject", "p9ReceiptMotion",
    "p9ReceiptClip", "p9ReceiptInstance", "p9ReceiptBundle", "p9NextProjectBtn",
    "p9NextProjectHint", "p9SeamReviewLink", "autoPublishBtn", "autoBackupBtn",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement()]));
  elements.p9PublishSteps.children = ["validate", "compile", "publish", "verify"].map((phase) => {
    const row = new FakeElement();
    row.dataset.publishPhase = phase;
    row.small = new FakeElement();
    return row;
  });
  return {
    elements,
    getElementById: (id) => elements[id],
    createElement: () => {
      const link = new FakeElement();
      link.click = () => {};
      return link;
    },
  };
}

function packageDetail(packageId = PACKAGE_A) {
  return {
    package_id: packageId, project_id: "sample-a",
    motion_id: "kimodo-wave", clip_id: "wave-left",
  };
}

function reviewInput() {
  return {
    review: { status: "approved", method: "human", revision: 1 },
    decisions: [], root_release_keys: [],
    draw_order_loop_reset: { mode: "explicit", approved: false },
  };
}

function receipt(overrides = {}) {
  return {
    packageId: PACKAGE_A,
    projectId: "sample-a",
    motionId: "kimodo-wave",
    clipId: "wave-left",
    reused: false,
    address: {
      projectId: "sample-a",
      motionInstanceV2Sha256: "1".repeat(64),
      bundleSha256: "2".repeat(64),
    },
    ...overrides,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

test("one final human click publishes, renders a path-free receipt, and offers the next sample", async () => {
  const doc = uiDocument();
  const calls = [];
  const continued = [];
  const locks = [];
  const controller = createMotionPolicyPublicationController(doc, {
    api: { adopt: async (...args) => { calls.push(args); return receipt(); } },
    buildReview: (options) => {
      assert.deepEqual(options, { authoritative: true });
      return { reviewInput: reviewInput(), filename: "sample-a.review.json" };
    },
    onPublished: () => ({ packageId: PACKAGE_B, projectId: "sample-b", motionId: "kimodo-wave" }),
    onContinue: async (packageId) => { continued.push(packageId); },
    onPublishingChange: (locked) => locks.push(locked),
  });
  controller.load(packageDetail());
  controller.setReady(true);

  doc.elements.autoPublishBtn.click();
  await flush();

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], PACKAGE_A);
  assert.equal(calls[0][1].review.method, "human");
  assert.deepEqual(calls[0][2].expected, {
    projectId: "sample-a", motionId: "kimodo-wave", clipId: "wave-left",
  });
  assert.deepEqual(locks, [true, false]);
  assert.equal(doc.elements.p9PublishReceipt.hidden, false);
  assert.equal(doc.elements.p9ReceiptProject.textContent, "sample-a");
  assert.equal(doc.elements.p9ReceiptBundle.textContent, "222222222222…22222222");
  assert.equal(doc.elements.p9ReceiptReuse.textContent, "新建本地结果");
  assert.equal(
    doc.elements.p9SeamReviewLink.attributes.href,
    `./seam-anchor-review.html?package_id=${PACKAGE_A}`,
  );
  assert.equal(doc.elements.p9NextProjectBtn.hidden, false);
  assert.match(doc.elements.p9NextProjectBtn.textContent, /本轮未处理.*sample-b/);
  assert.ok(doc.elements.p9PublishSteps.children.every((row) => row.dataset.state === "complete"));

  doc.elements.p9NextProjectBtn.click();
  await flush();
  assert.deepEqual(continued, [PACKAGE_B]);
});

test("reused receipt is explicit and a failed request keeps the ready draft retryable", async () => {
  const reusedDoc = uiDocument();
  const reusedController = createMotionPolicyPublicationController(reusedDoc, {
    api: { adopt: async () => receipt({ reused: true }) },
    buildReview: () => ({ reviewInput: reviewInput(), filename: "backup.json" }),
  });
  reusedController.load(packageDetail());
  reusedController.setReady(true);
  reusedDoc.elements.autoPublishBtn.click();
  await flush();
  assert.equal(reusedDoc.elements.p9ReceiptReuse.textContent, "复用既有结果");
  assert.equal(
    reusedDoc.elements.p9SeamReviewLink.attributes.href,
    `./seam-anchor-review.html?package_id=${PACKAGE_A}`,
  );
  assert.match(reusedDoc.elements.p9PublishStatus.textContent, /再次通过精确复验/);

  const failedDoc = uiDocument();
  let attempts = 0;
  const failedController = createMotionPolicyPublicationController(failedDoc, {
    api: { adopt: async () => { attempts += 1; throw new Error("本机发布不可用"); } },
    buildReview: () => ({ reviewInput: reviewInput(), filename: "backup.json" }),
  });
  failedController.load(packageDetail());
  failedController.setReady(true);
  failedDoc.elements.autoPublishBtn.click();
  await flush();
  assert.equal(attempts, 1);
  assert.equal(failedDoc.elements.autoPublishBtn.disabled, false);
  assert.equal(failedDoc.elements.autoBackupBtn.disabled, false);
  assert.match(failedDoc.elements.p9PublishStatus.textContent, /草稿仍保留/);
  assert.ok(failedDoc.elements.p9PublishSteps.children.every((row) => row.dataset.state === "failed"));
});

test("draft backup is non-authoritative and receives a collision-resistant filename", () => {
  const doc = uiDocument();
  const builds = [];
  const downloads = [];
  const controller = createMotionPolicyPublicationController(doc, {
    api: { adopt: async () => { throw new Error("must not publish"); } },
    buildReview: (options) => {
      builds.push(options);
      return {
        reviewInput: {
          format: "autospine-motion-policy-review-draft-backup",
          adoptable: false,
          draft: { review: { status: "draft", method: "unconfirmed" } },
        },
        filename: "fallback.json",
      };
    },
    download: (name, value) => downloads.push({ name, value }),
  });
  controller.load(packageDetail());
  controller.setReady(true);

  doc.elements.autoBackupBtn.click();

  assert.deepEqual(builds, [{ authoritative: false }]);
  assert.equal(downloads.length, 1);
  assert.equal(
    downloads[0].name,
    `sample-a.kimodo-wave.wave-left.${PACKAGE_A.slice(0, 12)}.motion-policy-review-draft.json`,
  );
  assert.equal(downloads[0].value.adoptable, false);
  assert.equal(downloads[0].value.draft.review.method, "unconfirmed");
});

test("a definite publish receipt survives a next-sample recommendation failure", async () => {
  const doc = uiDocument();
  const controller = createMotionPolicyPublicationController(doc, {
    api: { adopt: async () => receipt() },
    buildReview: () => ({ reviewInput: reviewInput(), filename: "backup.json" }),
    onPublished: () => { throw new Error("下一项索引暂不可用"); },
  });
  controller.load(packageDetail());
  controller.setReady(true);

  doc.elements.autoPublishBtn.click();
  await flush();

  assert.equal(doc.elements.p9PublishReceipt.hidden, false);
  assert.equal(doc.elements.p9PublishBadge.textContent, "已发布");
  assert.equal(doc.elements.autoPublishBtn.disabled, true);
  assert.match(doc.elements.p9PublishStatus.textContent, /P9 已发布并通过精确复验/);
  assert.match(doc.elements.p9NextProjectHint.textContent, /本轮未处理/);
});

test("draft invalidation scrubs every old receipt fact and Seam link", async () => {
  const doc = uiDocument();
  const controller = createMotionPolicyPublicationController(doc, {
    api: { adopt: async () => receipt() },
    buildReview: () => ({ reviewInput: reviewInput(), filename: "backup.json" }),
  });
  controller.load(packageDetail());
  controller.setReady(true);
  doc.elements.autoPublishBtn.click();
  await flush();
  assert.equal(doc.elements.p9PublishReceipt.hidden, false);

  controller.draftChanged();

  assert.equal(doc.elements.p9PublishReceipt.hidden, true);
  assert.equal(doc.elements.p9SeamReviewLink.attributes.href, undefined);
  assert.equal(doc.elements.p9ReceiptProject.textContent, "—");
  assert.equal(doc.elements.p9ReceiptInstance.textContent, "—");
  assert.equal(doc.elements.p9ReceiptBundle.textContent, "—");
});

test("publication lock remains active until a definite receipt and ignores draft invalidation", async () => {
  const doc = uiDocument();
  const pending = deferred();
  let published = 0;
  const locks = [];
  const controller = createMotionPolicyPublicationController(doc, {
    api: { adopt: async () => pending.promise },
    buildReview: () => ({ reviewInput: reviewInput(), filename: "backup.json" }),
    onPublished: () => { published += 1; return null; },
    onPublishingChange: (locked) => locks.push(locked),
  });
  controller.load(packageDetail());
  controller.setReady(true);
  doc.elements.autoPublishBtn.click();
  assert.deepEqual(locks, [true]);
  controller.draftChanged();
  pending.resolve(receipt());
  await flush();

  assert.equal(published, 1);
  assert.equal(doc.elements.p9PublishReceipt.hidden, false);
  assert.deepEqual(locks, [true, false]);
  assert.equal(doc.elements.autoPublishBtn.disabled, true);
});

test("authoritative review is built before the page locks and adoption starts only after locking", async () => {
  const doc = uiDocument();
  const events = [];
  const controller = createMotionPolicyPublicationController(doc, {
    api: {
      adopt: async () => {
        events.push("adopt");
        return receipt();
      },
    },
    buildReview: () => {
      events.push("build");
      return { reviewInput: reviewInput(), filename: "backup.json" };
    },
    onPublishingChange: (locked) => events.push(locked ? "lock" : "unlock"),
  });
  controller.load(packageDetail());
  controller.setReady(true);

  doc.elements.autoPublishBtn.click();
  await flush();

  assert.deepEqual(events.slice(0, 3), ["build", "lock", "adopt"]);
  assert.equal(events.at(-1), "unlock");
});

test("page lock disables every mutable control outside the live publication panel", () => {
  const project = new FakeElement();
  const timeline = new FakeElement();
  const alreadyDisabled = new FakeElement();
  const publish = new FakeElement();
  alreadyDisabled.disabled = true;
  publish.insidePublishPanel = true;
  const controls = [project, timeline, alreadyDisabled, publish];
  const panel = { contains: (control) => control.insidePublishPanel === true };
  const main = new FakeElement();
  const doc = {
    getElementById: (id) => id === "p9PublishPanel" ? panel : null,
    querySelector: (selector) => selector === "main" ? main : null,
    querySelectorAll: () => controls,
  };
  const lock = createMotionPolicyPageLock(doc);

  lock.setLocked(true);
  assert.equal(project.disabled, true);
  assert.equal(timeline.disabled, true);
  assert.equal(alreadyDisabled.disabled, true);
  assert.equal(publish.disabled, false);
  assert.equal(main.attributes["aria-busy"], "true");

  lock.setLocked(false);
  assert.equal(project.disabled, false);
  assert.equal(timeline.disabled, false);
  assert.equal(alreadyDisabled.disabled, true);
  assert.equal(main.attributes["aria-busy"], undefined);
});
