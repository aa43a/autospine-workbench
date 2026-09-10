"use strict";

const layouts = new WeakMap();
const STEPS = { asset: "素材检查", binding: "绑定规划与复核", sleeves: "袖装修复", animation: "动画预览", export: "导出", reports: "报告与证据" };
// Reparent existing controls: switching workspaces never rebuilds or saves a draft.
export function workbenchLayout(document) {
  if (!document?.getElementById("workspace")) return null;
  if (layouts.has(document)) return layouts.get(document);
  const node = (tag, text = "", cls = "") => {
    const el = document.createElement(tag); el.textContent = text; el.className = cls; return el;
  };
  const canvas = document.getElementById("main-content");
  const center = node("section", "", "workbench-center"), nav = node("nav", "", "workbench-step-nav");
  nav.setAttribute("aria-label", "工作区步骤");
  const pages = {}, buttons = {}, slots = {};
  canvas.before(center); center.append(nav);
  const library = node("a", "资产中心", "button button-secondary"); library.href = "/assets.html"; nav.append(library);
  for (const [id, label] of Object.entries(STEPS)) {
    const button = node("button", label, "button button-secondary"); button.type = "button";
    const page = node("section", "", "workbench-page"); page.id = `workbench-${id}`;
    page.setAttribute("aria-label", label); button.setAttribute("aria-controls", page.id);
    button.addEventListener("click", () => show(id));
    buttons[id] = button; pages[id] = page; nav.append(button); center.append(page);
  }
  pages.asset.append(canvas);
  const subnav = node("nav", "", "workbench-step-nav"); subnav.setAttribute("aria-label", "绑定工作区");
  pages.binding.append(subnav);
  const subbuttons = {};
  for (const [id, title] of Object.entries({ plan: "全角色规划", bindings: "图层绑定", joints: "关节复核", preparation: "来源准备" })) {
    const button = node("button", title, "button button-secondary"); button.type = "button";
    button.addEventListener("click", () => showBinding(id)); subbuttons[id] = button; subnav.append(button);
    slots[id] = node("div"); pages.binding.append(slots[id]);
  }
  const issues = node("details", "", "workbench-issues"), issuesTitle = node("summary", "异常队列"), issueNav = node("nav", "", "workbench-step-nav");
  issueNav.setAttribute("aria-label", "异常来源"); issues.append(issuesTitle, issueNav); center.append(issues);
  const issueSlots = {}, issueButtons = {};
  for (const [id, title] of Object.entries({ animated: "动画异常", static: "静态异常", qa: "素材 QA" })) {
    const button = node("button", title, "button button-secondary"); button.type = "button";
    button.addEventListener("click", () => showIssues(id)); issueNav.append(button); issueButtons[id] = button;
    issueSlots[id] = node("div"); issues.append(issueSlots[id]);
  }
  function show(id) {
    if (!pages[id]) return;
    for (const key of Object.keys(pages)) { pages[key].hidden = key !== id; buttons[key].setAttribute("aria-pressed", String(key === id)); }
    // Canvas geometry is recalculated by the existing resize handler.
    document.defaultView?.dispatchEvent(new Event("resize"));
  }
  function showBinding(id) {
    show("binding");
    for (const key of Object.keys(subbuttons)) { slots[key].hidden = key !== id; subbuttons[key].setAttribute("aria-pressed", String(key === id)); }
  }
  function showIssues(id) {
    for (const key of Object.keys(issueSlots)) { issueSlots[key].hidden = key !== id; issueButtons[key].setAttribute("aria-pressed", String(key === id)); }
  }
  function mount(id, ...elements) { (slots[id] || pages[id])?.append(...elements); }
  function mountIssues(id, ...elements) { issueSlots[id]?.append(...elements); }
  const moveSection = (id, target) => { const section = document.getElementById(id)?.closest("section"); if (section) target.append(section); };
  moveSection("qaHeading", issueSlots.qa); moveSection("capabilitiesHeading", pages.reports);
  for (const id of ["candidateReviewMount", "splitReviewMount"]) {
    const el = document.getElementById(id); if (el) pages.reports.append(el);
  }
  const evidence = node("div"); evidence.id = "meshEvidenceMount"; pages.reports.append(evidence);
  // The legacy stage indicators remain status-only data; this navigation owns workspace selection.
  const legacy = document.getElementById("workflowNav"); if (legacy) legacy.hidden = true;
  showBinding("plan"); show("asset"); showIssues("animated");
  const api = { show, showBinding, mount, mountIssues }; layouts.set(document, api); return api;
}
