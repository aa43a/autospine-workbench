import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createRegionRebindHandoffController, loadRegionRebindHandoff, parseRegionRebindHandoff,
  removeConsumedRebindAddress,
} from "../modules/workbench-rebind-handoff.js";
import {
  adoptionDraft, adoptionRequest, canonicalProvenanceSha256,
  normalizeAdoptionReceipt, submitRegionRebindAdoption,
} from "../modules/workbench-rebind-adoption-api.js";
import {
  PACKAGE_B, probeEntryFixture,
} from "./body-sway-probe-fixtures.mjs";

const PROJECT = "seethrough_output_5";
const LAYER = "layer-007-handwear-l";
const CANDIDATE = "f".repeat(64);
const RESOLVED = "4".repeat(64);

function query(overrides = {}) {
  return new URLSearchParams({
    project: PROJECT, layer: LAYER, rebind_package: PACKAGE_B,
    rebind_candidate: CANDIDATE, ...overrides,
  }).toString();
}

test("exact P10.2 handoff automatically resolves the recommended layer and bone", async () => {
  const requests = [];
  const result = await loadRegionRebindHandoff(`?${query()}`, PROJECT, async (url) => {
    requests.push(url);
    return probeEntryFixture({
      resultStatus: "structural_rejected",
      rejectedCheck: "sampled_canvas_containment",
    });
  }, RESOLVED);
  assert.deepEqual(requests, [`/api/idle-behavior/structural-probes/${PACKAGE_B}`]);
  assert.equal(result.layerId, LAYER);
  assert.equal(result.fromBoneId, "forearm.left");
  assert.equal(result.toBoneId, "upper-arm.left");
  assert.equal(result.currentMetrics.viewport_overflow_sample_count, 217);
  assert.equal(result.proposedMetrics.viewport_overflow_sample_count, 38);
});

test("duplicate, cross-project, and stale candidate addresses fail closed", async () => {
  assert.throws(() => parseRegionRebindHandoff(
    `?${query()}&rebind_candidate=${CANDIDATE}`,
  ), /重复/);
  await assert.rejects(() => loadRegionRebindHandoff(
    `?${query()}`, "another-project", async () => ({}), RESOLVED,
  ), /当前项目/);
  await assert.rejects(() => loadRegionRebindHandoff(
    `?${query({ rebind_candidate: "0".repeat(64) })}`, PROJECT,
    async () => probeEntryFixture({
      resultStatus: "structural_rejected",
      rejectedCheck: "sampled_canvas_containment",
    }),
    RESOLVED,
  ), /过期/);
});

test("historical P10.2 evidence cannot preselect a current project binding", async () => {
  await assert.rejects(() => loadRegionRebindHandoff(
    `?${query()}`, PROJECT,
    async () => probeEntryFixture({
      resultStatus: "structural_rejected",
      rejectedCheck: "sampled_canvas_containment",
    }),
    "0".repeat(64),
  ), /历史项目快照/);
});

test("workbench renders the project before starting non-blocking exact evidence verification", async () => {
  const source = await readFile(new URL("../app.js", import.meta.url), "utf8");
  const initialized = source.indexOf("initializeProject(project, projectId);");
  const started = source.indexOf("rebindHandoff.load(", initialized);
  assert.ok(initialized >= 0 && started > initialized);
  assert.doesNotMatch(source.slice(initialized, started + 32),
    /await\s+rebindHandoff\.load/);
  assert.match(source, /if \(!adoption && rebindHandoff\.blockGeneralMutation\("普通保存"\)\)/);
  assert.match(source, /function confirmSelectedLayerRig\(\) \{\s+if \(rebindHandoff\.blockGeneralMutation\("普通 Rig 确认"\)\)/);
});

test("controller returns immediately and selects only after exact evidence resolves", async () => {
  const pending = deferred();
  const selected = [];
  const controller = createRegionRebindHandoffController(new FakeDocument(), dependencies({
    apiRequest: () => pending.promise,
    selectLayer: (layerId) => selected.push(layerId),
  }));

  const result = controller.load(`?${query()}`, PROJECT);
  assert.equal(result, undefined);
  assert.deepEqual(selected, []);
  pending.resolve(probeEntryFixture({
    resultStatus: "structural_rejected",
    rejectedCheck: "sampled_canvas_containment",
  }));
  await settle();
  assert.deepEqual(selected, [LAYER]);
});

test("same-project snapshot drift and switched-project responses stay fail-closed", async () => {
  const driftPending = deferred();
  const alerts = [];
  let resolvedSha = RESOLVED;
  const driftController = createRegionRebindHandoffController(
    new FakeDocument(),
    dependencies({
      apiRequest: () => driftPending.promise,
      currentResolvedSha256: () => resolvedSha,
      showAlert: (message) => alerts.push(message),
    }),
  );
  driftController.load(`?${query()}`, PROJECT);
  resolvedSha = "0".repeat(64);
  driftPending.resolve(probeEntryFixture({
    resultStatus: "structural_rejected",
    rejectedCheck: "sampled_canvas_containment",
  }));
  await settle();
  assert.match(alerts[0], /项目快照已在核验期间变化/);

  const stalePending = deferred();
  let current = true;
  const staleAlerts = [];
  const staleSelected = [];
  const staleController = createRegionRebindHandoffController(
    new FakeDocument(),
    dependencies({
      apiRequest: () => stalePending.promise,
      selectLayer: (layerId) => staleSelected.push(layerId),
      showAlert: (message) => staleAlerts.push(message),
    }),
  );
  staleController.load(`?${query()}`, PROJECT, () => current);
  current = false;
  stalePending.resolve(probeEntryFixture({
    resultStatus: "structural_rejected",
    rejectedCheck: "sampled_canvas_containment",
  }));
  await settle();
  assert.deepEqual(staleSelected, []);
  assert.deepEqual(staleAlerts, []);
});

test("active handoff stays a preview, blocks generic mutation, and dismisses with zero residue", async () => {
  const document = new FakeDocument();
  const alerts = [];
  const select = {
    value: "forearm.left",
    options: [{ value: "forearm.left" }, { value: "upper-arm.left" }],
  };
  const layer = { id: LAYER, candidate_bone: "forearm.left" };
  let saves = 0;
  const controller = createRegionRebindHandoffController(document, dependencies({
    apiRequest: async () => probeEntryFixture({
      resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
    }),
    showAlert: (message) => alerts.push(message),
    save: async () => { saves += 1; return false; },
    renderLayerInspector: () => { select.value = layer.candidate_bone; },
  }));
  controller.load(`?${query()}`, PROJECT);
  await settle();
  controller.render(layer, select);

  assert.equal(controller.isActive(), true);
  assert.equal(select.value, "forearm.left");
  assert.equal(controller.blockGeneralMutation("普通保存"), true);
  assert.match(alerts.at(-1), /专用确认/);
  select.value = "upper-arm.left";
  dismissButton(document).dispatchEvent(new Event("click"));
  assert.equal(controller.isActive(), false);
  assert.equal(select.value, "forearm.left");
  assert.equal(controller.blockGeneralMutation("普通保存"), false);
  assert.equal(saves, 0);
});

test("dedicated confirmation submits the suggestion without mutating the shared Rig select", async () => {
  const document = new FakeDocument();
  const select = {
    value: "forearm.left",
    options: [{ value: "forearm.left" }, { value: "upper-arm.left" }],
  };
  const layer = { id: LAYER, candidate_bone: "forearm.left" };
  let submitted = null;
  const controller = createRegionRebindHandoffController(document, dependencies({
    apiRequest: async () => probeEntryFixture({
      resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
    }),
    save: async (suggestion) => { submitted = suggestion; return false; },
  }));
  controller.load(`?${query()}`, PROJECT);
  await settle();
  controller.render(layer, select);
  const previousConfirm = globalThis.confirm;
  globalThis.confirm = () => true;
  try {
    adoptButton(document).dispatchEvent(new Event("click"));
    await settle();
  } finally {
    globalThis.confirm = previousConfirm;
  }
  assert.equal(submitted?.candidateSha256, CANDIDATE);
  assert.equal(select.value, "forearm.left");
  assert.equal(controller.isActive(), true);
});

test("consuming a suggestion removes only its immutable address", () => {
  let replaced = null;
  removeConsumedRebindAddress(
    { href: `http://127.0.0.1:8765/?${query()}` },
    { replaceState: (_state, _title, url) => { replaced = String(url); } },
  );
  const url = new URL(replaced);
  assert.equal(url.searchParams.get("project"), PROJECT);
  assert.equal(url.searchParams.get("layer"), LAYER);
  assert.equal(url.searchParams.has("rebind_package"), false);
  assert.equal(url.searchParams.has("rebind_candidate"), false);
});

test("adoption posts one candidate-bound draft and accepts only its saved revision", async () => {
  const suggestion = {
    projectId: PROJECT, layerId: LAYER, packageId: PACKAGE_B,
    candidateSha256: CANDIDATE, fromBoneId: "forearm.left",
    toBoneId: "upper-arm.left",
  };
  const snapshot = {
    projectId: PROJECT, baseRevision: 5,
    draft: {
      joint_overrides: {}, joint_decisions: {}, split_decisions: {},
      layer_overrides: { [LAYER]: { candidate_bone: "upper-arm.left" } },
      notes: "",
    },
  };
  let observed = null;
  const receipt = await receiptFixture({
    ...adoptionRequest(suggestion, snapshot), package_id: PACKAGE_B,
  });
  const result = await submitRegionRebindAdoption(async (url, options) => {
    observed = { url, options };
    return receipt;
  }, suggestion, snapshot);
  assert.equal(observed.url,
    `/api/idle-behavior/structural-probes/${PACKAGE_B}/rebind-adoptions/${CANDIDATE}`);
  assert.equal(observed.options.headers["X-Autospine-Intent"],
    "region-rebind-adoption-v1");
  const body = JSON.parse(observed.options.body);
  assert.equal(Object.hasOwn(body, "package_id"), false);
  assert.equal(body.base_revision, 5);
  assert.equal(result.overrides.revision, 6);

  const wrong = structuredClone(receipt);
  wrong.overrides.layer_overrides[LAYER].candidate_bone = "hand.left";
  await assert.rejects(() => normalizeAdoptionReceipt(wrong, {
    ...body, package_id: PACKAGE_B,
  }), /目标 revision/);

  const tampered = structuredClone(receipt);
  tampered.provenance.source.motion_sample_count = 82;
  tampered.overrides.revision_provenance.source.motion_sample_count = 82;
  await assert.rejects(() => normalizeAdoptionReceipt(tampered, {
    ...body, package_id: PACKAGE_B,
  }), /provenance SHA 不一致/);
});

test("adoption draft is isolated and browser canonical SHA matches the Python golden", async () => {
  const draft = {
    joint_overrides: {}, joint_decisions: {}, split_decisions: {},
    layer_overrides: {}, notes: "",
  };
  const suggestion = { layerId: LAYER, toBoneId: "upper-arm.left" };
  const adopted = adoptionDraft(draft, suggestion);
  assert.equal(adopted.layer_overrides[LAYER].candidate_bone, "upper-arm.left");
  assert.deepEqual(draft.layer_overrides, {});
  const receipt = await receiptFixture({
    ...adoptionRequest({
      ...suggestion, fromBoneId: "forearm.left", candidateSha256: CANDIDATE,
    }, { projectId: PROJECT, baseRevision: 5, draft: adopted }),
    package_id: PACKAGE_B,
  });
  assert.equal(await canonicalProvenanceSha256(receipt.provenance),
    "ceb511d83d4e9eea0d2f8cb2edbb1046a7012e07d5d3f5c6cb30255fa5a15980");
});

async function receiptFixture(request) {
  const revision = request.base_revision + 1;
  const provenance = {
    format: "autospine-region-rebind-revision-provenance", format_version: 1,
    intent: "region-rebind-adoption-v1", project_id: request.project_id,
    revision, package_id: request.package_id, candidate_sha256: request.candidate_sha256,
    layer_id: request.layer_id, from_bone_id: request.from_bone_id,
    to_bone_id: request.to_bone_id,
    source: {
      rig_sha256: "2".repeat(64), motion_sha256: "3".repeat(64),
      motion_samples_sha256: "4".repeat(64), motion_sample_count: 81,
      attachment_id: request.layer_id, slot_id: "slot-handwear-l",
      current_bone_id: request.from_bone_id,
      candidate_bone_ids_sha256: "5".repeat(64),
      analyzer_profile_sha256: "6".repeat(64),
    },
    current_chain: {
      resolved_project_sha256: "7".repeat(64),
      layer_manifest_sha256: "8".repeat(64),
    },
    p10_head: {
      current_revision: 2, head_decision_sha256: "9".repeat(64),
      action: "adjust", probe_status: "pending_probe",
    },
  };
  return {
    format: "autospine-region-rebind-adoption-receipt", format_version: 1,
    status: "adopted", project_id: request.project_id, revision,
    package_id: request.package_id, candidate_sha256: request.candidate_sha256,
    layer_id: request.layer_id, from_bone_id: request.from_bone_id,
    to_bone_id: request.to_bone_id,
    provenance_sha256: await canonicalProvenanceSha256(provenance),
    provenance,
    overrides: {
      project_id: request.project_id, revision,
      layer_overrides: { [request.layer_id]: { candidate_bone: request.to_bone_id } },
      revision_provenance: structuredClone(provenance),
    },
  };
}

function dismissButton(document) {
  const panel = document.layerFields.children[0];
  return panel.children[5].children[1];
}

function adoptButton(document) {
  const panel = document.layerFields.children[0];
  return panel.children[5].children[0];
}

function dependencies(overrides = {}) {
  const layer = { id: LAYER, candidate_bone: "forearm.left" };
  return {
    apiRequest: async () => ({}), layers: () => [layer],
    effectiveLayer: (value) => value, selectLayer() {}, selectedLayer: () => layer,
    isDirty: () => false, currentResolvedSha256: () => RESOLVED,
    candidateBoneSelect: { value: "", options: [] }, confirmLayerRig: () => true,
    save: async () => false, showAlert() {}, announce() {}, renderLayerInspector() {},
    location: { href: `http://127.0.0.1:8765/?${query()}` },
    history: { replaceState() {} },
    ...overrides,
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

class FakeElement extends EventTarget {
  constructor(tagName = "div") {
    super();
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.hidden = false;
    this.options = [];
  }

  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  setAttribute(name, value) { this[name] = String(value); }
}

class FakeDocument {
  constructor() { this.layerFields = new FakeElement("section"); }
  getElementById(id) { return id === "layerFields" ? this.layerFields : null; }
  createElement(tagName) { return new FakeElement(tagName); }
}
