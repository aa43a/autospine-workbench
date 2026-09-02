"use strict";

const IDS = [
  "spineBadge", "spineStatus", "spineProgress", "spineProgressText",
  "spineAttempt", "spineAttemptState", "spineAttemptCode",
  "spineResult", "spineResultHeading", "spineFacts", "spineInventory",
  "spineScopes", "spineReleaseReasons", "spineFailure",
  "spineFailureHeading", "spineFailureMessage", "retrySpineBtn",
  "returnToMotionLink", "returnToMotionTop",
];
const FILE_LABELS = Object.freeze({
  "skeleton.json": ["Spine 骨架", "Spine 4.2 v3 JSON adapter 输出"],
  "skeleton.atlas": ["图集索引", "附件区域与纹理页映射"],
  "skeleton.png": ["纹理页", "由已绑定附件构建的透明纹理"],
  "run-manifest.json": ["运行回执", "v2 来源合同与能力边界"],
  "export-report.json": ["结构报告", "自动结构校验与阻塞门禁"],
});
const REASON_LABELS = Object.freeze({
  attachment_area_overlap_not_assessed: "附件重叠面积尚未评估",
  dynamic_seam_safety_unproven: "动态接缝安全尚未证明",
  full_attachment_boundary_continuity_unproven: "完整附件边界连续性尚未证明",
  official_runtime_not_loaded: "尚未由官方 Spine Runtime 加载",
  persistent_current_head_authority_not_granted: "尚未授予持久 current-head 权限",
  publishable_spine_timeline_not_granted: "尚未授予可发布 Spine 时间线",
  raster_visual_quality_unproven: "Raster 视觉质量尚未证明",
  release_authority_not_granted: "尚未授予发布权",
  runtime_equivalence_unproven: "Runtime 等价性尚未证明",
});

export function spine42V3V2Elements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const node = doc.getElementById(id);
    if (!node) throw new Error(`缺少 P10.7a v2 界面元素：${id}`);
    return [id, node];
  }));
}

export function renderSpine42V3V2Loading(elements) {
  badge(elements.spineBadge, "正在自动读取", "warning");
  status(elements, "正在闭合已完成的 MotionInstance；无需选择项目或文件。", "warning");
  elements.spineProgress.max = 1;
  elements.spineProgress.value = 0;
  elements.spineProgressText.textContent = "校验精确来源…";
  renderAttempt(elements, null);
  elements.spineResult.hidden = true;
  elements.spineFailure.hidden = true;
  elements.retrySpineBtn.hidden = true;
}

export function renderSpine42V3V2Run(elements, state) {
  if (state.status === "ready") {
    badge(elements.spineBadge, "来源已就绪", "success");
    status(elements, "唯一来源可用，正在自动创建第一次 adapter 任务。", "success");
    return;
  }
  const { run } = state;
  renderAttempt(elements, run);
  elements.spineProgress.max = run.progress.total;
  elements.spineProgress.value = run.progress.current;
  elements.spineProgressText.textContent = `${run.progress.current} / ${run.progress.total}`
    + ` · ${stageLabel(run.stage)}`;
  const active = ["queued", "running"].includes(state.status);
  badge(elements.spineBadge, active ? `第 ${run.attempt} 次生成中`
    : state.status === "completed" ? "adapter 已完成" : "本次尝试已封存",
  active ? "warning" : state.status === "completed" ? "success" : "error");
  status(elements, active
    ? "正在生成五文件 adapter bundle；刷新页面不会创建重复尝试。"
    : state.status === "completed" ? "生成完成，正在执行精确读回。"
      : `第 ${run.attempt} 次尝试未完成，旧回执保持不变。`,
  active ? "warning" : state.status === "completed" ? "success" : "error");
}

export function renderSpine42V3V2Failure(elements, run, message) {
  const retryable = Boolean(run?.retryable);
  badge(elements.spineBadge, retryable ? "可确认后重试" : "终止且不可重试", "error");
  status(elements, `P10.7a v2 未形成可用输出：${message}`, "error");
  renderAttempt(elements, run);
  elements.spineResult.hidden = true;
  elements.spineFailure.hidden = false;
  elements.spineFailureHeading.textContent = run
    ? `第 ${run.attempt} 次尝试已作为不可变回执保留`
    : "没有生成 Spine adapter";
  elements.spineFailureMessage.textContent = retryable
    ? "不会使用部分结果。确认重试会创建新 attempt，不会覆盖失败记录。"
    : "请先修复来源或本地服务；系统不会猜测输出或解除门禁。";
  elements.retrySpineBtn.hidden = !retryable;
}

export function renderSpine42V3V2Result(elements, value) {
  badge(elements.spineBadge, "Spine adapter 已发出", "success");
  status(elements, "五文件 bundle 已密封并完成精确读回；发布门禁仍保持阻塞。", "success");
  renderAttempt(elements, value.run);
  elements.spineProgress.max = value.run.progress.total;
  elements.spineProgress.value = value.run.progress.total;
  elements.spineProgressText.textContent = "精确读回通过";
  elements.spineFailure.hidden = true;
  elements.spineResult.hidden = false;
  renderFacts(elements.spineFacts, value);
  elements.spineInventory.replaceChildren(...value.inventory.map((name) => {
    const item = elements.spineInventory.ownerDocument.createElement("li");
    const copy = elements.spineInventory.ownerDocument.createElement("span");
    const [title, detail] = FILE_LABELS[name];
    copy.append(textNode(copy, "strong", title), textNode(copy, "small", detail));
    item.append(copy);
    return item;
  }));
  renderScopes(elements.spineScopes, value);
  elements.spineReleaseReasons.replaceChildren(
    ...value.releaseGate.reasonCodes.map((reason) =>
      textNode(elements.spineReleaseReasons, "li", REASON_LABELS[reason])),
  );
  queueMicrotask(() => elements.spineResultHeading.focus?.());
}

function renderFacts(container, value) {
  const rows = [
    ["项目", value.projectId], ["动作", value.clipId],
    ["输出", "Spine 4.2 v3 adapter"], ["精确读回", "已通过"],
    ["文件", `${value.inventory.length} / 5 已密封`],
    ["存储", value.reused ? "复用相同不可变输出" : "新建内容地址输出"],
  ];
  container.replaceChildren(...rows.map(([term, detail]) => {
    const wrapper = container.ownerDocument.createElement("div");
    wrapper.append(textNode(container, "dt", term), textNode(container, "dd", detail));
    return wrapper;
  }));
}

function renderScopes(container, value) {
  const rows = [
    ["Spine adapter", value.authority.spine_adapter_emitted ? "已发出" : "未发出", "pass"],
    ["精确读回", value.verification.exactReadback ? "已通过" : "未通过", "pass"],
    ["官方 Runtime", "未加载", "blocked"],
    ["Runtime 等价性", "未证明", "blocked"],
    ["Raster 视觉质量", "未证明", "blocked"],
    ["P10.7b v2 bridge", "尚未进入", "blocked"],
    ["外部授权采集", "不会自动运行", "blocked"],
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
  elements.spineAttempt.textContent = run ? `#${run.attempt}` : "—";
  elements.spineAttemptState.textContent = run ? statusLabel(run.status) : "等待创建";
  elements.spineAttemptCode.textContent = run?.failureCode || "无失败码";
}
function textNode(container, tag, text) {
  const node = container.ownerDocument.createElement(tag);
  node.textContent = text;
  return node;
}
function statusLabel(value) {
  return { queued: "已排队", running: "执行中", completed: "已完成",
    failed_retryable: "失败，可重试", failed_terminal: "终止失败" }[value] || value;
}
function stageLabel(value) {
  return { queued: "等待 worker", exact_motion_instance: "闭合 MotionInstance",
    source_adapter: "校验 v2 来源合同", spine_adapter: "生成 Spine adapter",
    publication: "发布五文件 bundle", parent_exact_readback: "精确读回",
    completed: "已完成", failed: "已封存失败" }[value] || value;
}
function badge(node, text, tone) { node.textContent = text; node.dataset.tone = tone; }
function status(elements, message, tone) {
  elements.spineStatus.textContent = message;
  elements.spineStatus.dataset.tone = tone;
}
