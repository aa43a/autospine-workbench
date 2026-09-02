"use strict";

const IDS = [
  "motionBadge", "motionStatus", "motionProgress", "motionProgressText",
  "motionAttempt", "motionAttemptState", "motionAttemptCode",
  "motionResult", "motionResultHeading", "motionFacts", "motionInventory",
  "motionScopes", "motionReleaseReasons", "motionTechnical",
  "motionFailure", "motionFailureHeading", "motionFailureMessage",
  "retryMotionBtn", "returnToSeamLink", "returnToSeamTop",
];

const FILE_LABELS = Object.freeze({
  "body-sway-motion-consumer-admission-v2.json":
    ["动作准入", "已复核来源与 setup-local 编译边界"],
  "motion-instance-v3.json":
    ["MotionInstance v3", "版本中立的 setup-local 骨骼时间线"],
  "run-manifest-v2.json":
    ["运行回执", "输入、输出与能力边界的不可变记录"],
});
const REASON_LABELS = Object.freeze({
  attachment_area_overlap_not_assessed: "附件重叠面积尚未评估",
  dynamic_seam_safety_unproven: "动态接缝安全尚未证明",
  full_attachment_boundary_raster_visual_regression_missing:
    "完整附件边界尚缺 Raster 视觉回归",
  persistent_current_head_authority_not_granted: "尚未授予持久 current-head 权限",
  publishable_timeline_not_emitted: "尚未生成可发布时间线",
  raster_visual_quality_unproven: "Raster 视觉质量尚未证明",
  runtime_equivalence_unproven: "官方 Runtime 等价性尚未证明",
  spine_adapter_not_emitted: "尚未生成 Spine adapter",
});

export function motionInstanceV3V2Elements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const node = doc.getElementById(id);
    if (!node) throw new Error(`缺少 P10.6b v2 界面元素：${id}`);
    return [id, node];
  }));
}

export function renderMotionInstanceV3V2Loading(elements) {
  badge(elements.motionBadge, "正在自动读取", "warning");
  status(elements, "正在闭合已完成的 P10.5d v2；无需选择项目、文件或 SHA。", "warning");
  elements.motionProgress.max = 1;
  elements.motionProgress.value = 0;
  elements.motionProgressText.textContent = "校验精确来源…";
  renderAttempt(elements, null);
  elements.motionResult.hidden = true;
  elements.motionFailure.hidden = true;
  elements.retryMotionBtn.hidden = true;
}

export function renderMotionInstanceV3V2Run(elements, state) {
  if (state.status === "ready") {
    badge(elements.motionBadge, "来源已就绪", "success");
    status(elements, "唯一精确来源可用，正在自动创建第一次生成任务。", "success");
    elements.motionProgress.max = 1;
    elements.motionProgress.value = 0;
    elements.motionProgressText.textContent = "即将开始…";
    return;
  }
  const { run } = state;
  renderAttempt(elements, run);
  elements.motionProgress.max = run.progress.total;
  elements.motionProgress.value = run.progress.current;
  elements.motionProgressText.textContent = `${run.progress.current} / ${run.progress.total}`
    + ` · ${stageLabel(run.stage)}`;
  const active = state.status === "queued" || state.status === "running";
  badge(elements.motionBadge, active ? `第 ${run.attempt} 次生成中`
    : state.status === "completed" ? "生成已完成" : "本次尝试已封存",
  active ? "warning" : state.status === "completed" ? "success" : "error");
  status(elements, active
    ? "正在生成并密封 MotionInstance v3；刷新页面不会创建重复尝试。"
    : state.status === "completed" ? "生成完成，正在执行精确读回。"
      : `第 ${run.attempt} 次尝试未完成，旧回执保持不变。`,
  active ? "warning" : state.status === "completed" ? "success" : "error");
}

export function renderMotionInstanceV3V2Failure(elements, run, message) {
  const retryable = Boolean(run?.retryable);
  badge(elements.motionBadge, retryable ? "可确认后重试" : "终止且不可重试", "error");
  status(elements, `P10.6b v2 未形成可用输出：${message}`, "error");
  renderAttempt(elements, run);
  elements.motionResult.hidden = true;
  elements.motionFailure.hidden = false;
  elements.motionFailureHeading.textContent = run
    ? `第 ${run.attempt} 次尝试已作为不可变回执保留`
    : "没有生成 MotionInstance v3";
  elements.motionFailureMessage.textContent = retryable
    ? "不会使用部分结果。确认重试后会创建新 attempt，不会覆盖本次失败记录。"
    : "需要先修复来源或本地服务；系统不会猜测输出，也不会解除后续门禁。";
  elements.retryMotionBtn.hidden = !retryable;
}

export function renderMotionInstanceV3V2Result(elements, value) {
  badge(elements.motionBadge, "MotionInstance v3 已发出", "success");
  status(elements, "三文件 bundle 已密封并完成精确读回；后续门禁仍保持阻塞。", "success");
  renderAttempt(elements, value.run);
  elements.motionProgress.max = value.run.progress.total;
  elements.motionProgress.value = value.run.progress.total;
  elements.motionProgressText.textContent = "精确读回通过";
  elements.motionFailure.hidden = true;
  elements.motionResult.hidden = false;
  renderFacts(elements.motionFacts, value);
  renderInventory(elements.motionInventory, value.inventory);
  renderScopes(elements.motionScopes, value);
  elements.motionReleaseReasons.replaceChildren(
    ...value.releaseGate.reasonCodes.map((reason) =>
      textNode(elements.motionReleaseReasons, "li", REASON_LABELS[reason])),
  );
  elements.motionTechnical.textContent = JSON.stringify({
    run_id: value.run.runId,
    run_sha256: value.runSha256,
    motion_instance_v3_sha256: value.address.motionInstanceV3Sha256,
    bundle_sha256: value.address.bundleSha256,
  }, null, 2);
  queueMicrotask(() => elements.motionResultHeading.focus?.());
}

function renderFacts(container, value) {
  const rows = [
    ["项目", value.projectId], ["动作", value.clipId],
    ["输出", "MotionInstance v3"], ["精确读回", "已通过"],
    ["文件", `${value.inventory.length} / 3 已密封`],
    ["存储", value.reused ? "复用相同不可变输出" : "新建内容地址输出"],
  ];
  container.replaceChildren(...rows.map(([term, detail]) => {
    const wrapper = container.ownerDocument.createElement("div");
    wrapper.append(textNode(container, "dt", term), textNode(container, "dd", detail));
    return wrapper;
  }));
}

function renderInventory(container, inventory) {
  container.replaceChildren(...inventory.map((name) => {
    const item = container.ownerDocument.createElement("li");
    const copy = container.ownerDocument.createElement("span");
    const [title, detail] = FILE_LABELS[name];
    copy.append(textNode(container, "strong", title),
      textNode(container, "small", detail));
    item.append(copy);
    return item;
  }));
}

function renderScopes(container, value) {
  const rows = [
    ["MotionInstance v3", value.authority.motion_instance_v3_emitted
      ? "已发出" : "未发出", "pass"],
    ["精确读回", value.verification.exactReadback ? "已通过" : "未通过", "pass"],
    ["Attachment Overlap", "未评估", "blocked"],
    ["动态接缝安全", "点代理不足以证明", "blocked"],
    ["完整接缝边界", "未证明", "blocked"],
    ["可发布时间线", "尚未生成", "blocked"],
    ["Spine adapter", "尚未生成", "blocked"],
    ["官方 Runtime", "尚未验证", "blocked"],
    ["Raster 视觉质量", "尚未验证", "blocked"],
    ["Current head 权限", "尚未授予", "blocked"],
    ["发布权", "仍然阻塞", "blocked"],
  ];
  container.replaceChildren(...rows.map(([title, detail, tone]) => {
    const item = container.ownerDocument.createElement("li");
    item.dataset.tone = tone;
    item.append(textNode(container, "strong", title), textNode(container, "small", detail));
    return item;
  }));
}

function renderAttempt(elements, run) {
  elements.motionAttempt.textContent = run ? `#${run.attempt}` : "—";
  elements.motionAttemptState.textContent = run ? statusLabel(run.status) : "等待创建";
  elements.motionAttemptCode.textContent = run?.failureCode || "无失败码";
}

function textNode(container, tag, text) {
  const node = container.ownerDocument.createElement(tag);
  node.textContent = text;
  return node;
}
function readable(value) { return String(value).replaceAll("_", " "); }
function statusLabel(value) {
  return { queued: "已排队", running: "执行中", completed: "已完成",
    failed_retryable: "失败，可重试", failed_terminal: "终止失败" }[value] || value;
}
function stageLabel(value) {
  return { queued: "等待 worker", exact_inputs: "闭合精确来源",
    motion_consumer_admission: "编译动作准入", motion_instance_v3: "生成 MotionInstance v3",
    publication: "发布三文件 bundle", parent_exact_readback: "精确读回",
    completed: "已完成", failed: "已封存失败" }[value] || readable(value);
}
function badge(node, text, tone) { node.textContent = text; node.dataset.tone = tone; }
function status(elements, message, tone = "") {
  elements.motionStatus.textContent = message;
  if (tone) elements.motionStatus.dataset.tone = tone;
  else delete elements.motionStatus.dataset.tone;
}
