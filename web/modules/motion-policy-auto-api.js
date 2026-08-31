const LIST_URL = "/api/motion-policy/review-packages";
const SHA = /^[0-9a-f]{64}$/;

export function createMotionPolicyAutoApi(fetchApi = globalThis.fetch) {
  return {
    async list(projectId = null) {
      return validateList(await request(fetchApi, scopedListUrl(projectId)));
    },
    async package(packageId, projectId = null) {
      if (!SHA.test(packageId)) {
        throw new Error("自动复核包 ID 无效");
      }
      const path = scopedDetailUrl(packageId, projectId);
      const value = validatePackage(await request(fetchApi, path), true);
      if (value.package_id !== packageId) throw new Error("自动复核包详情身份不匹配");
      return value;
    },
  };
}

function scopedDetailUrl(packageId, projectId) {
  if (projectId === null) return `${LIST_URL}/${packageId}`;
  if (typeof projectId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(projectId)) {
    throw new Error("自动项目范围无效");
  }
  return `${LIST_URL}/${packageId}?project_id=${encodeURIComponent(projectId)}`;
}

function scopedListUrl(projectId) {
  if (projectId === null) return LIST_URL;
  if (typeof projectId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(projectId)) {
    throw new Error("自动项目范围无效");
  }
  return `${LIST_URL}?project_id=${encodeURIComponent(projectId)}`;
}

async function request(fetchApi, url) {
  const response = await fetchApi(url, {
    method: "GET", credentials: "same-origin", cache: "no-store",
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.message || `自动项目请求失败（HTTP ${response.status}）`);
  return payload;
}

function validateList(value) {
  exact(value, ["format", "format_version", "count", "skipped_count",
    "recommended_package_id", "packages"], "自动项目清单");
  if (value.format !== "autospine-motion-policy-package-list" || value.format_version !== 2 ||
      !Number.isInteger(value.count) || value.count < 0 ||
      !Number.isInteger(value.skipped_count) || value.skipped_count < 0 ||
      !Array.isArray(value.packages) || value.count !== value.packages.length) {
    throw new Error("自动项目清单合同无效");
  }
  const packages = value.packages.map((row) => validatePackage(row, false));
  const ids = packages.map((row) => row.package_id);
  const recommended = packages.find(
    (row) => row.package_id === value.recommended_package_id,
  );
  if (new Set(ids).size !== ids.length ||
      (value.recommended_package_id !== null && !recommended)) {
    throw new Error("自动项目清单含重复或未知推荐项");
  }
  if (recommended && recommended.authoring_alignment !== "current") {
    throw new Error("自动项目清单不得推荐历史版本");
  }
  return { ...value, packages };
}

function validatePackage(value, documents) {
  const fields = ["format", "format_version", "project_id", "package_id", "motion_id", "clip_id",
    "identities", "inventory", "automation_profile", "authoring_alignment"];
  if (documents) fields.push("policy_json", "foot_candidates_json", "depth_candidates_json");
  exact(value, fields, "自动复核包");
  if (value.format !== "autospine-motion-policy-review-package" || value.format_version !== 2 ||
      value.automation_profile !== "safe-assist-v1") throw new Error("自动复核包版本无效");
  if (!["current", "historical"].includes(value.authoring_alignment)) {
    throw new Error("自动复核包绑定对齐状态无效");
  }
  for (const field of ["project_id", "motion_id", "clip_id"]) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value[field])) throw new Error(`自动复核包 ${field} 无效`);
  }
  if (!SHA.test(value.package_id)) throw new Error("自动复核包 package_id 无效");
  exact(value.identities, ["policy_sha256", "foot_candidates_sha256", "depth_candidates_sha256"], "自动身份");
  if (Object.values(value.identities).some((sha) => !SHA.test(sha))) throw new Error("自动复核包 SHA 无效");
  exact(value.inventory, ["total_count", "foot_count", "depth_count", "unconstrained_count", "candidate_ids_sha256"], "自动候选摘要");
  if (!["total_count", "foot_count", "depth_count", "unconstrained_count"]
    .every((key) => Number.isInteger(value.inventory[key]) && value.inventory[key] >= 0) ||
      value.inventory.total_count !== value.inventory.foot_count + value.inventory.depth_count ||
      !SHA.test(value.inventory.candidate_ids_sha256)) throw new Error("自动候选摘要无效");
  if (documents && !["policy_json", "foot_candidates_json", "depth_candidates_json"]
    .every((key) => typeof value[key] === "string" && value[key].length > 1)) {
    throw new Error("自动复核包缺少 JSON 证据");
  }
  return value;
}

function exact(value, fields, label) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join("\0") !== [...fields].sort().join("\0")) {
    throw new Error(`${label}字段无效`);
  }
}
