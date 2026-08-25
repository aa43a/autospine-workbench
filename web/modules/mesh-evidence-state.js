const SHA256 = /^[0-9a-f]{64}$/;

function digest(value, label) {
  const text = String(value || "");
  if (!SHA256.test(text)) throw new Error(`${label} SHA-256 无效`);
  return text;
}

export function normalizeMeshBundleIndex(payload, projectId) {
  if (payload?.format !== "autospine-mesh-bundle-evidence-index"
      || payload?.format_version !== 1
      || payload?.project_id !== projectId
      || !Array.isArray(payload?.items)) {
    throw new Error("Mesh bundle 索引合同无效");
  }
  const seen = new Set();
  const items = payload.items.map((item) => {
    const rig = digest(item?.rig_sha256, "RigIR");
    const bundle = digest(item?.bundle_sha256, "Bundle");
    const key = `${rig}/${bundle}`;
    if (seen.has(key)) throw new Error("Mesh bundle 索引包含重复地址");
    seen.add(key);
    return { rig_sha256: rig, bundle_sha256: bundle };
  });
  if (payload.count !== items.length) throw new Error("Mesh bundle 索引计数无效");
  return items.sort((left, right) => left.rig_sha256.localeCompare(right.rig_sha256)
    || left.bundle_sha256.localeCompare(right.bundle_sha256));
}

export function meshRigOptions(items) {
  return [...new Set(items.map((item) => item.rig_sha256))];
}

export function meshBundlesForRig(items, rigSha) {
  return items.filter((item) => item.rig_sha256 === rigSha)
    .map((item) => item.bundle_sha256);
}

export function meshBundleDetailUrl(apiBase, projectId, rigSha, bundleSha) {
  const rig = digest(rigSha, "RigIR");
  const bundle = digest(bundleSha, "Bundle");
  if (!projectId) throw new Error("项目标识无效");
  return `${String(apiBase).replace(/\/$/, "")}/${encodeURIComponent(projectId)}`
    + `/mesh-bundles/${rig}/${bundle}`;
}

export function meshBundleImageUrl(apiBase, projectId, rigSha, bundleSha, pngSha) {
  return `${meshBundleDetailUrl(apiBase, projectId, rigSha, bundleSha)}`
    + `/images/${digest(pngSha, "PNG")}`;
}

export function normalizeMeshBundleDetail(payload, expected) {
  if (payload?.format !== "autospine-mesh-bundle-evidence"
      || payload?.format_version !== 1
      || payload?.project_id !== expected.projectId
      || !payload?.source || !Array.isArray(payload?.hinges)) {
    throw new Error("Mesh bundle 证据合同无效");
  }
  const source = payload.source;
  for (const name of [
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
    "visuals_sha256", "bundle_sha256",
  ]) digest(source[name], name);
  if (source.rig_sha256 !== expected.rigSha
      || source.bundle_sha256 !== expected.bundleSha) {
    throw new Error("Mesh bundle 详情未绑定显式选择的双 SHA");
  }
  if (!new Set(["converted", "reviewed-noop"]).has(payload.status)
      || (payload.status === "reviewed-noop") !== (payload.hinges.length === 0)) {
    throw new Error("Mesh bundle 转换状态无效");
  }
  const expectedSummary = payload.status === "reviewed-noop"
    ? "reviewed-noop" : `converted=${payload.hinges.length}`;
  if (payload.summary !== expectedSummary) throw new Error("Mesh bundle 摘要无效");
  const hingeIds = new Set();
  payload.hinges.forEach((hinge) => {
    validateHinge(hinge);
    if (hingeIds.has(hinge.attachment_id)) throw new Error("Mesh hinge 标识重复");
    hingeIds.add(hinge.attachment_id);
  });
  return payload;
}

function validateHinge(hinge) {
  if (!hinge || typeof hinge.attachment_id !== "string"
      || !Number.isInteger(hinge.vertex_count) || hinge.vertex_count < 3
      || !Number.isInteger(hinge.triangle_count) || hinge.triangle_count < 1) {
    throw new Error("Mesh hinge 拓扑摘要无效");
  }
  const safe = hinge.continuous_safe_angle_deg;
  if (!Number.isInteger(safe?.minimum) || !Number.isInteger(safe?.maximum)
      || safe.minimum > 0 || safe.minimum < -135
      || safe.maximum < 0 || safe.maximum > 135) {
    throw new Error("Mesh hinge 连续安全角无效");
  }
  for (const key of ["heatmap", "setup", "widest_safe"]) {
    const image = hinge.images?.[key];
    digest(image?.png_sha256, `${key} PNG`);
    if (!Number.isInteger(image?.width) || image.width < 1 || image.width > 4096
        || !Number.isInteger(image?.height) || image.height < 1 || image.height > 4096) {
      throw new Error("Mesh evidence 图片尺寸无效");
    }
  }
  if (hinge.images.heatmap.angle_deg !== null
      || hinge.images.setup.angle_deg !== 0
      || !Number.isInteger(hinge.images.widest_safe.angle_deg)
      || hinge.images.widest_safe.angle_deg === 0
      || Math.abs(hinge.images.widest_safe.angle_deg) > 135) {
    throw new Error("Mesh evidence 姿势角无效");
  }
}

export function shortMeshSha(value) {
  return SHA256.test(String(value || "")) ? value.slice(0, 8) : "—";
}
