"use strict";

import {
  digestValue, exactCopy, exactFields, integer, safeId, sameJson,
} from "./body-sway-probe-contract-utils.js";

const ENDPOINT = "/api/idle-behavior/structural-probes";
const INTENT = "region-rebind-adoption-v1";
const RECEIPT_FIELDS = [
  "format", "format_version", "status", "project_id", "revision",
  "package_id", "candidate_sha256", "layer_id", "from_bone_id",
  "to_bone_id", "provenance_sha256", "provenance", "overrides",
];
const PROVENANCE_FIELDS = [
  "format", "format_version", "intent", "project_id", "revision",
  "package_id", "candidate_sha256", "layer_id", "from_bone_id",
  "to_bone_id", "source", "current_chain", "p10_head",
];
const SOURCE_FIELDS = [
  "rig_sha256", "motion_sha256", "motion_samples_sha256",
  "motion_sample_count", "attachment_id", "slot_id", "current_bone_id",
  "candidate_bone_ids_sha256", "analyzer_profile_sha256",
];

export async function submitRegionRebindAdoption(
  apiRequest, suggestion, snapshot, cryptoApi = globalThis.crypto,
) {
  const request = adoptionRequest(suggestion, snapshot);
  const packageId = digestValue(suggestion?.packageId, "换绑采用 package SHA");
  const payload = await apiRequest(
    `${ENDPOINT}/${encodeURIComponent(packageId)}`
      + `/rebind-adoptions/${encodeURIComponent(request.candidate_sha256)}`,
    {
      method: "POST",
      headers: { "X-Autospine-Intent": INTENT },
      body: JSON.stringify(request),
    },
  );
  return normalizeAdoptionReceipt(
    payload, { ...request, package_id: packageId }, cryptoApi,
  );
}

export function adoptionDraft(draft, suggestion) {
  const result = exactCopy(draft);
  const layerId = safeId(suggestion?.layerId, "换绑采用 layer_id");
  const target = safeId(suggestion?.toBoneId, "换绑采用 to_bone_id");
  if (!result || typeof result !== "object" || Array.isArray(result)
      || !result.layer_overrides || typeof result.layer_overrides !== "object"
      || Array.isArray(result.layer_overrides)) throw new Error("换绑采用草稿无效");
  const current = result.layer_overrides[layerId];
  result.layer_overrides[layerId] = {
    ...(current && typeof current === "object" && !Array.isArray(current) ? current : {}),
    candidate_bone: target,
  };
  return result;
}

export function adoptionRequest(suggestion, snapshot) {
  const request = {
    project_id: snapshot?.projectId,
    layer_id: suggestion?.layerId,
    from_bone_id: suggestion?.fromBoneId,
    to_bone_id: suggestion?.toBoneId,
    candidate_sha256: suggestion?.candidateSha256,
    base_revision: snapshot?.baseRevision,
    overrides: snapshot?.draft,
  };
  for (const field of ["project_id", "layer_id", "from_bone_id", "to_bone_id"]) {
    safeId(request[field], `换绑采用 ${field}`);
  }
  digestValue(request.candidate_sha256, "换绑采用 candidate SHA");
  if (!Number.isInteger(request.base_revision) || request.base_revision < 0
      || !request.overrides || typeof request.overrides !== "object"
      || Array.isArray(request.overrides)) throw new Error("换绑采用草稿无效");
  return request;
}

export async function normalizeAdoptionReceipt(
  value, request, cryptoApi = globalThis.crypto,
) {
  exactFields(value, RECEIPT_FIELDS, "换绑采用回执");
  const expected = {
    project_id: request.project_id, package_id: request.package_id,
    candidate_sha256: request.candidate_sha256, layer_id: request.layer_id,
    from_bone_id: request.from_bone_id, to_bone_id: request.to_bone_id,
  };
  if (value.format !== "autospine-region-rebind-adoption-receipt"
      || value.format_version !== 1 || value.status !== "adopted"
      || value.revision !== request.base_revision + 1
      || Object.entries(expected).some(([field, expectedValue]) =>
        value[field] !== expectedValue)) throw new Error("换绑采用回执身份无效");
  digestValue(value.provenance_sha256, "换绑 provenance SHA");
  requireProvenance(value.provenance, value);
  if (await canonicalProvenanceSha256(value.provenance, cryptoApi)
      !== value.provenance_sha256) throw new Error("换绑 provenance SHA 不一致");
  const overrides = value.overrides;
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)
      || overrides.project_id !== value.project_id
      || overrides.revision !== value.revision
      || overrides.layer_overrides?.[value.layer_id]?.candidate_bone
        !== value.to_bone_id
      || !sameJson(overrides.revision_provenance, value.provenance)) {
    throw new Error("换绑采用回执没有确认目标 revision");
  }
  return value;
}

export async function canonicalProvenanceSha256(value, cryptoApi = globalThis.crypto) {
  if (!cryptoApi?.subtle) throw new Error("当前浏览器不支持 SHA-256 Web Crypto");
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = new Uint8Array(await cryptoApi.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireProvenance(value, receipt) {
  exactFields(value, PROVENANCE_FIELDS, "换绑 revision provenance");
  if (value.format !== "autospine-region-rebind-revision-provenance"
      || value.format_version !== 1 || value.intent !== INTENT
      || ["project_id", "revision", "package_id", "candidate_sha256", "layer_id",
        "from_bone_id", "to_bone_id"].some((field) => value[field] !== receipt[field])) {
    throw new Error("换绑 revision provenance 与回执不一致");
  }
  const source = exactFields(value.source, SOURCE_FIELDS, "换绑 provenance 来源");
  for (const field of ["rig_sha256", "motion_sha256", "motion_samples_sha256",
    "candidate_bone_ids_sha256", "analyzer_profile_sha256"]) {
    digestValue(source[field], `换绑 provenance ${field}`);
  }
  for (const field of ["attachment_id", "slot_id", "current_bone_id"]) {
    safeId(source[field], `换绑 provenance ${field}`);
  }
  integer(source.motion_sample_count, 2, "换绑 provenance 采样数", 65536);
  if (source.attachment_id !== receipt.layer_id
      || source.current_bone_id !== receipt.from_bone_id) {
    throw new Error("换绑 provenance 来源绑定不一致");
  }
  const chain = exactFields(value.current_chain,
    ["resolved_project_sha256", "layer_manifest_sha256"], "换绑 current chain");
  digestValue(chain.resolved_project_sha256, "换绑 Resolved Project SHA");
  digestValue(chain.layer_manifest_sha256, "换绑 Layer Manifest SHA");
  const head = exactFields(value.p10_head,
    ["current_revision", "head_decision_sha256", "action", "probe_status"], "换绑 P10 head");
  integer(head.current_revision, 1, "换绑 P10 revision");
  digestValue(head.head_decision_sha256, "换绑 P10 decision SHA");
  if (head.action !== "adjust" || head.probe_status !== "pending_probe") {
    throw new Error("换绑 provenance P10 head 无效");
  }
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("换绑 provenance 不是 canonical JSON");
  return encoded;
}
