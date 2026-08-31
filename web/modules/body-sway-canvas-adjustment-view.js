"use strict";

const IDS = [
  "canvasAdjustmentPanel", "canvasAdjustmentBadge", "canvasAdjustmentMessage",
  "canvasGainGrid", "canvasAdjustmentAction", "canvasBindingAction",
  "canvasAdjustmentHint",
];

export function canvasAdjustmentElements(document = globalThis.document) {
  return Object.fromEntries(IDS.map((id) => {
    const element = document.getElementById(id);
    if (!element) throw new Error(`缺少画布调整元素：${id}`);
    return [id, element];
  }));
}

export function resetCanvasAdjustmentView(elements) {
  elements.canvasAdjustmentPanel.hidden = true;
  elements.canvasGainGrid.replaceChildren();
  elements.canvasAdjustmentAction.hidden = true;
  elements.canvasBindingAction.hidden = true;
  elements.canvasAdjustmentAction.removeAttribute("href");
  elements.canvasBindingAction.removeAttribute("href");
}

export function renderCanvasAdjustment(elements, entry) {
  resetCanvasAdjustmentView(elements);
  const adjustment = entry.canvasAdjustment;
  if (!adjustment) return;
  const viewportFitted = entry.viewportFit?.document?.fit_status === "fitted";
  const copy = classificationCopy(adjustment.classification);
  elements.canvasAdjustmentPanel.hidden = false;
  elements.canvasAdjustmentBadge.textContent = copy.badge;
  elements.canvasAdjustmentBadge.dataset.tone = copy.tone;
  elements.canvasAdjustmentMessage.textContent = copy.message;
  elements.canvasGainGrid.replaceChildren(...adjustment.probes.map((row) =>
    gainCard(elements.canvasGainGrid.ownerDocument, row, viewportFitted)));
  if (adjustment.proposal) {
    const query = new URLSearchParams({
      package_id: entry.package.package_id,
      canvas_adjustment_sha256: adjustment.candidateSha256,
    });
    elements.canvasAdjustmentAction.href = `./idle-behavior-review.html?${query}`;
    elements.canvasAdjustmentAction.hidden = false;
    elements.canvasAdjustmentHint.textContent =
      "建议只会预填为草稿；不会自动勾选、保存或覆盖现有 revision。仍需查看预览并在确认弹窗中提交。";
    elements.canvasAdjustmentHint.dataset.tone = "warning";
  } else if (adjustment.classification === "upstream_base_motion_canvas_overflow") {
    const recommendation = entry.rebindCandidates.find((row) =>
      row.recommendation.status === "recommended");
    const query = new URLSearchParams({ project: entry.package.project_id });
    if (recommendation) {
      query.set("layer", recommendation.attachmentId);
      query.set("rebind_package", entry.package.package_id);
      query.set("rebind_candidate", recommendation.candidateSha256);
    }
    elements.canvasBindingAction.href = `./index.html?${query}`;
    elements.canvasBindingAction.hidden = false;
    elements.canvasBindingAction.textContent = recommendation
      ? `复核自动换绑：${recommendation.recommendation.from_bone_id} → ${recommendation.recommendation.to_bone_id}`
      : "打开绑定工作台检查基础动作";
    elements.canvasAdjustmentHint.textContent = viewportFitted
      ? "0% 的旧素材框越界已由动态视口覆盖，不再视为 Rig 结构错误；换绑建议仍是独立的视觉/接缝候选，采用后会创建新 revision。"
      : "0% 身体摆动仍越界，说明问题来自基础动作、附件或画布；降低摆动参数无法修复。";
    elements.canvasAdjustmentHint.dataset.tone = viewportFitted ? "success" : "error";
  } else {
    elements.canvasAdjustmentHint.textContent = adjustment.classification
      === "reviewed_canvas_passed"
      ? "当前身体摆动在离散画布采样中通过，无需生成降幅草稿。"
      : "固定档位没有找到可带回的非零参数；可返回 P10.1 选择不使用身体摆动。";
    elements.canvasAdjustmentHint.dataset.tone = "warning";
  }
}

function gainCard(document, row, viewportFitted = false) {
  const canvasFailed = row.canvas_status === "rejected";
  const geometryFailed = row.sampled_geometry_status === "rejected";
  const passed = !canvasFailed && !geometryFailed;
  const percent = Math.round(row.gain.numerator / row.gain.denominator * 100);
  const card = document.createElement("article");
  card.className = "gain-card";
  card.dataset.tone = passed ? "success" : viewportFitted && canvasFailed ? "warning" : "error";
  card.setAttribute("role", "listitem");
  card.setAttribute("aria-label", `${percent}% 幅度：${passed ? "采样通过"
    : viewportFitted && canvasFailed ? "旧素材框越界，动态视口已覆盖" : "采样未通过"}`);
  const heading = document.createElement("h4");
  heading.textContent = `${percent}% 幅度`;
  const status = document.createElement("strong");
  status.textContent = passed ? "采样通过"
    : canvasFailed ? viewportFitted ? "旧素材框越界" : "画布越界"
      : "采样几何未通过";
  const detail = document.createElement("p");
  detail.textContent = passed
    ? `检查 ${row.sample_count} 个姿势，未发现画布越界或采样几何拒绝。`
    : canvasFailed
      ? `旧素材框记录 ${row.canvas_failure_tick_count} 个姿势、${row.canvas_failure_vertex_count} 个顶点越界；最大超出 ${formatPx(row.max_overflow_px)}${viewportFitted ? "；动态视口已覆盖完整动作。" : "。"}`
      : `画布范围通过，但有 ${row.geometry_rejection_tick_count} 个采样 tick（姿势）的几何检查未通过。`;
  card.append(heading, status, detail);
  if (canvasFailed) {
    const responsibility = document.createElement("p");
    responsibility.className = "gain-responsibility";
    responsibility.textContent = `责任附件：${row.affected_attachment_ids.join("、") || "未定位"}；方向：${row.failure_sides.map(sideName).join("、") || "未定位"}。`;
    const worst = document.createElement("p");
    worst.className = "gain-worst";
    worst.textContent = row.worst_failure
      ? `最严重位置：${row.worst_failure.attachment_id}，时间点 ${row.worst_failure.tick}，超出 ${formatPx(row.worst_failure.overflow_px)}。`
      : "没有可显示的最严重位置。";
    card.append(responsibility, worst);
  }
  return card;
}

function classificationCopy(value) {
  return ({
    reviewed_canvas_passed: {
      badge: "原参数通过", tone: "success",
      message: "原参数的画布采样已通过，不需要自动降低身体摆动。",
    },
    sampled_adjustment_candidate_available: {
      badge: "找到可复核草稿", tone: "warning",
      message: "系统逐档实测后找到最高的非零通过档位，可带回 P10.1 由你复核。",
    },
    upstream_base_motion_canvas_overflow: {
      badge: "旧素材框越界", tone: "warning",
      message: "即使把身体摆动降到 0%，动作仍超出原始素材框；动态视口会完整容纳它，固定框数字只保留为诊断。",
    },
    no_nonzero_sampled_adjustment_candidate: {
      badge: "没有非零通过档", tone: "error",
      message: "系统已检查全部固定档位，但没有找到同时通过画布与几何采样的非零档位。",
    },
  })[value];
}

function formatPx(value) {
  return `${Number(value).toFixed(1)} px`;
}

function sideName(value) {
  return ({ left: "左侧", right: "右侧", top: "顶部", bottom: "底部" })[value] || value;
}
