import {
  validateCandidatePair, validatePolicyCandidateBinding,
} from "./motion-policy-contracts.js";
import { deriveCandidateInventorySha } from "./motion-policy-hash.js";
import { deriveInventory } from "./motion-policy-inventory.js";

export async function authorizeCandidateInventory({ api, snapshot, isCurrent }) {
  const declared = {
    policy_sha256: snapshot.policySha,
    foot_candidates_sha256: snapshot.footSha,
    depth_candidates_sha256: snapshot.depthSha,
  };
  const result = await api.candidateInventory(
    snapshot.policyJson, snapshot.footJson, snapshot.depthJson, declared, snapshot.policy,
  );
  if (!isCurrent()) return null;
  const binding = validateCandidatePair(
    snapshot.foot.document, snapshot.depth.document, snapshot.footSha, snapshot.depthSha,
  );
  validatePolicyCandidateBinding(snapshot.policy, snapshot.depth.document, snapshot.policySha);
  const derived = await deriveInventory(
    snapshot.foot.document, binding.footSha256,
    snapshot.depth.document, binding.depthSha256,
  );
  if (!isCurrent()) return null;
  await validateInventory(result.inventory, derived);
  if (!isCurrent()) return null;
  const candidateIdsSha256 = result.inventory.candidate_ids_sha256;
  const snapshotKey = [
    binding.projectId, binding.clipId, snapshot.policySha,
    binding.footSha256, binding.depthSha256, candidateIdsSha256,
  ].join("|");
  return { ...binding, ...derived, candidateIdsSha256, snapshotKey };
}

export async function validateInventory(expected, derived, cryptoApi = globalThis.crypto) {
  const actual = {
    total_count: derived.candidates.length,
    foot_count: derived.candidates.filter((row) => row.kind === "foot_lock").length,
    depth_count: derived.candidates.filter((row) => row.kind === "depth_order").length,
    unconstrained_count: derived.unconstrainedTicks.length,
  };
  for (const key of Object.keys(actual)) {
    if (expected?.[key] !== actual[key]) {
      throw new Error(`Python 预检 inventory.${key} 与浏览器展示清单不一致`);
    }
  }
  const candidateIdsSha = await deriveCandidateInventorySha(
    derived.candidates.map((row) => row.candidateId), cryptoApi,
  );
  if (expected?.candidate_ids_sha256 !== candidateIdsSha) {
    throw new Error("Python 预检的候选 ID 清单摘要与浏览器展示清单不一致");
  }
}
