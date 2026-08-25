const STAGE_LABELS = {
  ingest: "导入",
  decomposition: "分层",
  layers: "图层检查",
  anchors: "锚点",
  skeleton: "骨骼校正",
  rig: "骨骼校正",
  bindings: "绑定",
  animation: "动画",
  qa: "能力验收",
  export: "导出",
  "psd-audit": "PSD 审计",
  "layer-review": "图层检查",
  "skeleton-review": "骨骼校正",
  "rig-review": "绑定复核",
  "spine-export": "Spine 导出",
};

export function normalizeWorkflow(raw) {
  let stages = [];
  if (Array.isArray(raw)) stages = raw;
  else if (Array.isArray(raw?.steps)) stages = raw.steps;
  else if (Array.isArray(raw?.stages)) stages = raw.stages;
  else if (raw && typeof raw === "object") {
    stages = Object.entries(raw).map(([id, value]) => {
      if (value && typeof value === "object") return { id, ...value };
      return { id, status: value };
    });
  }

  if (!stages.length) {
    stages = ["layers", "skeleton", "bindings", "qa"].map((id, index) => ({
      id,
      status: index === 0 ? "active" : "pending",
    }));
  }

  return stages.map((stage, index) => {
    const item = typeof stage === "string" ? { id: stage } : stage;
    const id = String(item.id ?? item.name ?? `stage-${index + 1}`);
    return {
      ...item,
      id,
      label: item.label || item.title || STAGE_LABELS[id] || id,
      status: String(item.status || item.state || "pending").toLowerCase(),
    };
  });
}

export function compositeQaFlag(auditWarnings) {
  if (auditWarnings?.high_composite_error) {
    return {
      code: "COMPOSITE_ERROR",
      message: "背景匹配后的可见合成仍有明显差异，需要目视复核",
      severity: "warning",
      layerId: null,
    };
  }
  if (auditWarnings?.raw_composite_difference
    && auditWarnings?.composite_quality?.status === "unavailable") {
    return {
      code: "COMPOSITE_ANALYSIS_REQUIRED",
      message: "raw RGBA 表示存在差异，尚需运行可见像素合成 QA",
      severity: "warning",
      layerId: null,
    };
  }
  return null;
}

export function unresolvedJointIds(project, joints = []) {
  const backendIds = project?.resolved?.qa?.unresolved_joint_ids;
  if (Array.isArray(backendIds)) return backendIds.map(String);
  return joints
    .filter((joint) => joint?.review_state === "unreviewed" && Number(joint?.confidence ?? 0) < 0.55)
    .map((joint) => String(joint.id));
}

export function confidenceLevel(value) {
  const score = Number(value);
  if (Number.isFinite(score) && score >= 0.8) return "high";
  if (Number.isFinite(score) && score >= 0.55) return "medium";
  return Number.isFinite(score) ? "low" : "unknown";
}

export function formatConfidence(value) {
  const score = Number(value);
  return Number.isFinite(score) ? `${Math.round(score * 100)}%` : "—";
}

export function setConfidenceBadge(element, value) {
  element.textContent = formatConfidence(value);
  element.dataset.level = confidenceLevel(value);
}
