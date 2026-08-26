"use strict";

export const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const PROJECT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function requireProject(value) {
  const projectId = String(value ?? "").trim();
  if (!PROJECT_PATTERN.test(projectId)) {
    throw new Error("项目 ID 必须是 1–128 位安全标识符");
  }
  return projectId;
}

export function requireSha256(value, label = "SHA-256") {
  const digest = String(value ?? "").trim();
  if (!SHA256_PATTERN.test(digest)) {
    throw new Error(`${label} 必须是 64 位小写十六进制`);
  }
  return digest;
}

export function normalizeReviewAddress(values) {
  return Object.freeze({
    projectId: requireProject(values?.projectId),
    previewSha256: requireSha256(values?.previewSha256, "preview SHA-256"),
    bundleSha256: requireSha256(values?.bundleSha256, "bundle SHA-256"),
    artifactSha256: requireSha256(values?.artifactSha256, "artifact SHA-256"),
  });
}

export function reviewAddressKey(address) {
  const value = normalizeReviewAddress(address);
  return [
    value.projectId,
    value.previewSha256,
    value.bundleSha256,
    value.artifactSha256,
  ].join(":");
}

const segment = (value) => encodeURIComponent(String(value));

export function bodySwayReviewPaths(rawAddress) {
  const address = normalizeReviewAddress(rawAddress);
  const base = [
    "/api/projects",
    segment(address.projectId),
    "body-sway-runtime-captures",
    address.previewSha256,
    address.bundleSha256,
    address.artifactSha256,
    "visual-review",
  ].join("/");

  const candidateBase = (candidateSha256) =>
    `${base}/candidates/${requireSha256(candidateSha256, "candidate SHA-256")}`;

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
    image: (candidateSha256, caseId, pngSha256) => {
      if (!PROJECT_PATTERN.test(String(caseId ?? ""))) {
        throw new Error("case ID 不是安全标识符");
      }
      return `${candidateBase(candidateSha256)}/cases/${segment(caseId)}/image/${
        requireSha256(pngSha256, "PNG SHA-256")}`;
    },
  });
}
