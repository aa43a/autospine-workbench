"use strict";

const IDS = [
  "seamBadge", "seamStatus", "seamProgress", "seamProgressText",
  "attemptNumber", "attemptState", "attemptCode", "seamResult",
  "resultHeading", "resultFacts", "relationshipGrid", "scopeGrid",
  "releaseReasons", "technicalReceipts", "seamFailure", "failureHeading",
  "failureMessage", "retrySeamBtn", "returnToSafetyLink", "continueMotionLink",
  "motionHandoff",
];

const RELATIONSHIP_LABELS = Object.freeze({
  "seam.torso_arm.left": "左肩 · 躯干/手臂",
  "seam.torso_arm.right": "右肩 · 躯干/手臂",
  "seam.pelvis_leg.left": "左髋 · 骨盆/腿",
  "seam.pelvis_leg.right": "右髋 · 骨盆/腿",
  "seam.leg_foot.left": "左踝 · 腿/脚",
  "seam.leg_foot.right": "右踝 · 腿/脚",
  "shoulder-left": "左肩", "elbow-left": "左肘", "wrist-left": "左腕",
  "hip-left": "左髋", "knee-left": "左膝", "ankle-left": "左踝",
  "shoulder-right": "右肩", "elbow-right": "右肘", "wrist-right": "右腕",
  "hip-right": "右髋", "knee-right": "右膝", "ankle-right": "右踝",
});

export function dynamicSeamV2Elements(doc = document) {
  return Object.fromEntries(IDS.map((id) => {
    const node = doc.getElementById(id);
    if (!node) throw new Error(`缺少 P10.5d v2 界面元素：${id}`);
    return [id, node];
  }));
}

export function renderDynamicSeamLoading(elements) {
  badge(elements.seamBadge, "正在自动读取", "warning");
  status(elements, "正在闭合 P10.4b v2 与当前 P10.5c；无需选择项目、文件或 SHA。", "warning");
  elements.seamProgress.max = 1;
  elements.seamProgress.value = 0;
  elements.seamProgressText.textContent = "校验精确来源…";
  renderAttempt(elements, null);
  elements.seamResult.hidden = true;
  elements.seamFailure.hidden = true;
  elements.retrySeamBtn.hidden = true;
  elements.motionHandoff.hidden = true;
}

export function renderDynamicSeamRun(elements, state) {
  if (state.status === "ready") {
    badge(elements.seamBadge, "来源已就绪", "success");
    status(elements, "精确来源唯一且可用，正在自动创建第一次分析。", "success");
    elements.seamProgress.max = 1;
    elements.seamProgress.value = 0;
    elements.seamProgressText.textContent = "即将开始…";
    return;
  }
  const { run } = state;
  renderAttempt(elements, run);
  elements.seamProgress.max = run.progress.total;
  elements.seamProgress.value = run.progress.current;
  elements.seamProgressText.textContent = `${run.progress.current} / ${run.progress.total}`
    + ` · ${stageLabel(run.stage)}`;
  const active = state.status === "queued" || state.status === "running";
  badge(elements.seamBadge, active ? `第 ${run.attempt} 次分析中`
    : state.status === "completed" ? "分析已完成" : "本次分析已封存",
  active ? "warning" : state.status === "completed" ? "success" : "error");
  status(elements, active
    ? "正在逐段计算接缝锚点残差上界；页面刷新不会创建重复尝试。"
    : state.status === "completed" ? "分析完成，正在精确读回三文件 bundle。"
      : `第 ${run.attempt} 次尝试未完成，旧回执保持不变。`,
  active ? "warning" : state.status === "completed" ? "success" : "error");
}

export function renderDynamicSeamFailure(elements, run, message) {
  const retryable = Boolean(run?.retryable);
  badge(elements.seamBadge, retryable ? "可确认后重试" : "终止且不可重试", "error");
  status(elements, `P10.5d v2 未形成可用结论：${message}`, "error");
  renderAttempt(elements, run);
  elements.seamResult.hidden = true;
  elements.seamFailure.hidden = false;
  elements.failureHeading.textContent = run
    ? `第 ${run.attempt} 次尝试已作为不可变回执保留`
    : "没有生成动态接缝结论";
  elements.failureMessage.textContent = retryable
    ? "不会使用部分结果。点击重试后仍需确认，系统会创建新的 attempt，不覆盖本次记录。"
    : "该失败需要修复来源或算法后再进入；系统没有猜测结果，也没有解除发布门禁。";
  elements.retrySeamBtn.hidden = !retryable;
  elements.motionHandoff.hidden = true;
}

export function renderDynamicSeamResult(elements, value) {
  const certified = value.probe.status
    === "continuous_preview_v2_reviewed_anchor_residual_certified";
  badge(elements.seamBadge,
    certified ? "锚点残差代理已证明" : "分析完成 · 存在未定项",
  certified ? "success" : "warning");
  status(elements, certified
    ? "所有已复核接缝关系均有有限工程上界；视觉与发布门禁仍未关闭。"
    : "分析正常完成，但至少一个区间或关系尚不能证明。", certified ? "success" : "warning");
  renderAttempt(elements, value.run);
  elements.seamProgress.max = value.run.progress.total;
  elements.seamProgress.value = value.run.progress.total;
  elements.seamProgressText.textContent = "结果已精确读回并密封";
  elements.seamFailure.hidden = true;
  elements.seamResult.hidden = false;
  elements.motionHandoff.hidden = !certified;
  elements.resultHeading.textContent = certified
    ? "逐关系工程代理证据已生成" : "逐关系结果含未定证据";
  renderFacts(elements.resultFacts, value);
  renderRelationships(elements.relationshipGrid, value.probe.relationships,
    value.probe.summary.thresholdSquaredPx2);
  renderScopes(elements.scopeGrid, value);
  elements.releaseReasons.replaceChildren(...value.releaseGate.reasonCodes.map((reason) =>
    textNode(elements.releaseReasons, "li", readable(reason))));
  elements.technicalReceipts.textContent = JSON.stringify({
    run_id: value.run.runId, attempt: value.run.attempt,
    head_event_sha256: value.run.headEventSha256,
    probe_sha256: value.bundle.probeSha256,
    bundle_sha256: value.bundle.bundleSha256,
    source_set_sha256: value.bundle.sourceSetSha256,
    source_document_sha256: value.bundle.sourceDocumentSha256,
  }, null, 2);
  queueMicrotask(() => elements.resultHeading.focus?.());
}

function renderAttempt(elements, run) {
  elements.attemptNumber.textContent = run ? `#${run.attempt}` : "—";
  elements.attemptState.textContent = run ? statusLabel(run.status) : "等待创建";
  elements.attemptCode.textContent = run?.failureCode || "无失败码";
}

function renderFacts(container, value) {
  const summary = value.probe.summary;
  const rows = [
    ["项目", value.projectId], ["动作", value.clipId],
    ["接缝关系", `${summary.relationshipCount} 条`],
    ["连续区间", `${summary.certifiedSegmentCount} 已证明 · ${summary.indeterminateSegmentCount} 未定`],
    ["锚点对", `${summary.anchorPairCount} 对`],
    ["区间盒", `${summary.evaluatedBoxCount} 个`],
  ];
  container.replaceChildren(...rows.map(([term, detail]) => {
    const wrapper = container.ownerDocument.createElement("div");
    wrapper.append(textNode(container, "dt", term), textNode(container, "dd", detail));
    return wrapper;
  }));
}

function renderRelationships(container, rows, thresholdSquared) {
  const threshold = Math.sqrt(thresholdSquared);
  container.replaceChildren(...rows.map((row) => {
    const within = row.maximumSquaredPx2 !== null
      && row.maximumSquaredPx2 <= thresholdSquared;
    const conclusion = row.status !== "finite_upper_bound" ? "尚不能证明"
      : within ? "有限上界在阈值内" : "有限上界超过阈值";
    const article = container.ownerDocument.createElement("article");
    article.className = "relationship-card";
    article.dataset.tone = within ? "pass" : "warning";
    article.setAttribute("aria-label", `${relationshipLabel(row.relationshipId)}：${conclusion}`);
    const header = container.ownerDocument.createElement("header");
    header.append(
      textNode(container, "h3", relationshipLabel(row.relationshipId)),
      textNode(container, "span", conclusion),
    );
    const residual = row.maximumSquaredPx2 === null
      ? "尚无完整有限上界" : `≤ ${Math.sqrt(row.maximumSquaredPx2).toFixed(2)} px`;
    const list = container.ownerDocument.createElement("dl");
    for (const [term, detail] of [
      ["锚点残差", residual],
      ["工程阈值", `≤ ${threshold.toFixed(2)} px`],
      ["Gap proxy", `${residual}（非像素裂缝）`],
      ["Overlap", "未评估"],
      ["覆盖", `${row.segmentCount} 个相邻区间`],
    ]) {
      const wrapper = container.ownerDocument.createElement("div");
      wrapper.append(textNode(container, "dt", term), textNode(container, "dd", detail));
      list.append(wrapper);
    }
    article.append(header, list);
    if (row.reasonCodes.length) {
      article.append(textNode(container, "p", `原因：${row.reasonCodes.map(readable).join("、")}`));
    }
    return article;
  }));
}

function renderScopes(container, value) {
  const certified = value.claims
    .continuous_preview_v2_anchor_residual_within_engineering_tolerance;
  const rows = [
    ["锚点残差", certified ? "工程上界已证明" : "存在未定项", certified ? "pass" : "warning"],
    ["Gap proxy", certified ? "工程代理已证明" : "存在未定项", certified ? "pass" : "warning"],
    ["Overlap", "未评估", "blocked"], ["Raster 裂缝", "未证明", "blocked"],
    ["官方 Runtime", "未证明等价", "blocked"], ["视觉与发布", "仍然阻塞", "blocked"],
  ];
  container.replaceChildren(...rows.map(([title, detail, tone]) => {
    const item = container.ownerDocument.createElement("li");
    item.dataset.tone = tone;
    item.append(textNode(container, "strong", title), textNode(container, "small", detail));
    return item;
  }));
}

function textNode(container, tag, text) {
  const node = container.ownerDocument.createElement(tag);
  node.textContent = text;
  return node;
}
function relationshipLabel(id) {
  return RELATIONSHIP_LABELS[id] || id.replaceAll("-", " · ");
}
function readable(value) { return String(value).replaceAll("_", " "); }
function statusLabel(value) {
  return { queued: "已排队", running: "执行中", completed: "已完成",
    failed_retryable: "失败，可重试", failed_terminal: "终止失败" }[value] || value;
}
function stageLabel(value) {
  return { queued: "等待独立 worker", compile_segments: "准备逐段分析",
    exact_inputs: "闭合精确来源", dynamic_seam_segments: "逐段接缝证明",
    dynamic_seam_validation_segments: "逐段语义复验", publication: "发布三文件 bundle",
    parent_exact_readback: "父进程精确读回",
    completed: "已完成", failed: "已封存失败" }[value] || readable(value);
}
function badge(node, text, tone) { node.textContent = text; node.dataset.tone = tone; }
function status(elements, message, tone = "") {
  elements.seamStatus.textContent = message;
  if (tone) elements.seamStatus.dataset.tone = tone;
  else delete elements.seamStatus.dataset.tone;
}
