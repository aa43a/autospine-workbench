import { API_BASE, apiRequest } from "./api.js";
import { mountSplitReview } from "./split-review-markup.js";
import {
  applySplitDecision,
  buildSplitDecision,
  isCurrentSplitArtifact,
  isSplitReviewLayer,
  removeSplitDecision,
  shouldShowSplitReviewBody,
  shortSha,
  splitArtifactsForLayer,
  splitDecisionStatus,
  splitPartImageUrl,
} from "./split-review-state.js";

const SIDES = ["left", "right"];

export function createSplitReview({
  mount,
  draftState,
  getResolvedSnapshotSha,
  onDecision,
  announce,
  request = apiRequest,
  apiBase = API_BASE,
}) {
  const elements = mountSplitReview(mount);
  let projectId = null;
  let selectedLayer = null;
  let indexPayload = { items: [] };
  let indexStatus = "idle";
  let artifactStatus = "idle";
  let artifact = null;
  let artifactSha = null;
  let error = null;
  let projectSequence = 0;
  let artifactSequence = 0;
  const artifactCache = new Map();

  elements.reloadBtn.addEventListener("click", () => loadProject(projectId));
  elements.artifactSelect.addEventListener("change", (event) => {
    loadArtifact(event.target.value);
  });
  elements.acceptBtn.addEventListener("click", () => commit("accept"));
  elements.rejectBtn.addEventListener("click", () => commit("reject"));
  elements.removeBtn.addEventListener("click", removeDecision);
  elements.reason.addEventListener("input", () => elements.reason.setCustomValidity(""));

  async function loadProject(nextProjectId) {
    projectId = nextProjectId == null ? null : String(nextProjectId);
    const token = ++projectSequence;
    artifactSequence += 1;
    indexPayload = { items: [] };
    indexStatus = projectId ? "loading" : "idle";
    artifactStatus = "idle";
    artifact = null;
    artifactSha = null;
    error = null;
    artifactCache.clear();
    elements.cliCommand.textContent = `python -m autospine_workbench publish-split-previews ${projectId || "<project-id>"}`;
    render();
    if (!projectId) return;
    try {
      const payload = await request(
        `${apiBase}/${encodeURIComponent(projectId)}/split-previews`,
      );
      if (token !== projectSequence) return;
      indexPayload = payload || { items: [] };
      indexStatus = "ready";
      syncArtifactSelection();
    } catch (nextError) {
      if (token !== projectSequence) return;
      indexStatus = "error";
      error = nextError;
      render();
    }
  }

  function setLayer(layer) {
    const next = isSplitReviewLayer(layer) ? layer : null;
    const changed = String(next?.id ?? "") !== String(selectedLayer?.id ?? "");
    selectedLayer = next;
    if (changed) {
      artifactSequence += 1;
      artifact = null;
      artifactSha = null;
      artifactStatus = "idle";
      elements.reason.value = currentDecision()?.reason || "";
      elements.reason.setCustomValidity("");
    }
    syncArtifactSelection();
  }

  function availableArtifacts() {
    if (!selectedLayer) return [];
    return splitArtifactsForLayer(
      indexPayload,
      String(selectedLayer.id),
      String(getResolvedSnapshotSha?.() || ""),
      currentDecision()?.split_artifact_sha256 || "",
    );
  }

  function syncArtifactSelection() {
    if (!selectedLayer || indexStatus !== "ready") {
      render();
      return;
    }
    const items = availableArtifacts();
    const selectedExists = items.some((item) => item.artifact_sha256 === artifactSha);
    const nextSha = selectedExists ? artifactSha : items[0]?.artifact_sha256 || null;
    if (!nextSha) {
      artifact = null;
      artifactSha = null;
      artifactStatus = "empty";
      render();
      return;
    }
    if (artifact && nextSha === artifactSha) {
      render();
      return;
    }
    loadArtifact(nextSha);
  }

  async function loadArtifact(nextSha) {
    if (!availableArtifacts().some((item) => item.artifact_sha256 === nextSha)) return;
    artifactSha = nextSha;
    error = null;
    if (artifactCache.has(nextSha)) {
      artifact = artifactCache.get(nextSha);
      artifactStatus = "ready";
      render();
      return;
    }
    const token = ++artifactSequence;
    const boundProject = projectId;
    artifact = null;
    artifactStatus = "loading";
    render();
    try {
      const payload = await request(
        `${apiBase}/${encodeURIComponent(boundProject)}/split-previews/${encodeURIComponent(nextSha)}`,
      );
      if (token !== artifactSequence || boundProject !== projectId) return;
      artifactCache.set(nextSha, payload);
      artifact = payload;
      artifactStatus = "ready";
      render();
      announce?.(`已加载切分预览 ${shortSha(nextSha)}`);
    } catch (nextError) {
      if (token !== artifactSequence || boundProject !== projectId) return;
      artifactStatus = "error";
      error = nextError;
      render();
    }
  }

  function commit(action) {
    elements.reason.setCustomValidity("");
    try {
      if (!selectedLayer || !artifactSha || !artifact) throw new Error("当前没有可审查切分预览");
      if (!isCurrentSplitArtifact(artifact, getResolvedSnapshotSha?.())) {
        throw new Error("历史切分预览仅供回看，不能写入新决定");
      }
      const decision = buildSplitDecision(action, artifactSha, elements.reason.value);
      applySplitDecision(draftState, selectedLayer.id, decision);
      onDecision?.(String(selectedLayer.id), decision);
      render();
      announce?.(action === "accept" ? "已接受当前切分预览" : "已拒绝当前切分预览");
    } catch (nextError) {
      const reasonError = nextError.message.includes("理由");
      elements.reason.setCustomValidity(reasonError ? nextError.message : "");
      if (reasonError) {
        elements.reason.reportValidity();
        elements.reason.focus();
      }
      elements.decisionStatus.dataset.status = "error";
      elements.decisionStatus.textContent = nextError.message;
      announce?.(nextError.message);
    }
  }

  function removeDecision() {
    if (!selectedLayer || !removeSplitDecision(draftState, selectedLayer.id)) return;
    elements.reason.value = "";
    elements.reason.setCustomValidity("");
    onDecision?.(String(selectedLayer.id), null);
    render();
    announce?.("已移除当前图层的切分决定");
  }

  function currentDecision() {
    return selectedLayer ? draftState.splitDecisions?.[String(selectedLayer.id)] || null : null;
  }

  function storedDecision() {
    return selectedLayer
      ? draftState.resolvedSplitDecisions?.[String(selectedLayer.id)] || null
      : null;
  }

  function render() {
    elements.section.hidden = !selectedLayer;
    if (!selectedLayer) return;
    renderStatus();
    renderArtifactPicker();
    renderArtifact();
    renderDecision();
  }

  function renderStatus() {
    const messages = {
      idle: "正在等待预览索引。",
      loading: "正在加载切分预览索引…",
      error: `切分预览加载失败：${error?.message || "未知错误"}`,
      empty: "当前图层没有已发布的切分预览。",
      "artifact-loading": "正在读取当前切分预览…",
    };
    const status = indexStatus === "error" ? "error"
      : indexStatus === "loading" ? "loading"
        : artifactStatus === "error" ? "error"
          : artifactStatus === "loading" ? "artifact-loading"
            : artifactStatus === "empty" ? "empty" : artifactStatus;
    elements.loadState.hidden = status === "ready";
    elements.loadState.dataset.status = status;
    elements.loadState.textContent = messages[status]
      || (status === "error" ? `切分预览加载失败：${error?.message || "未知错误"}` : "");
    elements.reloadBtn.disabled = indexStatus === "loading" || artifactStatus === "loading";
    elements.cliHint.hidden = status === "ready";
    elements.body.hidden = !shouldShowSplitReviewBody(
      artifact, currentDecision(), availableArtifacts().length > 0,
    );
  }

  function renderArtifactPicker() {
    const items = availableArtifacts();
    elements.artifactSelect.replaceChildren();
    for (const [index, item] of items.entries()) {
      const option = elements.section.ownerDocument.createElement("option");
      const current = item.resolved_snapshot_sha256 === getResolvedSnapshotSha?.();
      option.value = item.artifact_sha256;
      option.textContent = `${index + 1}. ${shortSha(item.artifact_sha256)} · ${current ? "当前" : "历史"} snapshot`;
      elements.artifactSelect.append(option);
    }
    elements.artifactSelect.value = artifactSha || "";
    elements.artifactSelect.disabled = items.length < 2 || artifactStatus === "loading";
    const selected = items.find((item) => item.artifact_sha256 === artifactSha);
    const current = selected?.resolved_snapshot_sha256 === getResolvedSnapshotSha?.();
    elements.artifactMeta.textContent = items.length
      ? `${items.length} 个预览 · ${shortSha(artifactSha)} · ${current ? "当前 snapshot" : "历史 snapshot（只读）"}`
      : "此图层没有可用预览";
  }

  function renderArtifact() {
    elements.evidence.replaceChildren();
    elements.parts.replaceChildren();
    if (!artifact) return;
    const target = artifact.review_target || {};
    const source = target.source || {};
    const operation = target.operation || {};
    appendEvidence("Source", `${source.layer_id || "—"} · ${source.canonical_role || "—"}`);
    appendEvidence("Source raster", source.raster_sha256);
    appendEvidence("Resolved snapshot", artifact.resolved_snapshot_sha256);
    appendEvidence("Algorithm", `${operation.algorithm?.id || "—"} v${operation.algorithm?.version || "—"}`);
    appendEvidence("Config hash", artifact.operation_config_sha256);
    appendEvidence("Review hash", artifact.review_target_sha256);
    appendEvidence("Manifest hash", artifact.layer_manifest_sha256);
    for (const side of SIDES) renderPart(side, target.parts?.[side]);
  }

  function appendEvidence(label, value) {
    const doc = elements.section.ownerDocument;
    const row = doc.createElement("div");
    const term = doc.createElement("dt");
    const detail = doc.createElement("dd");
    term.textContent = label;
    detail.textContent = String(value || "—");
    row.append(term, detail);
    elements.evidence.append(row);
  }

  function renderPart(side, part = {}) {
    const doc = elements.section.ownerDocument;
    const figure = doc.createElement("figure");
    figure.className = "split-review-part";
    figure.dataset.side = side;
    const image = doc.createElement("img");
    image.src = splitPartImageUrl(apiBase, projectId, artifactSha, side);
    image.alt = `${side === "left" ? "左侧" : "右侧"}切分子图层 ${part.layer_id || ""}`;
    image.loading = "lazy";
    image.decoding = "async";
    const caption = doc.createElement("figcaption");
    const title = doc.createElement("strong");
    const facts = doc.createElement("small");
    title.textContent = `${side.toUpperCase()} · ${part.layer_id || "—"}`;
    const pivot = Array.isArray(part.pivot_xy) ? part.pivot_xy.join(", ") : "—";
    facts.textContent = `${part.candidate_bone || "未绑定"} · pivot ${pivot} · ${shortSha(part.raster_sha256)}`;
    caption.append(title, facts);
    figure.append(image, caption);
    elements.parts.append(figure);
  }

  function renderDecision() {
    const decision = currentDecision();
    const status = splitDecisionStatus(decision, storedDecision(), artifactSha);
    elements.statusBadge.dataset.status = status.kind;
    elements.statusBadge.textContent = status.label;
    elements.decisionStatus.dataset.status = status.kind;
    const statusText = decision?.reason
      ? `${status.label} · ${decision.reason}` : status.label;
    const current = isCurrentSplitArtifact(artifact, getResolvedSnapshotSha?.());
    elements.decisionStatus.textContent = artifact && !current
      ? `${statusText} · 历史 snapshot 只读，仅可移除已有决定` : statusText;
    const ready = artifactStatus === "ready" && current;
    elements.acceptBtn.disabled = !ready;
    elements.rejectBtn.disabled = !ready;
    elements.removeBtn.disabled = !decision;
    elements.acceptBtn.setAttribute("aria-pressed", String(
      decision?.action === "accept" && decision.split_artifact_sha256 === artifactSha,
    ));
    elements.rejectBtn.setAttribute("aria-pressed", String(
      decision?.action === "reject" && decision.split_artifact_sha256 === artifactSha,
    ));
  }

  return { loadProject, setLayer, render };
}
