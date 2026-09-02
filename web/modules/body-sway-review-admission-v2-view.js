"use strict";

const REASON_LABELS = Object.freeze({
  continuous_time_safety_unproven: "连续时间安全尚未证明",
  preview_only_timeline: "当前仍是预览动作时间线",
  reviewed_seam_anchors_missing: "当前链尚缺已复核接缝锚点",
  safe_range_unproven: "可复用安全幅度范围尚未证明",
});

export function admissionV2Elements(document) {
  return Object.freeze({
    badge: document.querySelector("#admissionBadge"),
    status: document.querySelector("#admissionStatus"),
    result: document.querySelector("#admissionResult"),
    failure: document.querySelector("#admissionFailure"),
    facts: document.querySelector("#admissionFacts"),
    claims: document.querySelector("#admissionClaims"),
    blockers: document.querySelector("#releaseBlockers"),
    digest: document.querySelector("#admissionDigest"),
    technical: document.querySelector("#technicalDocument"),
    retry: document.querySelector("#retryAdmissionBtn"),
    reviewLink: document.querySelector("#returnToReviewLink"),
  });
}

export function renderLoading(elements) {
  elements.badge.textContent = "正在校验";
  elements.badge.dataset.tone = "warning";
  setStatus(elements.status, "正在重放 completed execution 与当前人工复核头…");
  elements.result.hidden = true;
  elements.failure.hidden = true;
}

export function renderMissingJob(elements) {
  elements.badge.textContent = "缺少任务";
  elements.badge.dataset.tone = "error";
  setStatus(elements.status,
    "此入口需要由已完成的 P10.3c 视觉复核携带 job_id 进入；系统不会猜测 latest。",
    "error");
  elements.failure.hidden = false;
  elements.retry.hidden = true;
  elements.reviewLink.hidden = true;
}

export function renderFailure(elements, message, jobId = null) {
  elements.badge.textContent = "未准入";
  elements.badge.dataset.tone = "error";
  setStatus(elements.status, `P10.4a v2 未准入：${message}`, "error");
  elements.result.hidden = true;
  elements.failure.hidden = false;
  elements.retry.hidden = false;
  if (jobId) {
    elements.reviewLink.href = `./body-sway-review-v2.html?job_id=${encodeURIComponent(jobId)}`;
    elements.reviewLink.hidden = false;
  }
}

export function renderAdmission(elements, value) {
  elements.badge.textContent = "准入检查通过";
  elements.badge.dataset.tone = "success";
  setStatus(elements.status,
    "官方 Runtime 采样视觉决定已按 current head 精确重放。", "success");
  elements.failure.hidden = true;
  elements.result.hidden = false;
  renderFacts(elements.facts, value);
  renderClaims(elements.claims, value.claims);
  renderBlockers(elements.blockers, value.releaseReasons);
  elements.digest.textContent = value.admissionSha256;
  elements.technical.textContent = JSON.stringify(value.document, null, 2);
}

function renderFacts(container, value) {
  const rows = [
    ["项目", value.projectId || "由 exact job 绑定"],
    ["动作", value.clipId || "由 exact job 绑定"],
    ["采集任务", compact(value.jobId)],
    ["人工 revision", value.revision === null ? "current approved head" : String(value.revision)],
  ];
  container.replaceChildren(...rows.map(([term, description]) => fact(container, term, description)));
}

function renderClaims(container, claims) {
  const rows = [
    ["官方采样执行已绑定", claims.completed_sampled_execution_bound !== false],
    ["采样画面人工通过", claims.sampled_visual_approved === true],
    ["编译时 current head 已确认", claims.head_observed_at_compile_time === true],
    ["可以发布 Spine 动画", claims.release_authority === true],
  ];
  container.replaceChildren(...rows.map(([label, passed]) => {
    const item = container.ownerDocument.createElement("li");
    item.dataset.state = passed ? "pass" : "blocked";
    const strong = container.ownerDocument.createElement("strong");
    strong.textContent = passed ? "已确认" : "仍阻塞";
    const span = container.ownerDocument.createElement("span");
    span.textContent = label;
    item.append(strong, span);
    return item;
  }));
}

function renderBlockers(container, reasons) {
  container.replaceChildren(...reasons.map((reason) => {
    const item = container.ownerDocument.createElement("li");
    item.textContent = REASON_LABELS[reason] || reason;
    return item;
  }));
}

function fact(container, term, description) {
  const document = container.ownerDocument;
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = description;
  wrapper.append(dt, dd);
  return wrapper;
}

function compact(value) {
  return value.length > 20 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}

function setStatus(node, message, tone = "") {
  node.textContent = message;
  if (tone) node.dataset.tone = tone;
  else delete node.dataset.tone;
}
