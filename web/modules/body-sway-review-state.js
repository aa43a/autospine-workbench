"use strict";

import { requireSha256, reviewAddressKey } from "./body-sway-review-address.js";

const ACTIONS = new Set(["approve", "reject", "unobservable"]);
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function createRequestSequence() {
  let current = 0;
  return Object.freeze({
    next: () => ++current,
    invalidate: () => ++current,
    isCurrent: (token) => token === current,
    value: () => current,
  });
}

export function createBusyGate(setBusy) {
  if (typeof setBusy !== "function") throw new TypeError("busy callback is required");
  let current = 0;
  return Object.freeze({
    begin() {
      current += 1;
      setBusy(true);
      return current;
    },
    finish(token) {
      if (token === current) setBusy(false);
    },
  });
}

export function createBusyGroup(names, onChange) {
  if (!Array.isArray(names) || !names.length || new Set(names).size !== names.length
      || names.some((name) => typeof name !== "string" || !name)
      || typeof onChange !== "function") {
    throw new TypeError("busy group requires unique names and a callback");
  }
  const activity = Object.fromEntries(names.map((name) => [name, false]));
  const gates = Object.fromEntries(names.map((name) => [
    name,
    createBusyGate((busy) => {
      activity[name] = busy;
      onChange(Object.freeze({ ...activity }));
    }),
  ]));
  return Object.freeze({
    gate(name) {
      if (!Object.hasOwn(gates, name)) throw new Error("unknown busy channel");
      return gates[name];
    },
  });
}

export function createReviewState() {
  return {
    addressKey: null,
    candidate: null,
    candidateSha256: null,
    history: null,
    selectedDecision: null,
    baseline: null,
    decisions: {},
    reviewerId: "",
    reviewNotes: "",
    currentCaseId: null,
    stale: false,
  };
}

export function clearReviewForAddress(state, address = null) {
  return {
    ...createReviewState(),
    addressKey: address ? reviewAddressKey(address) : null,
    currentCaseId: state?.currentCaseId || null,
  };
}

function requireCase(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)
      || !SAFE_ID.test(String(row.case_id ?? ""))
      || !(row.animation === null || SAFE_ID.test(String(row.animation ?? "")))
      || !Number.isInteger(row.tick) || row.tick < 0
      || !Number.isFinite(row.time_seconds) || row.time_seconds < 0
      || !row.image || typeof row.image !== "object"
      || Object.hasOwn(row.image, "path")
      || !Number.isInteger(row.image.size_bytes) || row.image.size_bytes < 1
      || !Number.isInteger(row.image.width) || row.image.width < 1
      || !Number.isInteger(row.image.height) || row.image.height < 1) {
    throw new Error("候选包含无效的 case 元数据");
  }
  requireSha256(row.evidence_sha256, "evidence SHA-256");
  requireSha256(row.image.png_sha256, "PNG SHA-256");
  return row;
}

export function normalizeCandidateEnvelope(payload, address) {
  const candidateSha256 = requireSha256(payload?.candidate_sha256, "candidate SHA-256");
  const candidate = payload?.candidate;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)
      || candidate.project_id !== address.projectId
      || candidate.status !== "candidate_only"
      || candidate.source?.temporary_preview_sha256 !== address.previewSha256
      || candidate.source?.runtime_capture_bundle_sha256 !== address.bundleSha256
      || candidate.source?.capture_artifact_set_sha256 !== address.artifactSha256
      || candidate.release_gate?.status !== "blocked"
      || !Array.isArray(candidate.release_gate?.reason_codes)
      || candidate.release_gate.reason_codes.some((reason) => typeof reason !== "string")
      || !Array.isArray(candidate.cases)
      || candidate.cases.length < 3 || candidate.cases.length > 55) {
    throw new Error("候选响应与显式地址不一致");
  }
  const seen = new Set();
  const cases = candidate.cases.map((row) => {
    requireCase(row);
    if (seen.has(row.case_id)) throw new Error("候选 case ID 重复");
    seen.add(row.case_id);
    return row;
  });
  return { candidateSha256, candidate: { ...candidate, cases } };
}

export function setCaseDecision(state, caseId, action, notes = "") {
  if (!state.candidate?.cases.some((row) => row.case_id === caseId)) {
    throw new Error("case 不属于当前候选");
  }
  if (!ACTIONS.has(action)) throw new Error("不支持的 case 判定");
  if (typeof notes !== "string" || notes.length > 2048) {
    throw new Error("case 备注不能超过 2048 字符");
  }
  return {
    ...state,
    decisions: { ...state.decisions, [caseId]: { action, notes } },
  };
}

export function setCaseNotes(state, caseId, notes) {
  if (!state.candidate?.cases.some((row) => row.case_id === caseId)
      || typeof notes !== "string" || notes.length > 2048) {
    throw new Error("case 备注无效");
  }
  const current = state.decisions[caseId] || { action: null, notes: "" };
  return {
    ...state,
    decisions: { ...state.decisions, [caseId]: { ...current, notes } },
  };
}

export function deriveReviewSummary(candidate, decisions) {
  const counts = { approve: 0, reject: 0, unobservable: 0, pending: 0 };
  for (const row of candidate?.cases || []) {
    const choice = decisions?.[row.case_id];
    const action = choice?.action;
    const incomplete = action !== "approve" && !choice?.notes?.trim();
    if (ACTIONS.has(action) && !incomplete) counts[action] += 1;
    else counts.pending += 1;
  }
  const status = counts.pending
    ? "candidate_only"
    : counts.reject || counts.unobservable
      ? "sampled_visual_rejected"
      : "sampled_visual_approved";
  const baseReasons = (candidate?.release_gate?.reason_codes || [])
    .filter((reason) => reason !== "manual_visual_review_required");
  const reasonCodes = counts.pending
    ? [...baseReasons, "manual_visual_review_required"]
    : status === "sampled_visual_rejected"
      ? [...baseReasons, "sampled_visual_review_rejected"]
      : baseReasons;
  return { counts, caseCount: candidate?.cases?.length || 0, status,
    releaseGate: { status: "blocked", reasonCodes: [...new Set(reasonCodes)].sort() } };
}

export function buildReviewSubmission(state) {
  if (!state.candidate || !state.baseline) throw new Error("请先显式选择当前 head 作为基线");
  if (!SAFE_ID.test(state.reviewerId)) throw new Error("reviewer ID 不是安全标识符");
  if (typeof state.reviewNotes !== "string" || state.reviewNotes.length > 4096) {
    throw new Error("总备注不能超过 4096 字符");
  }
  const base = state.baseline;
  if (!Number.isInteger(base.revision) || base.revision < 0 || base.revision >= 64
      || (base.revision === 0 && base.decisionSha256 !== null)
      || (base.revision > 0 && !/^[0-9a-f]{64}$/.test(base.decisionSha256))) {
    throw new Error("提交基线无效");
  }
  const decisions = state.candidate.cases.map((row) => {
    const choice = state.decisions[row.case_id];
    if (!choice || !ACTIONS.has(choice.action)) throw new Error(`case ${row.case_id} 尚未判定`);
    if (choice.action !== "approve" && !choice.notes.trim()) {
      throw new Error(`case ${row.case_id} 的备注不能为空`);
    }
    return {
      case_id: row.case_id,
      evidence_sha256: row.evidence_sha256,
      action: choice.action,
      notes: choice.notes,
    };
  });
  return {
    base_revision: state.baseline.revision,
    candidate_sha256: state.candidateSha256,
    previous_decision_sha256: state.baseline.decisionSha256,
    review: { reviewer_id: state.reviewerId, notes: state.reviewNotes },
    decisions,
  };
}

export function markSubmissionConflict(state) {
  return {
    ...state,
    history: null,
    selectedDecision: null,
    baseline: null,
    stale: true,
  };
}
