const SHA256 = /^[0-9a-f]{64}$/;
const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);
const CLIENT_FIELDS = ["action", "split_artifact_sha256", "reason"];

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function itemTime(item) {
  const value = Date.parse(item?.published_at || item?.created_at || "");
  return Number.isFinite(value) ? value : 0;
}

export function splitArtifactsForLayer(
  payload,
  layerId,
  currentResolvedSha = "",
  preferredArtifactSha = "",
) {
  const items = Array.isArray(payload) ? payload : payload?.items;
  return (Array.isArray(items) ? items : [])
    .map((item, index) => ({ ...item, _index: index }))
    .filter((item) => item.layer_id === layerId && SHA256.test(item.artifact_sha256 || ""))
    .sort((left, right) => {
      const current = Number(right.resolved_snapshot_sha256 === currentResolvedSha)
        - Number(left.resolved_snapshot_sha256 === currentResolvedSha);
      if (current) return current;
      const preferred = Number(right.artifact_sha256 === preferredArtifactSha)
        - Number(left.artifact_sha256 === preferredArtifactSha);
      if (preferred) return preferred;
      const time = itemTime(right) - itemTime(left);
      if (time) return time;
      const digest = right.artifact_sha256.localeCompare(left.artifact_sha256);
      return digest || left._index - right._index;
    })
    .map(({ _index, ...item }) => item);
}

export function clientSplitDecisions(value) {
  const result = {};
  if (!plainObject(value)) return result;
  for (const [layerId, decision] of Object.entries(value)) {
    if (UNSAFE_KEYS.has(layerId) || !plainObject(decision)) continue;
    const client = {};
    for (const field of CLIENT_FIELDS) {
      if (Object.prototype.hasOwnProperty.call(decision, field)) {
        client[field] = decision[field];
      }
    }
    result[layerId] = client;
  }
  return result;
}

export function buildSplitDecision(action, artifactSha, reason = "") {
  if (!SHA256.test(String(artifactSha || ""))) throw new Error("切分 artifact 标识无效");
  if (!new Set(["accept", "reject"]).has(action)) throw new Error("切分审查操作无效");
  const decision = { action, split_artifact_sha256: artifactSha };
  if (action === "reject") {
    const text = String(reason).trim();
    if (!text) throw new Error("拒绝切分时必须填写理由");
    if (text.length > 1000) throw new Error("拒绝理由不能超过 1000 个字符");
    decision.reason = text;
  }
  return decision;
}

export function applySplitDecision(state, layerId, decision) {
  if (!plainObject(state.splitDecisions)) state.splitDecisions = {};
  const id = String(layerId);
  if (UNSAFE_KEYS.has(id)) throw new Error("切分图层标识无效");
  state.splitDecisions[id] = { ...decision };
  return state.splitDecisions[id];
}

export function removeSplitDecision(state, layerId) {
  if (!plainObject(state.splitDecisions)) state.splitDecisions = {};
  const id = String(layerId);
  if (UNSAFE_KEYS.has(id)) return false;
  const existed = Object.prototype.hasOwnProperty.call(state.splitDecisions, id);
  delete state.splitDecisions[id];
  return existed;
}

export function splitDecisionStatus(draftDecision, storedDecision, artifactSha = "") {
  if (!plainObject(draftDecision)) return { kind: "none", label: "尚未审查" };
  const digest = draftDecision.split_artifact_sha256;
  const sameStored = plainObject(storedDecision)
    && storedDecision.action === draftDecision.action
    && storedDecision.split_artifact_sha256 === digest
    && String(storedDecision.reason || "") === String(draftDecision.reason || "");
  const suffix = artifactSha && artifactSha !== digest ? ` · 绑定 ${shortSha(digest)}` : "";
  if (sameStored && storedDecision.binding_status === "stale") {
    return { kind: "stale", label: `已失效${suffix}` };
  }
  if (draftDecision.action === "reject") {
    return { kind: "rejected", label: `${sameStored ? "已拒绝" : "待保存拒绝"}${suffix}` };
  }
  if (sameStored && storedDecision.binding_status === "current") {
    return { kind: "accepted-current", label: `已接受 · 当前有效${suffix}` };
  }
  return { kind: "accepted-pending", label: `待保存接受${suffix}` };
}

export function isSplitReviewLayer(layer) {
  return plainObject(layer)
    && layer.disposition === "split_left_right"
    && plainObject(layer.split_spec)
    && plainObject(layer.split_spec.parts?.left)
    && plainObject(layer.split_spec.parts?.right);
}

export function shouldShowSplitReviewBody(artifact, decision, hasArtifacts = false) {
  return plainObject(artifact) || plainObject(decision) || hasArtifacts === true;
}

export function isCurrentSplitArtifact(artifact, currentResolvedSha) {
  const digest = String(currentResolvedSha || "");
  return plainObject(artifact)
    && SHA256.test(digest)
    && artifact.resolved_snapshot_sha256 === digest;
}

export function splitPartImageUrl(apiBase, projectId, artifactSha, side) {
  if (projectId == null || String(projectId) === "") throw new Error("项目标识无效");
  if (!SHA256.test(String(artifactSha || ""))) throw new Error("切分 artifact 标识无效");
  if (!new Set(["left", "right"]).has(side)) throw new Error("切分侧别无效");
  return `${String(apiBase).replace(/\/$/, "")}/${encodeURIComponent(projectId)}`
    + `/split-previews/${encodeURIComponent(artifactSha)}/parts/${side}/image`;
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  })[character]);
}

export function shortSha(value) {
  return typeof value === "string" && value ? value.slice(0, 8) : "未知";
}
