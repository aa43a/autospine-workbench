"use strict";

import { API_BASE, apiRequest } from "./api.js";
import { candidatesForJoint } from "./candidate-review-state.js";
import {
  geometryReferencesForCandidate,
  resolveGeometryEvidenceTargets,
} from "./geometry-evidence-ref.js";
import {
  describeGeometryTargets,
  renderGeometryEvidence,
} from "./geometry-evidence-renderer.js";

export function createGeometryEvidenceController({
  elements,
  request = apiRequest,
  renderEvidence = renderGeometryEvidence,
}) {
  let sequence = 0;
  let desired = null;
  const documents = new Map();

  elements.geometryEvidenceRetryBtn.addEventListener("click", () => {
    if (desired) load(desired, true);
  });

  function sync(review) {
    const candidate = selectedCandidate(review);
    if (!candidate) {
      reset(review.status === "ready" ? "选择候选后回看固定几何证据。" : "等待候选数据。", "neutral");
      return;
    }
    let references;
    try {
      references = geometryReferencesForCandidate(candidate);
    } catch (error) {
      failWithoutRetry(error);
      return;
    }
    if (!references.length) {
      reset("当前候选没有固定 geometry evidence 引用。", "neutral");
      return;
    }
    const shas = new Set(references.map((item) => item.sha256));
    if (shas.size !== 1) {
      failWithoutRetry(new Error("当前候选混用了多个几何证据 artifact"));
      return;
    }
    const sha256 = references[0].sha256;
    const spec = {
      projectId: String(review.projectId),
      sha256,
      references,
      key: `${review.projectId}\u001f${sha256}\u001f${references.map((item) => item.fragment).join("\u001e")}`,
    };
    if (desired?.key === spec.key) return;
    desired = spec;
    sequence += 1;
    const cached = documents.get(cacheKey(spec));
    if (cached) {
      resolveAndRender(spec, cached);
      return;
    }
    load(spec, false);
  }

  async function load(spec, force) {
    desired = spec;
    const token = ++sequence;
    if (force) documents.delete(cacheKey(spec));
    clearEvidence();
    showStatus("loading", `正在加载几何证据 ${spec.sha256.slice(0, 8)}…`);
    elements.geometryEvidenceRetryBtn.hidden = true;
    try {
      const document = await request(
        `${API_BASE}/${encodeURIComponent(spec.projectId)}/geometry-evidence/${encodeURIComponent(spec.sha256)}`,
      );
      if (token !== sequence || desired?.key !== spec.key) return;
      documents.set(cacheKey(spec), document);
      resolveAndRender(spec, document);
    } catch (error) {
      if (token !== sequence || desired?.key !== spec.key) return;
      documents.delete(cacheKey(spec));
      clearEvidence();
      showStatus("error", `几何证据加载失败：${error.message || "未知错误"}`);
      elements.geometryEvidenceRetryBtn.hidden = false;
    }
  }

  function resolveAndRender(spec, document) {
    try {
      const targets = resolveGeometryEvidenceTargets(document, {
        projectId: spec.projectId,
        sha256: spec.sha256,
        references: spec.references,
      });
      renderEvidence(elements.geometryEvidenceGroup, targets);
      showStatus("ready", `${spec.sha256.slice(0, 8)} · ${describeGeometryTargets(targets)}`);
      elements.geometryEvidenceRetryBtn.hidden = true;
    } catch (error) {
      documents.delete(cacheKey(spec));
      clearEvidence();
      showStatus("error", `几何证据损坏：${error.message}`);
      elements.geometryEvidenceRetryBtn.hidden = false;
    }
  }

  function reset(message, kind) {
    desired = null;
    sequence += 1;
    clearEvidence();
    showStatus(kind, message);
    elements.geometryEvidenceRetryBtn.hidden = true;
  }

  function failWithoutRetry(error) {
    desired = null;
    sequence += 1;
    clearEvidence();
    showStatus("error", `几何证据引用损坏：${error.message}`);
    elements.geometryEvidenceRetryBtn.hidden = true;
  }

  function clearEvidence() {
    elements.geometryEvidenceGroup.replaceChildren();
  }

  function showStatus(kind, message) {
    const status = elements.geometryEvidenceStatus;
    if (status.dataset.kind !== kind) status.dataset.kind = kind;
    if (status.textContent !== message) status.textContent = message;
  }

  return { sync };
}

function selectedCandidate(review) {
  if (review.status !== "ready" || !review.candidateId) return null;
  return candidatesForJoint(review.artifact, review.jointId)
    .find((candidate) => candidate.candidate_id === review.candidateId) || null;
}

function cacheKey(spec) {
  return `${spec.projectId}:${spec.sha256}`;
}
