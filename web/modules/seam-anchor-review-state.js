"use strict";

import {
  requireSafeId, seamReviewAddressKey,
} from "./seam-anchor-review-address.js";
import {
  hasExactFields, requireSeamLocator,
} from "./seam-anchor-review-candidate.js";
import {
  requireAdjustedAnchorPairs,
} from "./seam-anchor-review-anchor-validation.js";

const ACTIONS = new Set(["accept", "adjust", "reject", "unobservable"]);
const REVIEW_BLOCKERS = [
  "dynamic_seam_safety_unproven", "reviewed_seam_anchor_set_missing",
  "runtime_equivalence_unproven", "visual_seam_quality_unproven",
];

const clone = (value) => JSON.parse(JSON.stringify(value));

export function createRequestSequence() {
  let current = 0;
  return Object.freeze({
    next: () => ++current,
    invalidate: () => ++current,
    isCurrent: (token) => token === current,
  });
}

export function createBusyGroup(names, onChange) {
  if (!Array.isArray(names) || new Set(names).size !== names.length
      || names.some((name) => typeof name !== "string" || !name)
      || typeof onChange !== "function") throw new TypeError("busy group is invalid");
  const current = Object.fromEntries(names.map((name) => [name, 0]));
  const activity = Object.fromEntries(names.map((name) => [name, false]));
  const announce = () => onChange(Object.freeze({ ...activity }));
  return Object.freeze({
    begin(name) {
      if (!Object.hasOwn(current, name)) throw new Error("unknown busy channel");
      current[name] += 1;
      activity[name] = true;
      announce();
      return current[name];
    },
    finish(name, token) {
      if (current[name] === token) activity[name] = false;
      announce();
    },
  });
}

export function createSeamReviewState() {
  return {
    addressKey: null, candidate: null, candidateSha256: null,
    attachmentImages: [], history: null, selectedDecision: null,
    baseline: null, decisions: {}, reviewerId: "", reviewNotes: "",
    currentRelationshipId: null, stale: false,
  };
}

export function clearSeamReviewForAddress(state, address = null) {
  return {
    ...createSeamReviewState(),
    addressKey: address ? seamReviewAddressKey(address) : null,
    currentRelationshipId: state?.currentRelationshipId || null,
  };
}

export function hasLoadedSeamReviewAddress(state, address) {
  return Boolean(
    state?.candidate && state.addressKey === seamReviewAddressKey(address),
  );
}

export function parseAdjustedAnchors(text, option, attachmentImages = []) {
  let anchors;
  try { anchors = JSON.parse(text); } catch { throw new Error("anchors 必须是有效 JSON"); }
  if (!Array.isArray(anchors) || anchors.length < 2 || anchors.length > 8) {
    throw new Error("anchors 必须包含 2–8 个完整锚点对");
  }
  anchors.forEach((row, index) => {
    if (!hasExactFields(row, ["pair_id", "parent", "child"])
        || row.pair_id !== `anchor.${String(index).padStart(3, "0")}`) {
      throw new Error("anchor pair_id 或字段不完整");
    }
    requireSeamLocator(row.parent, option.parent_attachment_id, option.parent_attachment_type);
    requireSeamLocator(row.child, option.child_attachment_id, option.child_attachment_type);
  });
  requireAdjustedAnchorPairs(anchors, option, attachmentImages);
  return clone(anchors);
}

function relationshipById(state, relationshipId) {
  const row = state.candidate?.relationships.find(
    (item) => item.relationship_id === relationshipId,
  );
  if (!row) throw new Error("relationship 不属于当前候选");
  return row;
}

export function setSeamOption(state, relationshipId, optionId) {
  const relationship = relationshipById(state, relationshipId);
  const option = relationship.options.find(
    (row) => row.option_id === optionId && row.status === "candidate",
  );
  if (!option) throw new Error("只能选择带完整证据的 candidate option");
  const current = state.decisions[relationshipId] || {};
  const action = current.action || null;
  const finalAnchors = action === "adjust" ? clone(option.anchors) : null;
  return { ...state, decisions: { ...state.decisions, [relationshipId]: {
    ...current, action, optionId: option.option_id,
    optionEvidenceSha256: option.evidence_sha256,
    notes: current.notes || "", finalAnchors,
    anchorText: finalAnchors ? JSON.stringify(finalAnchors, null, 2) : "",
    anchorError: null,
  } } };
}

export function setSeamAction(state, relationshipId, action) {
  if (!ACTIONS.has(action)) throw new Error("不支持的 seam 判定");
  const relationship = relationshipById(state, relationshipId);
  const current = state.decisions[relationshipId] || { notes: "" };
  if (relationship.status === "unobservable") {
    if (action !== "unobservable") throw new Error("该关系只能标记为不可观测");
    return { ...state, decisions: { ...state.decisions, [relationshipId]: {
      ...current, action, optionId: null, optionEvidenceSha256: null,
      finalAnchors: null, anchorText: "", anchorError: null,
    } } };
  }
  const option = relationship.options.find(
    (row) => row.option_id === current.optionId && row.status === "candidate",
  );
  if (!option) throw new Error("请先选择一个 candidate option");
  const finalAnchors = action === "adjust" ? clone(option.anchors) : null;
  return { ...state, decisions: { ...state.decisions, [relationshipId]: {
    ...current, action, finalAnchors,
    anchorText: finalAnchors ? JSON.stringify(finalAnchors, null, 2) : "",
    anchorError: null,
  } } };
}

export function setSeamNotes(state, relationshipId, notes) {
  relationshipById(state, relationshipId);
  if (typeof notes !== "string" || notes.length > 2048) throw new Error("判定备注无效");
  const current = state.decisions[relationshipId] || {};
  return { ...state, decisions: { ...state.decisions, [relationshipId]: {
    ...current, action: current.action || null, notes,
  } } };
}

export function setAdjustedAnchorsText(state, relationshipId, text) {
  const relationship = relationshipById(state, relationshipId);
  const current = state.decisions[relationshipId];
  const option = relationship.options.find((row) => row.option_id === current?.optionId);
  if (current?.action !== "adjust" || !option) throw new Error("当前判定不是 adjust");
  try {
    const finalAnchors = parseAdjustedAnchors(
      text, option, state.attachmentImages,
    );
    return { ...state, decisions: { ...state.decisions, [relationshipId]: {
      ...current, anchorText: text, finalAnchors, anchorError: null,
    } } };
  } catch (error) {
    return { ...state, decisions: { ...state.decisions, [relationshipId]: {
      ...current, anchorText: text, finalAnchors: null, anchorError: error.message,
    } } };
  }
}

function completeChoice(relationship, choice) {
  if (!choice || !ACTIONS.has(choice.action)) return false;
  if (relationship.status === "unobservable") {
    return choice.action === "unobservable" && Boolean(choice.notes?.trim());
  }
  const option = relationship.options.find((row) => row.option_id === choice.optionId
    && row.evidence_sha256 === choice.optionEvidenceSha256 && row.status === "candidate");
  if (!option || (choice.action !== "accept" && !choice.notes?.trim())) return false;
  return choice.action !== "adjust" || Boolean(choice.finalAnchors) && !choice.anchorError;
}

export function deriveSeamReviewSummary(candidate, decisions) {
  const counts = { accept: 0, adjust: 0, reject: 0, unobservable: 0, pending: 0 };
  for (const relationship of candidate?.relationships || []) {
    const choice = decisions?.[relationship.relationship_id];
    if (completeChoice(relationship, choice)) counts[choice.action] += 1;
    else counts.pending += 1;
  }
  const status = counts.pending ? "candidate_only"
    : counts.accept + counts.adjust === 6
      ? "reviewed_anchor_set_ready_for_compile" : "reviewed_anchor_set_blocked";
  const reasonCodes = counts.pending
    ? [...(candidate?.release_gate?.reason_codes || [])]
    : status === "reviewed_anchor_set_blocked"
      ? [...REVIEW_BLOCKERS, "reviewed_seam_anchor_selection_blocked"]
      : [...REVIEW_BLOCKERS];
  return {
    counts, relationshipCount: candidate?.relationships?.length || 0, status,
    releaseGate: { status: "blocked", reasonCodes: [...new Set(reasonCodes)].sort() },
  };
}

export function expectedSeamSubmissionResult(state) {
  const derived = deriveSeamReviewSummary(state.candidate, state.decisions);
  const anchorPairCount = state.candidate.relationships.reduce(
    (total, relationship) => {
      const choice = state.decisions[relationship.relationship_id];
      if (choice?.action === "adjust") return total + choice.finalAnchors.length;
      if (choice?.action !== "accept") return total;
      const option = relationship.options.find(
        (row) => row.option_id === choice.optionId,
      );
      return total + option.anchors.length;
    }, 0,
  );
  return {
    status: derived.status,
    releaseGate: {
      status: derived.releaseGate.status,
      reason_codes: derived.releaseGate.reasonCodes,
    },
    summary: {
      relationship_count: derived.relationshipCount,
      accept_count: derived.counts.accept,
      adjust_count: derived.counts.adjust,
      reject_count: derived.counts.reject,
      unobservable_count: derived.counts.unobservable,
      anchor_pair_count: anchorPairCount,
    },
  };
}

export function buildSeamReviewSubmission(state) {
  if (!state.candidate || !state.baseline) throw new Error("请先显式选择当前 head 作为基线");
  const reviewerId = requireSafeId(state.reviewerId, "reviewer ID");
  if (typeof state.reviewNotes !== "string" || state.reviewNotes.length > 4096) {
    throw new Error("总备注不能超过 4096 字符");
  }
  const base = state.baseline;
  if (!Number.isInteger(base.revision) || base.revision < 0 || base.revision >= 64
      || (base.revision === 0 && base.decisionSha256 !== null)
      || (base.revision > 0 && !/^[0-9a-f]{64}$/.test(base.decisionSha256))) {
    throw new Error("提交基线无效");
  }
  const decisions = state.candidate.relationships.map((relationship) => {
    const choice = state.decisions[relationship.relationship_id];
    if (!completeChoice(relationship, choice)) {
      throw new Error(`${relationship.relationship_id} 尚未完成有效判定`);
    }
    const row = {
      relationship_id: relationship.relationship_id,
      relationship_evidence_sha256: relationship.evidence_sha256,
      action: choice.action, option_id: choice.optionId,
      option_evidence_sha256: choice.optionEvidenceSha256, notes: choice.notes || "",
    };
    if (choice.action === "adjust") row.final_anchors = clone(choice.finalAnchors);
    return row;
  });
  return {
    base_revision: base.revision, candidate_sha256: state.candidateSha256,
    previous_decision_sha256: base.decisionSha256,
    review: { reviewer_id: reviewerId, notes: state.reviewNotes }, decisions,
  };
}

export function markSeamSubmissionConflict(state) {
  return { ...state, history: null, selectedDecision: null, baseline: null, stale: true };
}
