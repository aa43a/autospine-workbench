import { cloneJson } from "./draft-transactions.js";

export function captureOverrideDraft(state) {
  return {
    joint_overrides: cloneJson(state.jointOverrides, {}),
    joint_decisions: cloneJson(state.jointDecisions, {}),
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
  state.jointDecisions = normalizeOverrideMap(draft?.joint_decisions);
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
    joint_decisions: normalizeOverrideMap(
      overrides?.joint_decisions ?? fallbackDraft?.joint_decisions,
    ),
    layer_overrides: normalizeLayerOverrideMap(
      overrides?.layer_overrides ?? fallbackDraft?.layer_overrides,
    ),
    notes: String(overrides?.notes ?? fallbackDraft?.notes ?? ""),
  };
}
