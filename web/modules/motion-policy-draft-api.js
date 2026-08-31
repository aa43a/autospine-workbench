const BASE = "/api/motion-policy/review-drafts";
const INTENT = "depth-policy-draft-adoption-v1";
const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function createMotionPolicyDraftApi(fetchApi = globalThis.fetch) {
  return {
    async list(projectId = null) {
      return validateList(await get(fetchApi, scopedListUrl(projectId)));
    },
    async detail(draftId, projectId = null) {
      requireSha(draftId, "草案 ID");
      const value = validateDetail(await get(
        fetchApi, scopedDetailUrl(draftId, projectId),
      ));
      if (value.draft_id !== draftId) throw new Error("草案详情身份不一致");
      return value;
    },
    async adopt(detail) {
      validateDetail(detail);
      const response = await fetchApi(`${BASE}/${detail.draft_id}/policy-adoptions`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Autospine-Intent": INTENT,
        },
        body: JSON.stringify({
          format: "autospine-depth-policy-draft-adoption-request",
          format_version: 1,
          intent: INTENT,
          draft_id: detail.draft_id,
          manifest_sha256: detail.manifest_sha256,
          proposal_sha256: detail.proposal_sha256,
          explicit_confirmation: true,
        }),
      });
      const value = await response.json().catch(() => null);
      if (!response.ok) throw new Error(value?.message || `Depth policy 生成失败（HTTP ${response.status}）`);
      return validateReceipt(value, detail);
    },
  };
}

function scopedListUrl(projectId) {
  if (projectId === null) return BASE;
  requireId(projectId, "project_id");
  return `${BASE}?project_id=${encodeURIComponent(projectId)}`;
}

function scopedDetailUrl(draftId, projectId) {
  if (projectId === null) return `${BASE}/${draftId}`;
  requireId(projectId, "project_id");
  return `${BASE}/${draftId}?project_id=${encodeURIComponent(projectId)}`;
}

async function get(fetchApi, url) {
  const response = await fetchApi(url, {
    method: "GET", credentials: "same-origin", cache: "no-store",
    headers: { Accept: "application/json" },
  });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.message || `草案请求失败（HTTP ${response.status}）`);
  return value;
}

function validateList(value) {
  exact(value, ["format", "format_version", "count", "skipped_count",
    "recommended_draft_id", "drafts"], "草案清单");
  if (value.format !== "autospine-motion-policy-draft-list" || value.format_version !== 1 ||
      !Number.isInteger(value.count) || value.count < 0 ||
      !Number.isInteger(value.skipped_count) || value.skipped_count < 0 ||
      !Array.isArray(value.drafts) || value.count !== value.drafts.length) {
    throw new Error("草案清单合同无效");
  }
  const drafts = value.drafts.map(validateSummary);
  const recommended = drafts.find((row) => row.draft_id === value.recommended_draft_id);
  if (new Set(drafts.map((row) => row.draft_id)).size !== drafts.length ||
      (value.recommended_draft_id !== null && !recommended) ||
      (recommended && recommended.authoring_alignment !== "current")) {
    throw new Error("草案清单推荐项无效");
  }
  return { ...value, drafts };
}

function validateSummary(value) {
  exact(value, ["format", "format_version", "draft_id", "project_id",
    "motion_namespace", "clip_id", "manifest_sha256", "proposal_sha256",
    "foot_candidates_sha256", "promotion_motion_id", "pair_count",
    "authoring_alignment"], "草案摘要");
  if (value.format !== "autospine-motion-policy-review-draft-detail" ||
      value.format_version !== 1 || !["current", "historical"].includes(value.authoring_alignment) ||
      value.pair_count !== 1) {
    throw new Error("草案摘要合同无效");
  }
  for (const key of ["project_id", "motion_namespace", "clip_id", "promotion_motion_id"]) requireId(value[key], key);
  for (const key of ["draft_id", "manifest_sha256", "proposal_sha256", "foot_candidates_sha256"]) requireSha(value[key], key);
  return value;
}

function validateDetail(value) {
  const summary = { ...value };
  delete summary.semantic_summary;
  validateSummary(summary);
  exact(value, [...Object.keys(summary), "semantic_summary"], "草案详情");
  const semantic = object(value.semantic_summary, "草案语义摘要");
  exact(semantic, ["pair_count", "pairs"], "草案语义摘要");
  if (semantic.pair_count !== value.pair_count || !Array.isArray(semantic.pairs) ||
      semantic.pairs.length !== value.pair_count) throw new Error("草案语义摘要不完整");
  semantic.pairs.forEach(validatePair);
  return value;
}

function validatePair(pair) {
  exact(pair, ["pair_id", "setup_front_slot", "slots"], "Depth pair");
  requireId(pair.pair_id, "pair_id");
  requireId(pair.setup_front_slot, "setup_front_slot");
  if (!Array.isArray(pair.slots) || pair.slots.length !== 2) throw new Error("Depth pair 必须包含两个图层");
  for (const slot of pair.slots) {
    exact(slot, ["slot_id", "depth_role"], "Depth slot");
    requireId(slot.slot_id, "slot_id");
    requireId(slot.depth_role, "depth_role");
  }
  if (!pair.slots.some((slot) => slot.slot_id === pair.setup_front_slot)) throw new Error("前景图层不属于当前 pair");
}

function validateReceipt(value, detail) {
  exact(value, ["format", "format_version", "status", "draft_id", "project_id",
    "motion_id", "clip_id", "reused", "policy_sha256",
    "depth_candidates_sha256", "package_id"], "Depth policy 回执");
  if (value.format !== "autospine-depth-policy-draft-adoption-receipt" ||
      value.format_version !== 1 || value.status !== "passed" ||
      value.draft_id !== detail.draft_id || value.project_id !== detail.project_id ||
      value.clip_id !== detail.clip_id || value.motion_id !== detail.promotion_motion_id ||
      typeof value.reused !== "boolean") throw new Error("Depth policy 回执身份无效");
  requireSha(value.package_id, "package_id");
  requireSha(value.policy_sha256, "policy_sha256");
  requireSha(value.depth_candidates_sha256, "depth_candidates_sha256");
  return value;
}

function exact(value, fields, label) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join("\0") !== [...fields].sort().join("\0")) throw new Error(`${label}字段无效`);
}
function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label}必须是对象`);
  return value;
}
function requireSha(value, label) { if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 无效`); }
function requireId(value, label) { if (typeof value !== "string" || !ID.test(value)) throw new Error(`${label} 无效`); }

export const DEPTH_POLICY_DRAFT_INTENT = INTENT;
