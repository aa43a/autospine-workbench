const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function cloneJson(value, fallback = null) {
  if (value == null) return fallback;
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return fallback;
  }
}

function equalScalar(left, right) {
  return left === right || (Number.isNaN(left) && Number.isNaN(right));
}

function collectPatch(base, current, path, operations) {
  if (isPlainObject(base) && isPlainObject(current)) {
    const keys = [...new Set([...Object.keys(base), ...Object.keys(current)])].sort();
    for (const key of keys) {
      if (UNSAFE_KEYS.has(key)) continue;
      const nextPath = [...path, key];
      if (!Object.prototype.hasOwnProperty.call(current, key)) {
        operations.push({ op: "remove", path: nextPath });
      } else if (!Object.prototype.hasOwnProperty.call(base, key)) {
        operations.push({ op: "set", path: nextPath, value: cloneJson(current[key]) });
      } else {
        collectPatch(base[key], current[key], nextPath, operations);
      }
    }
    return;
  }

  if (Array.isArray(base) && Array.isArray(current)) {
    if (JSON.stringify(base) === JSON.stringify(current)) return;
  } else if (equalScalar(base, current)) {
    return;
  }
  operations.push({ op: "set", path, value: cloneJson(current) });
}

export function createDraftPatch(baseDraft, currentDraft) {
  const operations = [];
  collectPatch(baseDraft || {}, currentDraft || {}, [], operations);
  return operations;
}

function resolveParent(root, path, create) {
  let target = root;
  for (const key of path.slice(0, -1)) {
    if (UNSAFE_KEYS.has(key)) return null;
    if (!isPlainObject(target[key])) {
      if (!create) return null;
      target[key] = {};
    }
    target = target[key];
  }
  return target;
}

export function applyDraftPatch(baseDraft, operations) {
  let result = cloneJson(baseDraft, {});
  for (const operation of operations || []) {
    const path = Array.isArray(operation?.path) ? operation.path.map(String) : [];
    if (path.some((key) => UNSAFE_KEYS.has(key))) continue;
    if (!path.length) {
      if (operation.op === "set") result = cloneJson(operation.value, {});
      continue;
    }
    const parent = resolveParent(result, path, operation.op === "set");
    if (!parent) continue;
    const key = path[path.length - 1];
    if (operation.op === "remove") delete parent[key];
    if (operation.op === "set") parent[key] = cloneJson(operation.value);
  }
  return result;
}

export function captureSaveSnapshot({ projectId, baseRevision, editEpoch, draft }) {
  return Object.freeze({
    projectId: String(projectId),
    baseRevision,
    editEpoch,
    draft: cloneJson(draft, {}),
  });
}

export function reconcileSaveResponse({
  snapshot,
  liveDraft,
  serverDraft,
  currentEditEpoch,
}) {
  const pendingOperations = createDraftPatch(snapshot.draft, liveDraft);
  return {
    draft: applyDraftPatch(serverDraft, pendingOperations),
    persistedDraft: cloneJson(serverDraft, {}),
    pendingOperations,
    hasPendingEdits: currentEditEpoch !== snapshot.editEpoch || pendingOperations.length > 0,
  };
}

export function createLocalPatchArtifact({ projectId, baseRevision, baseDraft, currentDraft }) {
  return {
    schema: "https://autospine.local/schemas/local-draft-patch-v1",
    project_id: String(projectId),
    base_revision: baseRevision,
    created_at: new Date().toISOString(),
    operations: createDraftPatch(baseDraft, currentDraft),
  };
}
