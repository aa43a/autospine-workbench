import { API_BASE, apiRequest } from "./api.js";
import { createCandidateCard } from "./candidate-review-elements.js";
import { captureCandidateFocus, scheduleCandidateFocus } from "./candidate-review-focus.js";
import { renderCandidateOverlay } from "./candidate-review-overlay.js";
import { updateCandidateDecisionStatus } from "./candidate-review-status.js";
import { createGeometryEvidenceController } from "./geometry-evidence-controller.js";
import {
  acceptedCandidatePoint,
  applyCandidateDecision,
  buildJointDecision,
  candidatesForJoint,
  createCandidateReviewState,
  decisionMatchesArtifact,
  decisionMatchesSelection,
  reduceCandidateReview,
  syncedReasonValue,
} from "./candidate-review-state.js";

const ACTION_LABELS = {
  accept: "接受候选",
  adjust: "按当前位置调整",
  reject: "拒绝候选",
  unobservable: "标记不可观测",
};
export function createCandidateReview({ elements, draftState, getJoint, getCanvasSize, onDecision, announce }) {
  let review = createCandidateReviewState();
  let projectSequence = 0;
  let artifactSequence = 0;
  let lastJointSyncKey = null;
  let lastSyncedReason = "";
  const artifactsBySha = new Map();
  const geometryEvidence = createGeometryEvidenceController({ elements });

  elements.candidateArtifactSelect.addEventListener("change", (event) => loadArtifact(event.target.value));
  elements.candidateRetryBtn.addEventListener("click", retryLoad);
  for (const action of Object.keys(ACTION_LABELS)) {
    elements[`candidate${capitalize(action)}Btn`].addEventListener("click", () => commit(action));
  }
  elements.candidateReason.addEventListener("input", () => {
    elements.candidateReason.setCustomValidity("");
  });
  async function loadProject(projectId) {
    const projectToken = ++projectSequence;
    artifactSequence += 1;
    artifactsBySha.clear();
    lastJointSyncKey = null;
    lastSyncedReason = "";
    elements.candidateReason.value = "";
    review = reduceCandidateReview(review, { type: "project-loading", projectId: String(projectId) });
    render();
    try {
      const payload = await apiRequest(`${API_BASE}/${encodeURIComponent(projectId)}/candidate-artifacts`);
      if (projectToken !== projectSequence) return;
      review = reduceCandidateReview(review, { type: "index-loaded", payload });
      render();
      const desiredSha = currentDecision()?.candidate_artifact_sha256;
      const nextSha = review.items.some((item) => item.artifact_sha256 === desiredSha) ? desiredSha : review.artifactSha;
      if (nextSha) await loadArtifact(nextSha);
    } catch (error) {
      if (projectToken !== projectSequence) return;
      review = reduceCandidateReview(review, { type: "failed", error });
      render();
    }
  }
  async function loadArtifact(artifactSha) {
    if (!review.items.some((item) => item.artifact_sha256 === artifactSha)) return;
    const artifactToken = ++artifactSequence;
    const projectId = review.projectId;
    review = reduceCandidateReview(review, { type: "artifact-loading", artifactSha });
    render();
    try {
      const payload = await apiRequest(
        `${API_BASE}/${encodeURIComponent(projectId)}/candidate-artifacts/${encodeURIComponent(artifactSha)}`,
      );
      if (artifactToken !== artifactSequence || projectId !== review.projectId) return;
      const decision = currentDecision();
      review = reduceCandidateReview(review, {
        type: "artifact-loaded",
        payload,
        preferredId: decision?.candidate_artifact_sha256 === artifactSha ? decision.candidate_id : null,
        clearCandidate: isUnobservableOnArtifact(decision, artifactSha),
      });
      artifactsBySha.set(artifactSha, review.artifact);
      render();
      announce?.(`已加载候选 artifact ${artifactSha.slice(0, 8)}`);
    } catch (error) {
      if (artifactToken !== artifactSequence || projectId !== review.projectId) return;
      review = reduceCandidateReview(review, { type: "failed", error });
      render();
    }
  }
  function setJoint(jointId) {
    const id = jointId == null ? null : String(jointId);
    const changed = id !== review.jointId;
    const decision = id == null ? null : draftState.jointDecisions?.[id];
    const syncKey = jointSyncKey(id, decision);
    const decisionChanged = syncKey !== lastJointSyncKey;
    if (!changed && !decisionChanged) return;
    const focus = captureCandidateFocus(elements);
    const nextReason = decision?.reason || "";
    elements.candidateReason.value = syncedReasonValue({
      currentValue: elements.candidateReason.value,
      lastSyncedReason,
      nextReason,
      jointChanged: changed,
      decisionChanged,
    });
    lastSyncedReason = nextReason;
    lastJointSyncKey = syncKey;
    review = reduceCandidateReview(review, {
      type: "joint-selected",
      jointId: id,
      preferredId: decision?.candidate_artifact_sha256 === review.artifactSha ? decision.candidate_id : null,
      clearCandidate: isUnobservableOnArtifact(decision, review.artifactSha),
    });
    render();
    scheduleCandidateFocus(elements, focus);
    const desiredSha = decision?.candidate_artifact_sha256;
    if ((changed || decisionChanged) && desiredSha && desiredSha !== review.artifactSha
        && review.items.some((item) => item.artifact_sha256 === desiredSha)) {
      loadArtifact(desiredSha);
    }
  }
  function chooseCandidate(candidateId, focusKind) {
    review = reduceCandidateReview(review, { type: "candidate-selected", candidateId });
    render();
    scheduleCandidateFocus(elements, { kind: focusKind, candidateId });
    announce?.(`已选择候选 ${candidateOrdinal(candidateId)}`);
  }
  function retryLoad() {
    if (review.status !== "error") return;
    if (review.items.length && review.artifactSha) {
      loadArtifact(review.artifactSha);
      return;
    }
    if (review.projectId != null) loadProject(review.projectId);
  }
  function commit(action) {
    const joint = getJoint();
    elements.candidateReason.setCustomValidity("");
    try {
      if (!joint || String(joint.id) !== review.jointId) throw new Error("请先选择一个关节");
      const decision = buildJointDecision({
        action,
        artifactSha: review.artifactSha,
        candidateId: review.candidateId,
        point: [Number(joint.x), Number(joint.y)],
        reason: elements.candidateReason.value,
      });
      applyCandidateDecision(draftState, review.jointId, decision);
      onDecision?.(review.jointId, decision);
      render();
      announce?.(`关节 ${review.jointId}：${ACTION_LABELS[action]}`);
    } catch (error) {
      const reasonError = error.message.includes("理由");
      elements.candidateReason.setCustomValidity(reasonError ? error.message : "");
      if (reasonError) elements.candidateReason.focus();
      updateCandidateDecisionStatus(elements.candidateDecisionStatus, "error", error.message);
      announce?.(error.message);
    }
  }
  function render() {
    renderStatus();
    renderArtifactPicker();
    renderJointCandidates();
    renderOverlay();
    geometryEvidence.sync(review);
  }
  function renderStatus() {
    const messages = {
      loading: "正在加载候选 artifact 列表…",
      "artifact-loading": "正在读取所选候选 artifact…",
      empty: "此项目还没有候选 artifact。请先运行候选生成阶段。",
      error: `候选数据加载失败：${review.error?.message || "未知后端错误"}`,
      idle: "尚未加载候选数据。",
    };
    elements.candidateLoadState.hidden = review.status === "ready";
    elements.candidateLoadState.dataset.state = review.status;
    elements.candidateLoadState.textContent = messages[review.status] || "";
    elements.candidateRetryBtn.hidden = review.status !== "error";
    elements.candidateReviewBody.hidden = review.items.length === 0;
  }
  function renderArtifactPicker() {
    const select = elements.candidateArtifactSelect;
    select.replaceChildren();
    review.items.forEach((item, index) => {
      const option = new Option(
        `${index + 1}. ${item.provider} v${item.provider_version} · ${item.candidate_count} 候选 · ${item.artifact_sha256.slice(0, 8)}`,
        item.artifact_sha256,
      );
      select.add(option);
    });
    select.value = review.artifactSha || "";
    select.disabled = review.status === "artifact-loading";
    const item = review.items.find((entry) => entry.artifact_sha256 === review.artifactSha);
    if (!item) {
      elements.candidateArtifactMeta.textContent = "—";
      return;
    }
    const methods = Object.entries(item.method_counts || {}).map(([name, count]) => `${name} ×${count}`).join("、") || "无";
    const flags = item.qa_flags?.length ? item.qa_flags.join("、") : "无";
    elements.candidateArtifactMeta.textContent = `${item.joint_count} 关节 · QA ${item.qa_status}（${flags}）· 方法 ${methods}`;
  }
  function renderJointCandidates() {
    const ready = review.status === "ready" && review.jointId;
    elements.candidateJointEmpty.hidden = Boolean(ready);
    elements.candidateJointBody.hidden = !ready;
    elements.candidateList.replaceChildren();
    if (!ready) return;
    const jointEvidence = review.artifact.joints?.[review.jointId];
    const candidates = candidatesForJoint(review.artifact, review.jointId);
    elements.candidateObservability.textContent = jointEvidence
      ? `可观测性：${jointEvidence.observability} · 共 ${candidates.length} 个候选`
      : "此 artifact 未提供当前关节";
    candidates.forEach((candidate, index) => elements.candidateList.append(
      createCandidateCard({
        candidate,
        index,
        selected: candidate.candidate_id === review.candidateId,
        onChoose: () => chooseCandidate(candidate.candidate_id, "list"),
      }),
    ));
    if (!candidates.length) {
      const empty = document.createElement("li");
      empty.className = "candidate-empty";
      empty.textContent = "当前 artifact 没有此关节的候选点；仍可标记为不可观测。";
      elements.candidateList.append(empty);
    }
    const decision = currentDecision();
    const decisionMatches = decisionMatchesArtifact(decision, review.artifactSha);
    const selectionMatches = decisionMatchesSelection(decision, review.artifactSha, review.candidateId);
    const manual = Boolean(draftState.jointOverrides?.[review.jointId]);
    const statusKind = decision
      ? (selectionMatches ? "success" : "warning")
      : "neutral";
    const statusText = decision && !decisionMatches
      ? `当前草稿绑定 artifact ${shortSha(decision.candidate_artifact_sha256)}；当前仅查看 ${shortSha(review.artifactSha)}。`
      : decision && !selectionMatches
        ? `当前草稿绑定候选 ${decision.candidate_id || "无"}；当前选中 ${review.candidateId || "无"}。`
      : decision
        ? `当前草稿：${ACTION_LABELS[decision.action] || decision.action}${decision.reason ? ` · ${decision.reason}` : ""}`
      : manual ? "当前为人工坐标；提交候选操作后将由该操作替代。" : "尚未写入候选审查决策。";
    updateCandidateDecisionStatus(elements.candidateDecisionStatus, statusKind, statusText);
    for (const action of Object.keys(ACTION_LABELS)) {
      const button = elements[`candidate${capitalize(action)}Btn`];
      button.disabled = action !== "unobservable" && !review.candidateId;
      button.setAttribute("aria-pressed", String(selectionMatches && decision?.action === action));
    }
  }
  function renderOverlay() {
    renderCandidateOverlay({
      group: elements.candidateGroup,
      artifact: review.status === "ready" ? review.artifact : null,
      jointId: review.jointId,
      selectedCandidateId: review.candidateId,
      getCanvasSize,
      onChoose: chooseCandidate,
    });
  }
  function currentDecision() {
    return review.jointId == null ? null : draftState.jointDecisions?.[review.jointId] || null;
  }
  function candidateOrdinal(candidateId) {
    return candidatesForJoint(review.artifact, review.jointId)
      .findIndex((candidate) => candidate.candidate_id === candidateId) + 1;
  }
  function resolveDecisionPoint(jointId, decision) {
    const artifact = artifactsBySha.get(decision?.candidate_artifact_sha256);
    return acceptedCandidatePoint(artifact, jointId, decision);
  }

  return { loadProject, setJoint, render, renderOverlay, resolveDecisionPoint };
}

function jointSyncKey(jointId, decision) {
  if (jointId == null) return "";
  return [
    jointId,
    decision?.action || "",
    decision?.candidate_artifact_sha256 || "",
    decision?.candidate_id || "",
    decision?.reason || "",
  ].join("\u001f");
}

function capitalize(value) {
  return value[0].toUpperCase() + value.slice(1);
}

function isUnobservableOnArtifact(decision, artifactSha) {
  return decision?.action === "unobservable"
    && decision.candidate_artifact_sha256 === artifactSha;
}

function shortSha(value) {
  return typeof value === "string" ? value.slice(0, 8) : "未知";
}
