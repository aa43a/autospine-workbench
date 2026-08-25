const ACTIONS = new Set(["accept", "adjust", "reject", "unobservable"]);
const CANDIDATE_ACTIONS = new Set(["accept", "adjust", "reject"]);
const SHA256 = /^[0-9a-f]{64}$/;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function createCandidateReviewState() {
  return {
    status: "idle",
    projectId: null,
    items: [],
    artifactSha: null,
    artifact: null,
    jointId: null,
    candidateId: null,
    error: null,
  };
}

export function reduceCandidateReview(state, event) {
  switch (event.type) {
    case "project-loading":
      return { ...createCandidateReviewState(), status: "loading", projectId: event.projectId };
    case "index-loaded": {
      const items = normalizeCandidateIndex(event.payload, state.projectId);
      return {
        ...state,
        status: items.length ? "artifact-loading" : "empty",
        items,
        artifactSha: items[0]?.artifact_sha256 || null,
        error: null,
      };
    }
    case "artifact-loading":
      return {
        ...state,
        status: "artifact-loading",
        artifactSha: event.artifactSha,
        artifact: null,
        candidateId: null,
        error: null,
      };
    case "artifact-loaded": {
      const artifact = normalizeCandidateArtifact(event.payload, state.projectId);
      const candidateId = event.clearCandidate
        ? null
        : selectCandidateId({
          artifact,
          jointId: state.jointId,
          preferredId: event.preferredId,
        });
      return { ...state, status: "ready", artifact, candidateId, error: null };
    }
    case "joint-selected":
      return {
        ...state,
        jointId: event.jointId == null ? null : String(event.jointId),
        candidateId: event.clearCandidate
          ? null
          : selectCandidateId({
            artifact: state.artifact,
            jointId: event.jointId,
            preferredId: event.preferredId,
          }),
      };
    case "candidate-selected": {
      const available = candidatesForJoint(state.artifact, state.jointId);
      const candidateId = available.some((item) => item.candidate_id === event.candidateId)
        ? event.candidateId
        : state.candidateId;
      return { ...state, candidateId };
    }
    case "failed":
      return { ...state, status: "error", artifact: null, candidateId: null, error: event.error };
    default:
      return state;
  }
}

export function normalizeCandidateIndex(payload, projectId) {
  if (!payload || typeof payload !== "object" || payload.kind !== "joint-candidates"
      || String(payload.project_id) !== String(projectId) || !Array.isArray(payload.items)) {
    throw new Error("候选 artifact 列表结构损坏");
  }
  return payload.items.map((item) => {
    if (!item || !SHA256.test(item.artifact_sha256) || typeof item.provider !== "string"
        || typeof item.provider_version !== "string" || !Number.isInteger(item.joint_count)
        || !Number.isInteger(item.candidate_count) || typeof item.qa_status !== "string"
        || !Array.isArray(item.qa_flags) || item.qa_flags.some((flag) => typeof flag !== "string")
        || !item.method_counts || typeof item.method_counts !== "object" || Array.isArray(item.method_counts)
        || Object.values(item.method_counts).some((count) => !Number.isInteger(count))) {
      throw new Error("候选 artifact 列表包含无效条目");
    }
    return item;
  });
}

export function normalizeCandidateArtifact(payload, projectId) {
  if (!payload || typeof payload !== "object" || payload.format !== "autospine-joint-candidates"
      || String(payload.project_id) !== String(projectId) || !payload.joints
      || typeof payload.joints !== "object" || Array.isArray(payload.joints)) {
    throw new Error("候选 artifact 结构损坏");
  }
  for (const [jointId, evidence] of Object.entries(payload.joints)) {
    if (!evidence || typeof evidence.observability !== "string" || !Array.isArray(evidence.candidates)) {
      throw new Error(`关节 ${jointId} 的候选结构损坏`);
    }
    for (const candidate of evidence.candidates) {
      const xy = candidate?.xy;
      if (typeof candidate?.candidate_id !== "string" || typeof candidate?.method !== "string"
          || candidate?.score_kind !== "heuristic" || !Number.isFinite(candidate?.heuristic_score)
          || candidate.heuristic_score < 0 || candidate.heuristic_score > 1
          || !Array.isArray(xy) || xy.length !== 2 || !xy.every(Number.isFinite)
          || !Array.isArray(candidate.source_layer_ids) || !Array.isArray(candidate.evidence)
          || candidate.evidence.some((item) => !item || typeof item.kind !== "string"
            || (item.source_ref != null && typeof item.source_ref !== "string") || typeof item.note !== "string")
          || !Array.isArray(candidate.qa_flags) || candidate.qa_flags.some((flag) => typeof flag !== "string")) {
        throw new Error(`关节 ${jointId} 包含损坏的候选数据`);
      }
    }
  }
  return payload;
}

export function candidatesForJoint(artifact, jointId) {
  if (!artifact || jointId == null) return [];
  const candidates = artifact.joints?.[String(jointId)]?.candidates;
  return Array.isArray(candidates) ? candidates : [];
}

export function selectCandidateId({ artifact, jointId, preferredId = null }) {
  const candidates = candidatesForJoint(artifact, jointId);
  return candidates.some((item) => item.candidate_id === preferredId)
    ? preferredId
    : candidates[0]?.candidate_id || null;
}

export function acceptedCandidatePoint(artifact, jointId, decision) {
  if (!decision || decision.action !== "accept") return null;
  const candidate = candidatesForJoint(artifact, jointId)
    .find((item) => item.candidate_id === decision.candidate_id);
  return candidate ? [...candidate.xy] : null;
}

export function decisionMatchesArtifact(decision, artifactSha) {
  return Boolean(
    decision
    && SHA256.test(String(artifactSha))
    && decision.candidate_artifact_sha256 === artifactSha,
  );
}

export function decisionMatchesSelection(decision, artifactSha, candidateId) {
  if (!decisionMatchesArtifact(decision, artifactSha)) return false;
  if (decision.action === "unobservable") return true;
  return CANDIDATE_ACTIONS.has(decision.action)
    && typeof candidateId === "string"
    && decision.candidate_id === candidateId;
}

export function syncedReasonValue({
  currentValue,
  lastSyncedReason,
  nextReason,
  jointChanged,
  decisionChanged,
}) {
  if (jointChanged || (decisionChanged && currentValue === lastSyncedReason)) {
    return nextReason;
  }
  return currentValue;
}

export function buildJointDecision({ action, artifactSha, candidateId, point, reason = "" }) {
  if (!ACTIONS.has(action)) throw new Error("不支持的审查操作");
  if (!SHA256.test(String(artifactSha))) throw new Error("候选 artifact 标识无效");
  if (CANDIDATE_ACTIONS.has(action) && (typeof candidateId !== "string" || !SAFE_ID.test(candidateId))) {
    throw new Error("请先选择一个候选点");
  }
  const trimmedReason = typeof reason === "string" ? reason.trim() : "";
  if (["adjust", "reject", "unobservable"].includes(action) && !trimmedReason) {
    throw new Error("此操作需要填写理由");
  }
  if (trimmedReason.length > 1000) throw new Error("理由不能超过 1000 个字符");

  const decision = { action, candidate_artifact_sha256: String(artifactSha) };
  if (CANDIDATE_ACTIONS.has(action)) decision.candidate_id = String(candidateId);
  if (action === "adjust") {
    if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite)) {
      throw new Error("当前关节位置无效");
    }
    decision.final_xy = point.map((value) => Math.round(value * 10) / 10);
  }
  if (trimmedReason) decision.reason = trimmedReason;
  return decision;
}

export function applyCandidateDecision(draftState, jointId, decision) {
  const id = String(jointId);
  if (!draftState.jointDecisions) draftState.jointDecisions = {};
  if (!draftState.jointOverrides) draftState.jointOverrides = {};
  delete draftState.jointOverrides[id];
  draftState.jointDecisions[id] = decision;
  return draftState;
}
