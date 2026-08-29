const BASE_URL = "/api/motion-policy/review-packages";
const INTENT = "motion-policy-adoption-v1";
const REQUEST_FORMAT = "autospine-motion-policy-adoption-request";
const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function createMotionPolicyAdoptionApi(fetchApi = globalThis.fetch) {
  return {
    async adopt(packageId, reviewInput, { expected = null } = {}) {
      requireSha(packageId, "自动复核包 ID");
      requireReviewInput(reviewInput);
      const response = await fetchApi(`${BASE_URL}/${packageId}/adoptions`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-AutoSpine-Intent": INTENT,
        },
        body: JSON.stringify({
          format: REQUEST_FORMAT,
          format_version: 1,
          intent: INTENT,
          package_id: packageId,
          review_input: reviewInput,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.message || `P9 本地发布失败（HTTP ${response.status}）`);
      }
      return normalizeAdoptionReceipt(payload, packageId, expected);
    },
  };
}

export function normalizeAdoptionReceipt(payload, requestedPackageId, expected = null) {
  const root = envelopeReport(payload);
  const receipt = object(root.receipt) || root;
  if (receipt.format !== "autospine-motion-policy-adoption-receipt" ||
      receipt.format_version !== 1) {
    throw new Error("P9 发布回执版本无效");
  }
  const publication = object(receipt.publication) || object(root.publication) || receipt;
  const verification = object(receipt.verification) || object(root.verification);
  const address = object(receipt.address) || object(publication.address);
  const packageId = first(receipt.package_id, root.package_id, publication.package_id);
  const projectId = first(receipt.project_id, root.project_id, publication.project_id, address?.project_id);
  const motionId = first(receipt.motion_id, root.motion_id, publication.motion_id);
  const clipId = first(receipt.clip_id, root.clip_id, publication.clip_id);
  const reused = firstBoolean(receipt.reused, root.reused, publication.reused);
  const instanceSha = first(
    address?.motion_instance_v2_sha256,
    receipt.motion_instance_v2_sha256,
    publication.motion_instance_v2_sha256,
  );
  const bundleSha = first(
    address?.bundle_sha256,
    receipt.reviewed_motion_bundle_sha256,
    receipt.bundle_sha256,
    publication.reviewed_motion_bundle_sha256,
    publication.bundle_sha256,
  );
  if (packageId !== requestedPackageId) throw new Error("发布回执与当前自动复核包不一致");
  requireId(projectId, "发布回执 project_id");
  requireId(motionId, "发布回执 motion_id");
  requireId(clipId, "发布回执 clip_id");
  requireSha(instanceSha, "MotionInstance v2 SHA");
  requireSha(bundleSha, "Reviewed bundle SHA");
  if (!address || address.project_id !== projectId) {
    throw new Error("发布回执地址与当前项目不一致");
  }
  if (typeof reused !== "boolean") throw new Error("发布回执缺少复用状态");
  requirePassed(root, receipt, verification);
  requireExpected({ projectId, motionId, clipId }, expected);
  return Object.freeze({
    packageId,
    projectId,
    motionId,
    clipId,
    reused,
    address: Object.freeze({
      projectId,
      motionInstanceV2Sha256: instanceSha,
      bundleSha256: bundleSha,
    }),
  });
}

function requireReviewInput(value) {
  exact(value, ["review", "decisions", "root_release_keys", "draw_order_loop_reset"], "复核输入");
  exact(value.review, ["status", "method", "revision"], "复核授权");
  if (value.review.status !== "approved" || value.review.method !== "human" ||
      !Number.isInteger(value.review.revision) || value.review.revision < 1 ||
      !Array.isArray(value.decisions) || !Array.isArray(value.root_release_keys) ||
      !object(value.draw_order_loop_reset)) {
    throw new Error("复核输入尚未形成有效的人工采用");
  }
}

function requirePassed(root, receipt, verification) {
  if (receipt.status !== "passed" || verification?.status !== "passed" ||
      verification.replayed_from_exact_upstreams !== true ||
      (root !== receipt && root.status !== "passed")) {
    throw new Error("发布回执未证明精确复验通过");
  }
}

function requireExpected(actual, expected) {
  if (expected === null || expected === undefined) return;
  if (!object(expected) || actual.projectId !== expected.projectId ||
      actual.motionId !== expected.motionId || actual.clipId !== expected.clipId) {
    throw new Error("发布回执与当前项目或动作不一致");
  }
}

function envelopeReport(value) {
  if (!object(value)) throw new Error("P9 发布回执不是 JSON 对象");
  if (object(value.report)) {
    if (value.ok !== true || value.status !== "passed") {
      throw new Error("P9 发布回执 envelope 未通过");
    }
    return value.report;
  }
  return value;
}

function exact(value, fields, label) {
  if (!object(value) || Object.keys(value).sort().join("\0") !== [...fields].sort().join("\0")) {
    throw new Error(`${label}字段无效`);
  }
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function first(...values) {
  return values.find((value) => typeof value === "string" && value.length > 0);
}

function firstBoolean(...values) {
  return values.find((value) => typeof value === "boolean");
}

function requireSha(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 无效`);
}

function requireId(value, label) {
  if (typeof value !== "string" || !ID.test(value)) throw new Error(`${label} 无效`);
}

export const MOTION_POLICY_ADOPTION_INTENT = INTENT;
