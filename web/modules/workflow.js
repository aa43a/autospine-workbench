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
