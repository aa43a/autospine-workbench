"use strict";

import { AUTOMATION_STATUS } from "./workbench-automation-view.js";
import { animatedReason } from "./workbench-animated-contract.js";
import { createAnimatedBindings } from "./workbench-animated-bindings.js";
import { createAnimatedPlayer } from "./workbench-animated-player.js";
import { createAnimatedRebase } from "./workbench-animated-rebase.js";
import { workbenchLayout } from "./workbench-layout.js";
import { createCharacterCoverage } from "./workbench-character-coverage.js";

const STEPS = {
  "resolve-project": "解析当前项目", "resolve-source": "解析已验证源", "build-skeleton": "生成骨架候选",
  "build-bindings": "解析图层绑定", "build-mesh": "构建加权网格", "apply-motion": "应用动作",
  "compile-spine": "编译 Spine 动画", "compile-animated-preview": "编译动画候选", "validate-preview": "检查预览质量",
  "build-weighted-mesh": "构建加权网格", "review-animation": "复核动画候选",
};
const TYPES = { joint: "关节", binding: "骨骼绑定", mesh: "网格", seam: "接缝", residual: "残余归属", runtime: "Runtime", layer: "图层" };
function node(document, tag, text = "") {
  const element = document.createElement(tag); element.textContent = text; return element;
}
export function createAnimatedView(document, callbacks) {
  const section = node(document, "section"), heading = node(document, "h3", "可变形动画候选预览");
  section.className = "automation-panel inspector-section";
  heading.id = "animatedPreviewHeading"; heading.tabIndex = -1; section.setAttribute("aria-labelledby", heading.id);
  const description = node(document, "p", "构建 Spine 4.3.26 动画候选并播放；待处理问题集中在底部异常队列。");
  const label = node(document, "label", "预览动作"), select = node(document, "select");
  label.setAttribute("for", "animatedPreviewClip"); select.id = "animatedPreviewClip";
  const actions = node(document, "div"); actions.className = "automation-actions";
  const build = node(document, "button", "构建动画候选"), refresh = node(document, "button", "刷新"), cancel = node(document, "button", "取消构建");
  for (const button of [build, refresh, cancel]) { button.type = "button"; button.className = "button button-secondary"; }
  build.className = "button button-primary"; actions.append(build, refresh, cancel);
  const status = node(document, "p"), summary = node(document, "p"), steps = node(document, "ol"), queueTitle = node(document, "h4", "动画待复核项"), queue = node(document, "ul");
  const reviewNotice = node(document, "p"); reviewNotice.setAttribute("role", "status");
  status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); queue.className = "automation-queue";
  const download = node(document, "a", "下载动画候选 / QA"); download.setAttribute("download", ""); download.className = "button button-secondary";
  const note = node(document, "p", "可下载候选不代表已采用或已获发布授权。修改复核后会重新构建相关下游。");
  const bindings = createAnimatedBindings(document, { save: callbacks.saveReview, complete: callbacks.completeBindings, changed: callbacks.bindingChanged, locate: callbacks.locate });
  const player = createAnimatedPlayer(document);
  const coverage = createCharacterCoverage(document, callbacks.locate);
  const rebase = createAnimatedRebase(document, callbacks.rebase);
  section.append(heading, description, label, select, actions, status, rebase.element, reviewNotice, summary, steps, download, player.element, queueTitle, queue, bindings.element, note);
  section.insertBefore(coverage.element, player.element);
  const layout = workbenchLayout(document), mount = document.getElementById("automationMount");
  if (layout) {
    layout.mount("animation", section); layout.mount("bindings", bindings.element);
    layout.mount("preparation", rebase.element); layout.mountIssues("animated", queueTitle, queue);
    bindings.element.open = true;
  } else mount?.append(section);
  const navigation = node(document, "nav"), staticLink = node(document, "button", "静态预览"), animatedLink = node(document, "button", "动画候选");
  navigation.className = "automation-actions"; navigation.setAttribute("aria-label", "选择预览类型");
  for (const button of [staticLink, animatedLink]) { button.type = "button"; button.className = "button button-secondary"; }
  animatedLink.addEventListener("click", () => { section.scrollIntoView({ block: "start", behavior: "smooth" }); heading.focus({ preventScroll: true }); });
  staticLink.addEventListener("click", () => document.getElementById("automationHeading")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  navigation.append(staticLink, animatedLink); if (!layout) mount?.prepend(navigation);
  build.addEventListener("click", callbacks.start); refresh.addEventListener("click", callbacks.refresh); cancel.addEventListener("click", callbacks.cancel);
  select.addEventListener("change", () => callbacks.setClip(select.value));
  download.addEventListener("click", (event) => { if (!callbacks.canDownload()) event.preventDefault(); });
  let clipSignature = null;
  function render(model) {
    const signature = JSON.stringify(model.clips);
    if (signature !== clipSignature) {
      clipSignature = signature;
      select.replaceChildren(...model.clips.map((clip) => {
        const option = node(document, "option", clip.label); option.value = clip.id; return option;
      }));
    }
    select.value = model.clip || ""; select.disabled = model.active || model.savingReview || !model.clips.length;
    build.disabled = !model.canStart; refresh.disabled = !model.hasProject || model.fetching || model.savingReview || model.rebasing;
    cancel.hidden = !model.canCancel; cancel.disabled = model.canceling;
    status.textContent = model.message; section.setAttribute("aria-busy", String(model.active || model.fetching || model.savingReview));
    reviewNotice.textContent = model.reviewNotice || "";
    summary.textContent = model.summary ? `加权网格图层 ${model.summary.mesh_layers ?? 0} · 身体参照图层 ${model.summary.context_layers ?? 0}` : "";
    steps.replaceChildren(...model.steps.map((step) => node(document, "li", `${STEPS[step.id] || "处理阶段"} · ${AUTOMATION_STATUS[step.status] || "等待开始"}`)));
    queueTitle.textContent = `动画待复核项 · ${model.items.length}`;
    queue.replaceChildren(...model.items.map((item) => {
      const row = node(document, "li"); row.className = "automation-review-item";
      row.append(node(document, "strong", `${TYPES[item.type] || "复核项"}${item.layer_id ? ` · ${item.layer_id}` : ""}`), node(document, "p", animatedReason(item.reason_code)));
      if (item.layer_id || item.entity_id) {
        const locate = node(document, "button", "定位复核"); locate.type = "button";
        locate.addEventListener("click", () => callbacks.locate(item)); row.append(locate);
      }
      return row;
    }));
    download.hidden = !model.downloadUrl;
    if (model.downloadUrl) download.setAttribute("href", model.downloadUrl); else download.removeAttribute("href");
    rebase.render(model); bindings.render(model); void player.load(model.playbackUrl);
    void coverage.load(model.downloadUrl);
  }
  return { render, resetReview: bindings.reset, focusBinding: (id) => { layout?.showBinding("bindings"); return bindings.focusLayer(id); },
    mountJoint: (element) => layout ? layout.mount("joints", element) : section.append(element),
    mountPlan: (element) => { if (layout) { layout.mount("plan", element); element.open = true; } else section.append(element); },
    mountSleeves: (element) => layout ? layout.mount("sleeves", element) : section.prepend(element),
    mountCharacter: (element) => section.prepend(element),
    mountPolicy: (element) => bindings.element.insertBefore(element, bindings.element.children[1]),
    mountPreparation: (element) => layout ? layout.mount("preparation", element) : section.insertBefore(element, reviewNotice), dispose: () => { coverage.dispose(); player.dispose(); } };
}
