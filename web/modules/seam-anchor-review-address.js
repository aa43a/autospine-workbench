"use strict";

export const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const SAFE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function requireSafeId(value, label = "标识符") {
  const identifier = String(value ?? "").trim();
  if (!SAFE_ID_PATTERN.test(identifier)) {
    throw new Error(`${label} 必须是 1–128 位安全标识符`);
  }
  return identifier;
}

export function requireSha256(value, label = "SHA-256") {
  const digest = String(value ?? "").trim();
  if (!SHA256_PATTERN.test(digest)) {
    throw new Error(`${label} 必须是 64 位小写十六进制`);
  }
  return digest;
}

export function normalizeSeamReviewAddress(values) {
  return Object.freeze({
    projectId: requireSafeId(values?.projectId, "项目 ID"),
    layerManifestSha256: requireSha256(
      values?.layerManifestSha256, "Layer Manifest SHA-256",
    ),
    p3RigSha256: requireSha256(values?.p3RigSha256, "P3 RigIR SHA-256"),
    p3BundleSha256: requireSha256(values?.p3BundleSha256, "P3 bundle SHA-256"),
  });
}

export function seamReviewAddressKey(address) {
  const value = normalizeSeamReviewAddress(address);
  return [
    value.projectId, value.layerManifestSha256,
    value.p3RigSha256, value.p3BundleSha256,
  ].join(":");
}

const segment = (value) => encodeURIComponent(String(value));

export function seamAnchorReviewPaths(rawAddress) {
  const address = normalizeSeamReviewAddress(rawAddress);
  const base = [
    "/api/projects", segment(address.projectId), "seam-anchor-reviews",
    address.layerManifestSha256, address.p3RigSha256, address.p3BundleSha256,
  ].join("/");
  const candidateBase = (candidateSha256) => `${base}/candidates/${
    requireSha256(candidateSha256, "candidate SHA-256")}`;
  return Object.freeze({
    candidate: () => `${base}/candidate`,
    history: (candidateSha256) => `${candidateBase(candidateSha256)}/history`,
    decision: (candidateSha256, revision, decisionSha256) => {
      if (!Number.isInteger(revision) || revision < 1 || revision > 64) {
        throw new Error("历史 revision 超出允许范围");
      }
      return `${candidateBase(candidateSha256)}/history/${revision}/${
        requireSha256(decisionSha256, "decision SHA-256")}`;
    },
    submit: (candidateSha256) => `${candidateBase(candidateSha256)}/decisions`,
    optionImage: (candidateSha256, optionId, attachmentId, imageSha256) =>
      `${candidateBase(candidateSha256)}/options/${
        segment(requireSafeId(optionId, "option ID"))}/attachments/${
        segment(requireSafeId(attachmentId, "attachment ID"))}/images/${
        requireSha256(imageSha256, "image SHA-256")}`,
  });
}
