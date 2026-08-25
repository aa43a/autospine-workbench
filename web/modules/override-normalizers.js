import { cloneJson } from "./draft-transactions.js";


export function canonicalSide(value) {
  const side = String(value ?? "unknown").toLowerCase();
  if (["left", "l"].includes(side)) return "left";
  if (["right", "r"].includes(side)) return "right";
  if (["center", "centre", "c", "none", "n/a"].includes(side)) return "center";
  if (["bilateral", "b", "both"].includes(side)) return "bilateral";
  return "unknown";
}

export function normalizeOverrideMap(value) {
  if (!value) return {};
  if (Array.isArray(value)) {
    return Object.fromEntries(
      value.filter(Boolean).map((entry) => [String(entry.id), cloneJson(entry, {})]),
    );
  }
  return typeof value === "object" ? cloneJson(value, {}) : {};
}

export function normalizeLayerOverrideMap(value) {
  const overrides = normalizeOverrideMap(value);
  for (const [layerId, rawOverride] of Object.entries(overrides)) {
    if (!rawOverride || typeof rawOverride !== "object" || Array.isArray(rawOverride)) {
      overrides[layerId] = {};
      continue;
    }
    const semantic = rawOverride.semantic && typeof rawOverride.semantic === "object"
      ? rawOverride.semantic
      : {};
    if (!("canonical_role" in rawOverride)) {
      const role = semantic.canonical_role ?? semantic.role ?? rawOverride.role;
      if (role != null) rawOverride.canonical_role = role;
    }
    if (!("side" in rawOverride) && "side" in semantic) rawOverride.side = semantic.side;
    if ("side" in rawOverride) rawOverride.side = canonicalSide(rawOverride.side);
    delete rawOverride.semantic;
    delete rawOverride.role;
  }
  return overrides;
}
