import assert from "node:assert/strict";
import test from "node:test";

import { captureSaveSnapshot } from "../modules/draft-transactions.js";
import { overrideDraftFromServer } from "../modules/override-draft.js";
import { refreshSavedProject } from "../modules/saved-project-refresh.js";

const SHA_OLD = "a".repeat(64);
const SHA_NEW = "b".repeat(64);
const ARTIFACT = "c".repeat(64);
const clone = (value) => JSON.parse(JSON.stringify(value));
const normalizers = {
  normalizeOverrideMap: (value) => clone(value || {}),
  normalizeLayerOverrideMap: (value) => clone(value || {}),
};
const draftFromServer = (overrides, fallback) => overrideDraftFromServer(
  overrides,
  fallback,
  normalizers,
);

function draft(notes = "sent") {
  return {
    joint_overrides: {},
    joint_decisions: {},
    split_decisions: {
      sleeves: { action: "accept", split_artifact_sha256: ARTIFACT },
    },
    layer_overrides: {},
    notes,
  };
}

function project(revision, sha, overrides = {}) {
  return {
    id: "fixture",
    overrides: { revision, ...overrides },
    resolved: { project_id: "fixture", revision, sha256: sha },
  };
}

test("authoritative GET refreshes the resolved SHA and preserves edits made while saving", async () => {
  const snapshot = captureSaveSnapshot({
    projectId: "fixture", baseRevision: 4, editEpoch: 7, draft: draft(),
  });
  const storedDecision = {
    ...draft().split_decisions.sleeves,
    binding_status: "current",
    analysis: { provider: "binder" },
  };
  const savedOverrides = { revision: 5, ...draft(), split_decisions: { sleeves: storedDecision } };
  let liveDraft = draft();
  let editEpoch = 7;
  let finishRequest;
  const requestProject = () => new Promise((resolve) => { finishRequest = resolve; });
  const pending = refreshSavedProject({
    currentProject: project(4, SHA_OLD),
    projectId: "fixture",
    savedOverrides,
    snapshot,
    requestProject,
    getLiveDraft: () => liveDraft,
    getEditEpoch: () => editEpoch,
    draftFromServer,
  });

  liveDraft = draft("edited during refresh");
  editEpoch = 8;
  finishRequest(project(5, SHA_NEW, { ...draft(), split_decisions: { sleeves: storedDecision } }));
  const result = await pending;

  assert.equal(result.project.resolved.sha256, SHA_NEW);
  assert.equal(result.refreshError, null);
  assert.equal(result.reconciled.draft.notes, "edited during refresh");
  assert.equal(result.reconciled.hasPendingEdits, true);
  assert.deepEqual(result.reconciled.persistedDraft.split_decisions.sleeves, {
    action: "accept", split_artifact_sha256: ARTIFACT,
  });
});

test("refresh failure invalidates the old resolved SHA but keeps the successful PUT", async () => {
  const snapshot = captureSaveSnapshot({
    projectId: "fixture", baseRevision: 4, editEpoch: 2, draft: draft(),
  });
  const savedOverrides = { revision: 5, ...draft() };
  const result = await refreshSavedProject({
    currentProject: project(4, SHA_OLD),
    projectId: "fixture",
    savedOverrides,
    snapshot,
    requestProject: async () => { throw new Error("offline"); },
    getLiveDraft: () => draft(),
    getEditEpoch: () => 2,
    draftFromServer,
  });
  assert.equal(result.project.resolved, null);
  assert.equal(result.overrides.revision, 5);
  assert.match(result.refreshError.message, /offline/);
  assert.equal(result.reconciled.hasPendingEdits, false);
});

test("a cached pre-save GET is rejected instead of restoring its stale SHA", async () => {
  const snapshot = captureSaveSnapshot({
    projectId: "fixture", baseRevision: 4, editEpoch: 2, draft: draft(),
  });
  const result = await refreshSavedProject({
    currentProject: project(4, SHA_OLD),
    projectId: "fixture",
    savedOverrides: { revision: 5, ...draft() },
    snapshot,
    requestProject: async () => project(4, SHA_OLD, draft()),
    getLiveDraft: () => draft(),
    getEditEpoch: () => 2,
    draftFromServer,
  });
  assert.equal(result.project.resolved, null);
  assert.match(result.refreshError.message, /权威版本/);
});
