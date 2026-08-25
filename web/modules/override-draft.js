import { cloneJson } from "./draft-transactions.js";

export function clientJointDecisions(value) {
  const decisions = cloneJson(value, {});
  for (const decision of Object.values(decisions)) {
    if (!decision || typeof decision !== "object" || Array.isArray(decision)) continue;
    delete decision.analysis;
    if (["accept", "reject", "unobservable"].includes(decision.action)) delete decision.final_xy;
  }
  return decisions;
}

export function captureOverrideDraft(state) {
  return {
    joint_overrides: cloneJson(state.jointOverrides, {}),
    joint_decisions: clientJointDecisions(state.jointDecisions),
    layer_overrides: cloneJson(state.layerOverrides, {}),
    notes: String(state.notes ?? ""),
  };
}

export function applyOverrideDraft(
  state,
  draft,
  { normalizeOverrideMap, normalizeLayerOverrideMap },
) {
  state.jointOverrides = normalizeOverrideMap(draft?.joint_overrides);
  state.jointDecisions = clientJointDecisions(
    normalizeOverrideMap(draft?.joint_decisions),
  );
  state.layerOverrides = normalizeLayerOverrideMap(draft?.layer_overrides);
  state.notes = String(draft?.notes ?? "");
}

export function overrideDraftFromServer(
  overrides,
  fallbackDraft,
  { normalizeOverrideMap, normalizeLayerOverrideMap },
) {
  return {
    joint_overrides: normalizeOverrideMap(
      overrides?.joint_overrides ?? fallbackDraft?.joint_overrides,
    ),
    joint_decisions: clientJointDecisions(
      normalizeOverrideMap(
        overrides?.joint_decisions ?? fallbackDraft?.joint_decisions,
      ),
    ),
    layer_overrides: normalizeLayerOverrideMap(
      overrides?.layer_overrides ?? fallbackDraft?.layer_overrides,
    ),
    notes: String(overrides?.notes ?? fallbackDraft?.notes ?? ""),
  };
}

export function resolvedDecisionPoint(clientDecision, resolvedDecision) {
  if (clientDecision?.action !== "accept" || resolvedDecision?.action !== "accept") {
    return null;
  }
  const identityKeys = ["candidate_artifact_sha256", "candidate_id"];
  if (identityKeys.some((key) => clientDecision[key] !== resolvedDecision[key])) {
    return null;
  }
  const point = resolvedDecision.final_xy;
  if (
    !Array.isArray(point)
    || point.length !== 2
    || point.some((value) => !Number.isFinite(Number(value)))
  ) {
    return null;
  }
  return point.map(Number);
}
