import assert from "node:assert/strict";
import test from "node:test";

import { createMotionPolicyDraftController } from "../modules/motion-policy-draft-controller.js";

const DRAFT = "a".repeat(64);
const PACKAGE = "b".repeat(64);

class FakeElement extends EventTarget {
  constructor(doc) {
    super(); this.ownerDocument = doc; this.children = []; this.dataset = {};
    this.attributes = {}; this.disabled = false; this.hidden = false;
    this.textContent = ""; this.value = ""; this.className = "";
  }
  append(...values) { this.children.push(...values); }
  replaceChildren(...values) { this.children = values; }
  toggleAttribute(name, force) { if (force) this.attributes[name] = ""; else delete this.attributes[name]; }
  removeAttribute(name) { delete this.attributes[name]; if (name === "src") delete this.src; }
}

function fixture() {
  const ids = [
    "draftPolicyPanel", "draftPolicyBadge", "draftProjectSelect", "draftReloadBtn",
    "draftPolicyEvidence", "draftCharacterComposite", "draftPairFacts",
    "draftApproveBtn", "draftPolicyStatus",
  ];
  const map = new Map();
  const doc = {
    createElement: () => new FakeElement(doc),
    getElementById: (id) => map.get(id),
  };
  ids.forEach((id) => map.set(id, new FakeElement(doc)));
  return { doc, elements: Object.fromEntries(map) };
}

function row() {
  return {
    draft_id: DRAFT, project_id: "sample", motion_namespace: "wave-r6-draft",
    clip_id: "wave-left", manifest_sha256: "1".repeat(64),
    proposal_sha256: "2".repeat(64), foot_candidates_sha256: "3".repeat(64),
    promotion_motion_id: "wave-r6-pabcdef", pair_count: 1,
    authoring_alignment: "current",
  };
}

function detail() {
  return {
    ...row(),
    semantic_summary: {
      pair_count: 1,
      pairs: [{
        pair_id: "hand-vs-face", setup_front_slot: "layer-011-face",
        slots: [
          { slot_id: "layer-007-handwear-l", depth_role: "humanoid.arm.upper.left" },
          { slot_id: "layer-011-face", depth_role: "humanoid.head" },
        ],
      }],
    },
  };
}

test("current draft renders semantic facts and one confirmation promotes into existing P9 load", async () => {
  const { doc, elements } = fixture();
  const confirmations = [];
  const promoted = [];
  let currentDraftAnnouncements = 0;
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [row()], recommended_draft_id: DRAFT }),
      detail: async () => detail(),
      adopt: async () => ({ package_id: PACKAGE, motion_id: "wave-r6-pabcdef" }),
    },
    packageApi: {
      list: async () => ({ packages: [] }),
      package: async () => ({
        package_id: PACKAGE, project_id: "sample", motion_id: "wave-r6-pabcdef",
        authoring_alignment: "current",
      }),
    },
    confirmAction: (message) => { confirmations.push(message); return true; },
    onCurrentDraft: () => { currentDraftAnnouncements += 1; },
    onPromoted: async (value) => promoted.push(value.package_id),
  });

  await controller.start();
  assert.equal(elements.draftPolicyPanel.hidden, false);
  assert.equal(elements.draftPolicyEvidence.hidden, false);
  assert.equal(elements.draftPairFacts.children.length, 3);
  assert.match(elements.draftPairFacts.children[0].children[0].textContent, /layer-007-handwear-l/);
  assert.match(elements.draftPairFacts.children[0].children[1].textContent, /humanoid\.arm\.upper\.left/);
  assert.match(elements.draftPairFacts.children[0].children[2].src, /layer-007-handwear-l\/image$/);
  assert.match(elements.draftPairFacts.children[1].children[2].alt, /layer-011-face/);
  assert.equal(elements.draftApproveBtn.disabled, false);
  assert.equal(currentDraftAnnouncements, 1);

  elements.draftApproveBtn.dispatchEvent(new Event("click"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(confirmations.length, 1);
  assert.match(confirmations[0], /layer-011-face/);
  assert.deepEqual(promoted, [PACKAGE]);
  assert.equal(elements.draftApproveBtn.disabled, true);
  assert.equal(elements.draftPolicyStatus.dataset.tone, "success");
  assert.match(confirmations[0], /防抖参数/);
});

test("cancelled confirmation emits no adoption", async () => {
  const { doc, elements } = fixture();
  let adopted = 0;
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [row()], recommended_draft_id: DRAFT }),
      detail: async () => detail(),
      adopt: async () => { adopted += 1; },
    },
    packageApi: { list: async () => ({ packages: [] }) },
    confirmAction: () => false,
  });
  await controller.start();
  elements.draftApproveBtn.dispatchEvent(new Event("click"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(adopted, 0);
});

test("legacy project_id query scopes pending draft discovery", async () => {
  const { doc, elements } = fixture();
  const other = { ...row(), draft_id: "c".repeat(64), project_id: "other" };
  const requested = [];
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [other, row()], recommended_draft_id: other.draft_id }),
      detail: async (draftId) => { requested.push(draftId); return detail(); },
    },
    packageApi: { list: async () => ({ packages: [] }) },
    locationSearch: "?project_id=sample",
  });

  await controller.start();
  assert.deepEqual(requested, [DRAFT]);
  assert.equal(elements.draftProjectSelect.value, DRAFT);
});

test("draft discovery reuses an already validated package inventory", async () => {
  const { doc, elements } = fixture();
  let packageListCalls = 0;
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [row()], recommended_draft_id: DRAFT }),
      detail: async () => detail(),
    },
    packageApi: {
      list: async () => { packageListCalls += 1; return { packages: [] }; },
    },
    packageInventory: () => ({ packages: [] }),
  });

  await controller.start();
  assert.equal(packageListCalls, 0);
  assert.equal(elements.draftPolicyEvidence.hidden, false);
});

test("refresh recovers a committed promotion from package inventory without reposting", async () => {
  const { doc, elements } = fixture();
  let detailCalls = 0;
  let adoptionCalls = 0;
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [row()], recommended_draft_id: DRAFT }),
      detail: async () => { detailCalls += 1; return detail(); },
      adopt: async () => { adoptionCalls += 1; },
    },
    packageInventory: () => ({ packages: [{
      project_id: "sample", motion_id: "wave-r6-pabcdef",
      authoring_alignment: "current",
    }] }),
  });

  await controller.start();
  assert.equal(elements.draftPolicyPanel.hidden, true);
  assert.equal(detailCalls, 0);
  assert.equal(adoptionCalls, 0);
});

test("a committed promotion survives package load failure and retries only the GET", async () => {
  const { doc, elements } = fixture();
  let adoptionCalls = 0;
  let packageCalls = 0;
  const locks = [];
  const controller = createMotionPolicyDraftController(doc, {
    api: {
      list: async () => ({ drafts: [row()], recommended_draft_id: DRAFT }),
      detail: async () => detail(),
      adopt: async () => {
        adoptionCalls += 1;
        return { package_id: PACKAGE, motion_id: "wave-r6-pabcdef", reused: false };
      },
    },
    packageApi: {
      list: async () => ({ packages: [] }),
      package: async () => {
        packageCalls += 1;
        if (packageCalls === 1) throw new Error("temporary read failure");
        return {
          package_id: PACKAGE, project_id: "sample",
          motion_id: "wave-r6-pabcdef", authoring_alignment: "current",
        };
      },
    },
    confirmAction: () => true,
    onPublishingChange: (locked) => locks.push(locked),
  });

  await controller.start();
  elements.draftApproveBtn.dispatchEvent(new Event("click"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(adoptionCalls, 1);
  assert.match(elements.draftPolicyBadge.textContent, /已生成，待同步/);
  assert.match(elements.draftApproveBtn.textContent, /重新同步/);

  elements.draftApproveBtn.dispatchEvent(new Event("click"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(adoptionCalls, 1);
  assert.equal(packageCalls, 2);
  assert.equal(elements.draftApproveBtn.disabled, true);
  assert.deepEqual(locks, [true, false, true, false]);
});
