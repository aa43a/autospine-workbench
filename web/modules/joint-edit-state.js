import { resolvedDecisionPoint } from "./override-draft.js";


function numberOr(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function resolveEffectiveJoint(joint, state, cachedCandidatePoint = null) {
  const jointId = String(joint.id);
  const override = state.jointOverrides[jointId] || {};
  const decision = state.jointDecisions[jointId] || {};
  const resolved = state.resolvedJointDecisions[jointId] || {};
  const acceptedPoint = resolvedDecisionPoint(decision, resolved)
    || cachedCandidatePoint
    || [];
  const decisionPoint = Array.isArray(decision.final_xy)
    ? decision.final_xy
    : acceptedPoint;
  return {
    ...joint,
    x: numberOr(override.x, numberOr(decisionPoint[0], numberOr(joint.x))),
    y: numberOr(override.y, numberOr(decisionPoint[1], numberOr(joint.y))),
    reviewAction: decision.action || null,
    isManual: Object.prototype.hasOwnProperty.call(state.jointOverrides, jointId),
  };
}

export function applyManualJoint(state, jointId, x, y) {
  const key = String(jointId);
  delete state.jointDecisions[key];
  state.jointOverrides[key] = {
    ...(state.jointOverrides[key] || {}),
    x: Math.round(x * 10) / 10,
    y: Math.round(y * 10) / 10,
  };
}

export function clearJointEdits(state, jointId) {
  const key = String(jointId);
  delete state.jointOverrides[key];
  delete state.jointDecisions[key];
}
