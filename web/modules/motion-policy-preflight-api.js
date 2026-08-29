export const PREFLIGHT_URL = "/api/motion-policy/preflight";
export const PREFLIGHT_INTENT = "motion-policy-preflight-v1";
export const PREFLIGHT_FORMAT = "autospine-motion-policy-preflight-request";

const SHA = /^[0-9a-f]{64}$/;
const BASE_RESULT_FIELDS = new Set([
  "format", "format_version", "status", "operation", "project_id", "clip_id", "identities",
]);

export class MotionPolicyPreflightError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = "MotionPolicyPreflightError";
    this.status = status;
    this.payload = payload;
  }
}

export function createMotionPolicyPreflightApi(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch implementation is required");
  return Object.freeze({
    async policyIdentity(policyJson, policy) {
      requireJsonText(policyJson, "policy_json");
      const payload = await request(fetchImpl, {
        format: PREFLIGHT_FORMAT,
        format_version: 1,
        operation: "policy_identity",
        policy_json: policyJson,
      });
      return normalizePolicyIdentity(payload, policy);
    },
    async candidateInventory(
      policyJson, footCandidatesJson, depthCandidatesJson, declared, policy,
    ) {
      requireJsonText(policyJson, "policy_json");
      requireJsonText(footCandidatesJson, "foot_candidates_json");
      requireJsonText(depthCandidatesJson, "depth_candidates_json");
      const payload = await request(fetchImpl, {
        format: PREFLIGHT_FORMAT,
        format_version: 1,
        operation: "candidate_inventory",
        policy_json: policyJson,
        foot_candidates_json: footCandidatesJson,
        depth_candidates_json: depthCandidatesJson,
        declared,
      });
      return normalizeCandidateInventory(payload, policy, declared);
    },
  });
}

export function normalizePolicyIdentity(payload, policy) {
  validateBase(payload, "policy_identity", policy, BASE_RESULT_FIELDS);
  exact(payload.identities, new Set(["policy_sha256"]), "policy identities");
  sha(payload.identities.policy_sha256, "policy_sha256");
  return payload;
}

export function normalizeCandidateInventory(payload, policy, declared) {
  validateBase(payload, "candidate_inventory", policy,
    new Set([...BASE_RESULT_FIELDS, "inventory"]));
  exact(payload.identities, new Set([
    "policy_sha256", "foot_candidates_sha256", "depth_candidates_sha256",
  ]), "candidate identities");
  exact(declared, new Set([
    "policy_sha256", "foot_candidates_sha256", "depth_candidates_sha256",
  ]), "declared identities");
  for (const key of Object.keys(declared)) {
    sha(declared[key], `declared.${key}`);
    if (payload.identities[key] !== declared[key]) {
      throw new MotionPolicyPreflightError(`Python 预检返回的 ${key} 与当前输入快照不一致`, 200, payload);
    }
  }
  exact(payload.inventory, new Set([
    "total_count", "foot_count", "depth_count", "unconstrained_count",
    "candidate_ids_sha256",
  ]), "candidate inventory");
  for (const [key, value] of Object.entries(payload.inventory)) {
    if (key === "candidate_ids_sha256") {
      sha(value, `inventory.${key}`);
      continue;
    }
    if (!Number.isInteger(value) || value < 0) {
      throw new MotionPolicyPreflightError(`Python 预检返回的 ${key} 无效`, 200, payload);
    }
  }
  if (payload.inventory.total_count !==
      payload.inventory.foot_count + payload.inventory.depth_count) {
    throw new MotionPolicyPreflightError("Python 预检返回的 inventory 计数不闭合", 200, payload);
  }
  return payload;
}

async function request(fetchImpl, body) {
  const response = await fetchImpl(PREFLIGHT_URL, {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Autospine-Intent": PREFLIGHT_INTENT,
    },
    body: JSON.stringify(body),
  });
  const payload = await responsePayload(response);
  if (!response.ok) {
    throw new MotionPolicyPreflightError(
      errorMessage(payload, response.status), response.status, payload,
    );
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new MotionPolicyPreflightError("本机 Python 预检返回的 JSON 无效", response.status, payload);
  }
  return payload;
}

function validateBase(payload, operation, policy, expectedFields) {
  exact(payload, expectedFields, "preflight result");
  if (payload.format !== "autospine-motion-policy-preflight-result" ||
      payload.format_version !== 1 || payload.status !== "passed" ||
      payload.operation !== operation || payload.project_id !== policy?.project_id ||
      payload.clip_id !== policy?.clip_id) {
    throw new MotionPolicyPreflightError("Python 预检响应与当前 policy 不一致", 200, payload);
  }
}

async function responsePayload(response) {
  const type = response.headers?.get?.("content-type") || "";
  if (type.includes("application/json")) return response.json().catch(() => null);
  return response.text().catch(() => "");
}

function errorMessage(payload, status) {
  if (payload && typeof payload === "object") {
    return payload.message || payload.detail || payload.error || `HTTP ${status}`;
  }
  return String(payload || `HTTP ${status}`);
}

function exact(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new MotionPolicyPreflightError(`${label} 必须是对象`, 200, value);
  }
  const keys = Object.keys(value);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw new MotionPolicyPreflightError(`${label} 字段不完整或不受支持`, 200, value);
  }
}

function sha(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) {
    throw new MotionPolicyPreflightError(`${label} 不是小写 SHA-256`, 200, value);
  }
}

function requireJsonText(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new MotionPolicyPreflightError(`${label} 必须是原始 JSON 文本`, 0, value);
  }
}
