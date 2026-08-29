import {
  setDecisionBatch, validateDecision,
} from "./motion-policy-review-state.js";

const BATCH_ACTIONS = new Set(["accept", "reject", "unobservable"]);

export function createBatchPreview(model, candidateIds, draft) {
  requireModel(model);
  const ids = exactFrozenIds(model, candidateIds);
  const decision = batchDraft(draft);
  const byId = candidateMap(model);
  for (const candidateId of ids) {
    const issue = validateDecision(byId.get(candidateId), decision);
    if (issue) throw new Error(`${candidateId}: ${issue}`);
  }
  return Object.freeze({
    snapshotKey: model.snapshotKey,
    decisionVersion: model.decisionVersion,
    candidateIds: ids,
    action: decision.action,
    reason_code: decision.reason_code,
    overwriteCount: ids.filter((id) => model.decisions.has(id)).length,
  });
}

export function applyBatchPreview(model, preview) {
  requireModel(model);
  if (!preview || preview.snapshotKey !== model.snapshotKey) {
    throw new Error("批量预览不属于当前 candidate snapshot");
  }
  if (preview.decisionVersion !== model.decisionVersion) {
    throw new Error("批量预览已因逐项决定变化而失效");
  }
  const ids = exactFrozenIds(model, preview.candidateIds);
  if (!sameIds(ids, preview.candidateIds)) {
    throw new Error("批量预览 candidate ID 顺序或内容已变化");
  }
  const overwriteCount = ids.filter((id) => model.decisions.has(id)).length;
  if (overwriteCount !== preview.overwriteCount) {
    throw new Error("批量预览覆盖数量已变化");
  }
  return setDecisionBatch(model, ids, {
    action: preview.action,
    reason_code: preview.reason_code,
    payload: null,
  });
}

function requireModel(model) {
  if (!model || typeof model.snapshotKey !== "string" || !model.snapshotKey) {
    throw new Error("批量草稿需要精确 candidate snapshotKey");
  }
  if (!Array.isArray(model.inventory?.candidates) || !(model.decisions instanceof Map) ||
      !Number.isInteger(model.decisionVersion)) {
    throw new Error("批量草稿 model 无效");
  }
}

function candidateMap(model) {
  return new Map(model.inventory.candidates.map((row) => [row.candidateId, row]));
}

function exactFrozenIds(model, candidateIds) {
  if (!Array.isArray(candidateIds) || candidateIds.length === 0) {
    throw new Error("批量预览必须包含至少一个 candidate ID");
  }
  const available = candidateMap(model);
  const unique = new Set();
  const ids = candidateIds.map((candidateId) => {
    if (typeof candidateId !== "string" || unique.has(candidateId)) {
      throw new Error("批量预览 candidate ID 必须唯一");
    }
    if (!available.has(candidateId)) throw new Error(`未知 candidate ID: ${candidateId}`);
    unique.add(candidateId);
    return candidateId;
  }).sort((a, b) => a.localeCompare(b));
  return Object.freeze(ids);
}

function batchDraft(draft) {
  if (!draft || !BATCH_ACTIONS.has(draft.action)) {
    throw new Error("批量草稿只允许 accept、reject 或 unobservable");
  }
  const decision = {
    action: draft.action,
    reason_code: draft.reason_code,
    payload: null,
  };
  if (typeof decision.reason_code !== "string" || !decision.reason_code) {
    throw new Error("批量 reason_code 必填");
  }
  return decision;
}

function sameIds(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
