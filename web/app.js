import { API_BASE, apiRequest, normalizeProjectSummaries } from "./modules/api.js";
import {
  applyDraftPatch,
  captureSaveSnapshot,
  cloneJson,
  createLocalPatchArtifact,
  reconcileSaveResponse,
} from "./modules/draft-transactions.js";
import { createSkeletonRenderer } from "./modules/skeleton-renderer.js";
import { applyOverrideDraft, captureOverrideDraft, overrideDraftFromServer } from "./modules/override-draft.js";
import { compositeQaFlag, confidenceLevel, formatConfidence, normalizeWorkflow, setConfidenceBadge, unresolvedJointIds } from "./modules/workflow.js";

const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  projects: [],
  project: null,
  selectedProjectId: null,
  selectedLayerId: null,
  selectedJointId: null,
  activeStage: null,
  editMode: "layers",
  zoom: 1,
  fitZoom: 1,
  previewOpacity: 1,
  showComposite: true,
  showSkeleton: true,
  search: "",
  dirty: false,
  saving: false,
  loading: false,
  baseRevision: null,
  jointOverrides: {},
  jointDecisions: {},
  layerOverrides: {},
  notes: "",
  dragJointId: null,
  dragPointerStart: null,
  loadSequence: 0,
  editEpoch: 0,
  persistedDraft: null,
  conflictPatch: null,
};

const dom = Object.fromEntries([
  "projectSelect", "refreshProjectsBtn", "workflowNav", "saveBtn", "saveIndicator",
  "saveIndicatorText", "globalAlert", "globalAlertText", "dismissAlertBtn", "layerCounter",
  "layerSearch", "clearSearchBtn", "showAllLayersBtn", "hideAllLayersBtn", "visibleLayerCount",
  "layerList", "layerModeBtn", "jointModeBtn", "toggleCompositeBtn", "toggleSkeletonBtn",
  "previewOpacity", "previewOpacityValue", "zoomOutBtn", "zoomInBtn", "zoomValueBtn",
  "fitCanvasBtn", "canvasViewport", "canvasSpace", "canvasSurface", "compositeImage",
  "layerStack", "skeletonSvg", "boneGroup", "layerSelectionGroup", "jointGroup", "canvasEmpty",
  "canvasEmptyTitle", "canvasEmptyText", "canvasLoading", "revisionBadge", "layerInspector",
  "layerConfidence", "layerSelectionEmpty", "layerFields", "layerSwatch", "selectedLayerName",
  "selectedLayerId", "selectedLayerBbox", "selectedLayerState", "semanticRoleInput",
  "semanticSideSelect", "layerDispositionSelect", "selectedLayerVisible", "jointConfidence", "jointSelectionEmpty",
  "jointFields", "selectedJointName", "selectedJointState", "jointXInput", "jointYInput",
  "resetJointBtn", "qaCounter", "qaList", "capabilityList", "overrideNotes", "canvasStatus",
  "selectionStatus", "overrideStatus", "networkStatus", "liveRegion", "conflictActions",
  "exportLocalPatchBtn", "replayConflictBtn",
].map((id) => [id, document.getElementById(id)]));

function normalizeOverrideMap(value) {
  if (!value) return {};
  if (Array.isArray(value)) {
    return Object.fromEntries(value.filter(Boolean).map((entry) => [String(entry.id), cloneJson(entry, {})]));
  }
  return typeof value === "object" ? cloneJson(value, {}) : {};
}

function normalizeLayerOverrideMap(value) {
  const overrides = normalizeOverrideMap(value);
  for (const [layerId, rawOverride] of Object.entries(overrides)) {
    if (!rawOverride || typeof rawOverride !== "object" || Array.isArray(rawOverride)) {
      overrides[layerId] = {};
      continue;
    }
    const semantic = rawOverride.semantic && typeof rawOverride.semantic === "object"
      ? rawOverride.semantic
      : {};
    if (!("canonical_role" in rawOverride)) {
      const role = semantic.canonical_role ?? semantic.role ?? rawOverride.role;
      if (role != null) rawOverride.canonical_role = role;
    }
    if (!("side" in rawOverride) && "side" in semantic) rawOverride.side = semantic.side;
    if ("side" in rawOverride) rawOverride.side = canonicalSide(rawOverride.side);
    delete rawOverride.semantic;
    delete rawOverride.role;
  }
  return overrides;
}

function captureCurrentDraft() {
  return captureOverrideDraft(state);
}

function applyDraftToState(draft) {
  applyOverrideDraft(state, draft, { normalizeOverrideMap, normalizeLayerOverrideMap });
  if (dom.overrideNotes.value !== state.notes) dom.overrideNotes.value = state.notes;
}

function draftFromServer(overrides, fallbackDraft = {}) {
  return overrideDraftFromServer(
    overrides, fallbackDraft, { normalizeOverrideMap, normalizeLayerOverrideMap },
  );
}

function createIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function numberOr(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function announce(message) {
  dom.liveRegion.textContent = "";
  requestAnimationFrame(() => {
    dom.liveRegion.textContent = message;
  });
}

function showAlert(message, { conflict = false } = {}) {
  dom.globalAlertText.textContent = message;
  dom.globalAlert.hidden = false;
  dom.conflictActions.hidden = !conflict;
}

function hideAlert() {
  dom.globalAlert.hidden = true;
  dom.globalAlertText.textContent = "";
  dom.conflictActions.hidden = true;
}

function setLoading(loading) {
  state.loading = loading;
  dom.canvasLoading.hidden = !loading;
  dom.projectSelect.disabled = loading || state.projects.length === 0;
  dom.refreshProjectsBtn.disabled = loading;
}

function setSaveState(kind, text) {
  dom.saveIndicator.dataset.state = kind;
  dom.saveIndicatorText.textContent = text;
}

function markDirty(message = "存在未保存校正") {
  state.editEpoch += 1;
  state.dirty = true;
  dom.saveBtn.disabled = !state.project || state.saving;
  setSaveState("dirty", "未保存");
  updateStatusbar();
  if (message) announce(message);
}

function clearDirty(message = "校正已保存") {
  state.dirty = false;
  dom.saveBtn.disabled = true;
  setSaveState("saved", "已保存");
  updateStatusbar();
  if (message) announce(message);
}

async function loadProjects({ preserveSelection = true } = {}) {
  const previousId = preserveSelection ? state.selectedProjectId : null;
  hideAlert();
  setLoading(true);
  dom.networkStatus.textContent = "正在连接 API…";

  try {
    const payload = await apiRequest(API_BASE);
    state.projects = normalizeProjectSummaries(payload);
    renderProjectOptions();
    dom.networkStatus.textContent = "API 已连接";

    if (!state.projects.length) {
      if (state.project) {
        showAlert("项目列表当前为空；已保留正在编辑的项目和本地校正。");
      } else {
        state.selectedProjectId = null;
        renderEmptyState("暂无项目", "API 已连接，但工作区中没有可编辑项目。");
      }
      return;
    }

    const requestedId = new URLSearchParams(location.search).get("project");
    const nextId = [previousId, requestedId, state.projects[0].id]
      .find((candidate) => candidate && state.projects.some((project) => project.id === candidate));
    dom.projectSelect.value = nextId;
    await loadProject(nextId);
  } catch (error) {
    state.projects = [];
    renderProjectOptions();
    dom.networkStatus.textContent = "API 连接失败";
    if (!state.project) renderEmptyState("无法加载项目", "请确认工作台服务正在运行，然后重试。");
    showAlert(`项目列表加载失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function renderProjectOptions() {
  dom.projectSelect.replaceChildren();
  if (!state.projects.length) {
    const option = new Option("没有可用项目", "");
    dom.projectSelect.add(option);
    dom.projectSelect.disabled = true;
    return;
  }

  for (const project of state.projects) {
    const option = new Option(project.name, project.id);
    if (project.status) option.dataset.status = project.status;
    dom.projectSelect.add(option);
  }
  dom.projectSelect.disabled = state.loading;
}

async function loadProject(projectId) {
  if (!projectId) return;
  if (state.dirty) {
    const action = String(projectId) === state.selectedProjectId ? "刷新" : "切换";
    const proceed = window.confirm(`当前项目有未保存校正。继续${action}将放弃这些修改，是否继续？`);
    if (!proceed) {
      dom.projectSelect.value = state.selectedProjectId || "";
      return;
    }
  }

  const sequence = ++state.loadSequence;
  setLoading(true);
  dom.saveBtn.disabled = true;
  hideAlert();
  setSaveState("idle", "正在加载");

  try {
    const project = await apiRequest(`${API_BASE}/${encodeURIComponent(projectId)}`);
    if (sequence !== state.loadSequence) return;
    initializeProject(project, projectId);
    const query = new URL(location.href);
    query.searchParams.set("project", projectId);
    history.replaceState(null, "", query);
    requestAnimationFrame(() => fitCanvas());
    announce(`已加载项目 ${project.name || projectId}`);
  } catch (error) {
    if (sequence !== state.loadSequence) return;
    showAlert(`项目加载失败：${error.message}`);
    setSaveState("error", "加载失败");
  } finally {
    if (sequence === state.loadSequence) {
      setLoading(false);
      if (state.dirty && !state.saving) dom.saveBtn.disabled = false;
    }
  }
}

function initializeProject(project, fallbackId) {
  state.project = project || {};
  state.selectedProjectId = String(project?.id ?? fallbackId);
  state.selectedLayerId = null;
  state.selectedJointId = null;
  state.search = "";
  state.dirty = false;
  state.editEpoch = 0;
  state.conflictPatch = null;
  state.previewOpacity = 1;
  state.showComposite = true;
  state.showSkeleton = true;

  const overrides = project?.overrides || {};
  state.baseRevision = overrides.revision ?? project?.revision ?? 0;
  state.jointOverrides = normalizeOverrideMap(overrides.joint_overrides);
  state.jointDecisions = normalizeOverrideMap(overrides.joint_decisions);
  state.layerOverrides = normalizeLayerOverrideMap(overrides.layer_overrides);
  state.notes = String(overrides.notes ?? "");
  state.persistedDraft = captureCurrentDraft();

  dom.projectSelect.value = state.selectedProjectId;
  dom.layerSearch.value = "";
  dom.clearSearchBtn.hidden = true;
  dom.previewOpacity.value = "100";
  dom.previewOpacityValue.textContent = "100%";
  dom.overrideNotes.value = state.notes;
  dom.revisionBadge.textContent = `r${state.baseRevision}`;
  setSaveState("idle", "尚未修改");
  dom.saveBtn.disabled = true;

  renderWorkflow();
  renderLayerList();
  renderCanvas();
  renderInspectors();
  renderQa();
  renderCapabilities();
  updateStatusbar();
}

function getCanvasSize() {
  const canvas = state.project?.canvas || {};
  return {
    width: Math.max(1, numberOr(canvas.width ?? canvas.w, 1)),
    height: Math.max(1, numberOr(canvas.height ?? canvas.h, 1)),
  };
}

function getLayers() {
  return Array.isArray(state.project?.layers) ? state.project.layers : [];
}

function getJoints() {
  return Array.isArray(state.project?.skeleton?.joints) ? state.project.skeleton.joints : [];
}

function getBones() {
  if (Array.isArray(state.project?.bones)) return state.project.bones;
  return Array.isArray(state.project?.skeleton?.bones) ? state.project.skeleton.bones : [];
}

function effectiveLayer(layer) {
  const override = state.layerOverrides[String(layer.id)] || {};
  const semanticOverride = override.semantic || {};
  const sourceSemantic = layer.semantic || {};
  const canonicalRole = override.canonical_role ?? semanticOverride.canonical_role ?? semanticOverride.role
    ?? layer.canonical_role ?? sourceSemantic.canonical_role ?? sourceSemantic.role ?? "unknown";
  const side = canonicalSide(override.side ?? semanticOverride.side ?? layer.side ?? sourceSemantic.side);
  const disposition = override.disposition ?? layer.disposition ?? "review";
  const inferredConfidence = disposition === "review" ? 0.45 : disposition === "exclude" ? 0.7 : 0.82;
  return {
    ...layer,
    visible: override.visible ?? layer.visible ?? true,
    canonical_role: canonicalRole,
    side,
    disposition,
    semantic: {
      ...sourceSemantic,
      ...semanticOverride,
      role: canonicalRole,
      canonical_role: canonicalRole,
      side,
      confidence: sourceSemantic.confidence ?? layer.semantic_confidence ?? layer.confidence ?? inferredConfidence,
    },
  };
}

function effectiveJoint(joint) {
  const override = state.jointOverrides[String(joint.id)] || {};
  const decision = state.jointDecisions[String(joint.id)] || {};
  const decisionPoint = Array.isArray(decision.final_xy) ? decision.final_xy : [];
  return {
    ...joint,
    x: numberOr(override.x, numberOr(decisionPoint[0], numberOr(joint.x))),
    y: numberOr(override.y, numberOr(decisionPoint[1], numberOr(joint.y))),
    reviewAction: decision.action || null,
    isManual: Object.prototype.hasOwnProperty.call(state.jointOverrides, String(joint.id)),
  };
}

function getSelectedLayer() {
  const layer = getLayers().find((item) => String(item.id) === state.selectedLayerId);
  return layer ? effectiveLayer(layer) : null;
}

function getSelectedJoint() {
  const joint = getJoints().find((item) => String(item.id) === state.selectedJointId);
  return joint ? effectiveJoint(joint) : null;
}

function renderWorkflow() {
  const stages = normalizeWorkflow(state.project?.workflow);
  if (!state.activeStage || !stages.some((stage) => stage.id === state.activeStage)) {
    const requested = state.project?.workflow?.current_stage;
    state.activeStage = stages.find((stage) => stage.id === requested)?.id
      || stages.find((stage) => ["active", "in_progress", "current", "needs_review"].includes(stage.status))?.id
      || stages[0]?.id;
  }

  dom.workflowNav.replaceChildren();
  stages.forEach((stage, index) => {
    const button = document.createElement("button");
    button.className = "workflow-step";
    button.type = "button";
    button.dataset.status = stage.status;
    if (stage.id === state.activeStage) button.setAttribute("aria-current", "step");

    const stepIndex = document.createElement("span");
    stepIndex.className = "step-index";
    stepIndex.textContent = String(index + 1).padStart(2, "0");
    const label = document.createElement("span");
    label.textContent = stage.label;
    button.append(stepIndex, label);
    button.addEventListener("click", () => activateStage(stage));
    dom.workflowNav.append(button);
  });
}

function activateStage(stage) {
  state.activeStage = stage.id;
  const id = stage.id.toLowerCase();
  if (id.includes("joint") || id.includes("skeleton") || id.includes("rig") || id.includes("anchor")) {
    setEditMode("joints");
  } else if (id.includes("layer") || id.includes("decomp") || id.includes("ingest")) {
    setEditMode("layers");
  }
  renderWorkflow();
  announce(`已切换到${stage.label}阶段`);
}

function filterLayers() {
  const query = state.search.trim().toLocaleLowerCase();
  if (!query) return getLayers();
  return getLayers().filter((layer) => {
    const effective = effectiveLayer(layer);
    const flags = normalizeQaFlags(layer.qa_flags).map((flag) => `${flag.code} ${flag.message}`).join(" ");
    return [layer.id, layer.name, effective.semantic?.role, effective.semantic?.side, effective.disposition, flags]
      .some((value) => String(value ?? "").toLocaleLowerCase().includes(query));
  });
}

function renderLayerList() {
  const layers = getLayers();
  const filtered = filterLayers();
  const visible = layers.filter((layer) => effectiveLayer(layer).visible).length;
  dom.layerCounter.textContent = state.search ? `${filtered.length}/${layers.length}` : String(layers.length);
  dom.visibleLayerCount.textContent = `${visible} 可见`;
  dom.layerList.replaceChildren();

  if (!state.project) {
    const placeholder = document.createElement("div");
    placeholder.className = "list-placeholder";
    placeholder.textContent = "选择项目后显示图层";
    dom.layerList.append(placeholder);
    return;
  }

  if (!filtered.length) {
    const placeholder = document.createElement("div");
    placeholder.className = "list-placeholder";
    placeholder.textContent = state.search ? "没有匹配的图层" : "当前项目没有图层";
    dom.layerList.append(placeholder);
    return;
  }

  for (const rawLayer of filtered) {
    const layer = effectiveLayer(rawLayer);
    const id = String(layer.id);
    const row = document.createElement("div");
    row.className = "layer-row";
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", String(id === state.selectedLayerId));
    row.dataset.layerId = id;
    if (!layer.visible) row.classList.add("is-hidden");
    if (layer.empty) row.classList.add("is-empty");

    const visibilityButton = document.createElement("button");
    visibilityButton.className = "visibility-button";
    visibilityButton.type = "button";
    visibilityButton.title = layer.visible ? "隐藏图层" : "显示图层";
    visibilityButton.setAttribute("aria-label", `${layer.visible ? "隐藏" : "显示"}图层 ${layer.name || id}`);
    visibilityButton.append(createIcon(layer.visible ? "eye" : "eye-off"));
    visibilityButton.addEventListener("click", (event) => {
      event.stopPropagation();
      setLayerVisibility(id, !layer.visible);
    });

    const main = document.createElement("button");
    main.className = "layer-row-main";
    main.type = "button";
    main.title = layer.name || id;
    const name = document.createElement("strong");
    name.textContent = layer.name || id;
    const meta = document.createElement("span");
    meta.className = "layer-meta";
    const role = document.createElement("span");
    role.className = "role-tag";
    role.textContent = layer.semantic?.role || "unknown";
    const side = document.createElement("span");
    side.className = "side-tag";
    side.textContent = normalizeSide(layer.semantic?.side);
    meta.append(role, side);
    const qaCount = layerQaFlags(layer).length;
    if (qaCount) {
      const marker = document.createElement("span");
      marker.className = "qa-marker";
      marker.textContent = `QA ${qaCount}`;
      meta.append(marker);
    }
    main.append(name, meta);
    main.addEventListener("click", () => selectLayer(id));

    const stateDot = document.createElement("span");
    stateDot.className = `layer-state-dot ${confidenceLevel(layer.semantic?.confidence)}`;
    stateDot.title = `语义置信度 ${formatConfidence(layer.semantic?.confidence)}`;
    row.append(visibilityButton, main, stateDot);
    dom.layerList.append(row);
  }
}

function normalizeSide(value) {
  const side = String(value ?? "unknown").toUpperCase();
  if (["LEFT", "L"].includes(side)) return "L";
  if (["RIGHT", "R"].includes(side)) return "R";
  if (["CENTER", "CENTRE", "C", "NONE", "N/A"].includes(side)) return "C";
  if (["BILATERAL", "B", "BOTH"].includes(side)) return "B";
  return "?";
}

function canonicalSide(value) {
  const side = String(value ?? "unknown").toLowerCase();
  if (["left", "l"].includes(side)) return "left";
  if (["right", "r"].includes(side)) return "right";
  if (["center", "centre", "c", "none", "n/a"].includes(side)) return "center";
  if (["bilateral", "b", "both"].includes(side)) return "bilateral";
  return "unknown";
}

function selectLayer(id) {
  state.selectedLayerId = String(id);
  setEditMode("layers", { announceChange: false });
  renderLayerList();
  renderLayerInspector();
  renderLayerSelection();
  updateStatusbar();
  const layer = getSelectedLayer();
  announce(`已选择图层 ${layer?.name || id}`);
}

function selectJoint(id) {
  state.selectedJointId = String(id);
  setEditMode("joints", { announceChange: false });
  renderSkeleton();
  renderJointInspector();
  updateStatusbar();
  announce(`已选择关节 ${id}`);
}

function ensureLayerOverride(layerId) {
  if (!state.layerOverrides[layerId]) state.layerOverrides[layerId] = {};
  return state.layerOverrides[layerId];
}

function setLayerVisibility(layerId, visible, { quiet = false } = {}) {
  const override = ensureLayerOverride(String(layerId));
  override.visible = Boolean(visible);
  markDirty(quiet ? "" : `图层已${visible ? "显示" : "隐藏"}`);
  renderLayerList();
  renderCanvasLayers();
  if (state.selectedLayerId === String(layerId)) renderLayerInspector();
}

function bulkSetVisibility(visible) {
  for (const layer of getLayers()) {
    const override = ensureLayerOverride(String(layer.id));
    override.visible = visible;
  }
  markDirty(visible ? "全部图层已显示" : "全部图层已隐藏");
  renderLayerList();
  renderCanvasLayers();
  renderLayerInspector();
}

function normalizeBbox(bbox) {
  const { width: canvasWidth, height: canvasHeight } = getCanvasSize();
  if (Array.isArray(bbox)) {
    return {
      x: numberOr(bbox[0]),
      y: numberOr(bbox[1]),
      width: Math.max(0, numberOr(bbox[2], canvasWidth)),
      height: Math.max(0, numberOr(bbox[3], canvasHeight)),
    };
  }
  if (bbox && typeof bbox === "object") {
    const x = numberOr(bbox.x ?? bbox.left ?? bbox.x0);
    const y = numberOr(bbox.y ?? bbox.top ?? bbox.y0);
    const width = numberOr(bbox.width ?? bbox.w, numberOr(bbox.x1) - x || canvasWidth);
    const height = numberOr(bbox.height ?? bbox.h, numberOr(bbox.y1) - y || canvasHeight);
    return { x, y, width: Math.max(0, width), height: Math.max(0, height) };
  }
  return { x: 0, y: 0, width: canvasWidth, height: canvasHeight };
}

function renderCanvas() {
  if (!state.project) {
    dom.canvasSpace.hidden = true;
    renderEmptyState("选择一个项目", "项目加载完成后，可在此检查图层、拖拽关节并预览覆盖。");
    return;
  }

  const { width, height } = getCanvasSize();
  dom.canvasEmpty.hidden = true;
  dom.canvasSpace.hidden = false;
  dom.canvasSurface.style.width = `${width}px`;
  dom.canvasSurface.style.height = `${height}px`;
  dom.skeletonSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  dom.skeletonSvg.setAttribute("width", String(width));
  dom.skeletonSvg.setAttribute("height", String(height));

  const compositeUrl = state.project?.assets?.composite_url || state.project?.composite_url || "";
  if (compositeUrl) {
    dom.compositeImage.src = compositeUrl;
    dom.compositeImage.hidden = !state.showComposite;
  } else {
    dom.compositeImage.removeAttribute("src");
    dom.compositeImage.hidden = true;
  }

  renderCanvasLayers();
  renderSkeleton();
  applyPreviewOpacity();
  applyZoom();
}

function renderEmptyState(title, text) {
  dom.canvasSpace.hidden = true;
  dom.canvasEmpty.hidden = false;
  dom.canvasEmptyTitle.textContent = title;
  dom.canvasEmptyText.textContent = text;
}

function renderCanvasLayers() {
  dom.layerStack.replaceChildren();
  if (!state.project) return;
  const canvas = getCanvasSize();

  getLayers().forEach((rawLayer, index) => {
    const layer = effectiveLayer(rawLayer);
    if (!layer.visible || layer.empty || !layer.image_url) return;
    const bbox = normalizeBbox(layer.bbox);
    const image = document.createElement("img");
    image.className = "layer-image";
    image.src = layer.image_url;
    image.alt = "";
    image.draggable = false;
    image.dataset.layerId = String(layer.id);
    image.style.left = `${bbox.x}px`;
    image.style.top = `${bbox.y}px`;
    image.style.width = `${bbox.width}px`;
    image.style.height = `${bbox.height}px`;
    image.style.zIndex = String(index + 1);
    image.addEventListener("load", () => {
      if (image.naturalWidth === canvas.width && image.naturalHeight === canvas.height) {
        image.style.left = "0px";
        image.style.top = "0px";
        image.style.width = `${canvas.width}px`;
        image.style.height = `${canvas.height}px`;
      }
    }, { once: true });
    image.addEventListener("pointerdown", (event) => {
      if (state.editMode !== "layers") return;
      event.preventDefault();
      event.stopPropagation();
      selectLayer(String(layer.id));
    });
    dom.layerStack.append(image);
  });

  applyPreviewOpacity();
  renderLayerSelection();
}

function renderLayerSelection() {
  dom.layerSelectionGroup.replaceChildren();
  const layer = getSelectedLayer();
  if (!layer) return;
  const bbox = normalizeBbox(layer.bbox);
  const rect = document.createElementNS(SVG_NS, "rect");
  rect.classList.add("selected-layer-box");
  rect.setAttribute("x", String(bbox.x));
  rect.setAttribute("y", String(bbox.y));
  rect.setAttribute("width", String(bbox.width));
  rect.setAttribute("height", String(bbox.height));
  dom.layerSelectionGroup.append(rect);

  const radius = Math.max(2.5, Math.min(getCanvasSize().width, getCanvasSize().height) * 0.0035);
  [[bbox.x, bbox.y], [bbox.x + bbox.width, bbox.y], [bbox.x, bbox.y + bbox.height], [bbox.x + bbox.width, bbox.y + bbox.height]]
    .forEach(([x, y]) => {
      const point = document.createElementNS(SVG_NS, "circle");
      point.classList.add("selected-layer-corner");
      point.setAttribute("cx", String(x));
      point.setAttribute("cy", String(y));
      point.setAttribute("r", String(radius));
      dom.layerSelectionGroup.append(point);
    });
}

const skeletonRenderer = createSkeletonRenderer({
  boneGroup: dom.boneGroup,
  jointGroup: dom.jointGroup,
  skeletonSvg: dom.skeletonSvg,
  clamp,
  numberOr,
  formatConfidence,
  onJointPointerDown,
  onSelectJoint: selectJoint,
});

function renderSkeleton() {
  skeletonRenderer.render({
    visible: state.showSkeleton,
    hasProject: Boolean(state.project),
    joints: getJoints().map(effectiveJoint),
    bones: getBones(),
    selectedJointId: state.selectedJointId,
    canvasSize: getCanvasSize(),
  });
}

function onJointPointerDown(event) {
  if (state.editMode !== "joints") return;
  event.preventDefault();
  event.stopPropagation();
  const id = event.currentTarget.dataset.jointId;
  selectJoint(id);
  state.dragJointId = id;
  state.dragPointerStart = { x: event.clientX, y: event.clientY };
  dom.skeletonSvg.setPointerCapture(event.pointerId);
}

function updateJointFromPointer(event) {
  if (!state.dragJointId) return;
  if (state.dragPointerStart) {
    const distance = Math.hypot(
      event.clientX - state.dragPointerStart.x,
      event.clientY - state.dragPointerStart.y,
    );
    if (distance < 2) return;
    state.dragPointerStart = null;
  }
  const rect = dom.skeletonSvg.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const { width, height } = getCanvasSize();
  const x = clamp((event.clientX - rect.left) * width / rect.width, 0, width);
  const y = clamp((event.clientY - rect.top) * height / rect.height, 0, height);
  setJointOverride(state.dragJointId, x, y, { render: true, announceChange: false });
}

function setJointOverride(jointId, x, y, { render = true, announceChange = true } = {}) {
  delete state.jointDecisions[String(jointId)];
  state.jointOverrides[String(jointId)] = {
    ...(state.jointOverrides[String(jointId)] || {}),
    x: Math.round(x * 10) / 10,
    y: Math.round(y * 10) / 10,
  };
  markDirty(announceChange ? `关节 ${jointId} 已校正` : "");
  if (render) {
    renderSkeleton();
    renderJointInspector();
  }
}

function nudgeSelectedJoint(dx, dy) {
  const joint = getSelectedJoint();
  if (!joint) return;
  const { width, height } = getCanvasSize();
  setJointOverride(joint.id, clamp(joint.x + dx, 0, width), clamp(joint.y + dy, 0, height));
}

function renderInspectors() {
  renderLayerInspector();
  renderJointInspector();
}

function renderLayerInspector() {
  const layer = getSelectedLayer();
  dom.layerSelectionEmpty.hidden = Boolean(layer);
  dom.layerFields.hidden = !layer;
  if (!layer) {
    setConfidenceBadge(dom.layerConfidence, NaN);
    return;
  }

  const bbox = normalizeBbox(layer.bbox);
  const side = canonicalSide(layer.semantic?.side);
  dom.selectedLayerName.textContent = layer.name || String(layer.id);
  dom.selectedLayerId.textContent = String(layer.id);
  dom.selectedLayerBbox.textContent = `${Math.round(bbox.x)}, ${Math.round(bbox.y)} · ${Math.round(bbox.width)}×${Math.round(bbox.height)}`;
  dom.selectedLayerState.textContent = layer.empty ? "空图层" : `${layer.visible ? "可见" : "隐藏"} · ${layer.disposition}`;
  dom.semanticRoleInput.value = layer.semantic?.role || "unknown";
  dom.semanticSideSelect.value = side;
  dom.layerDispositionSelect.value = ["keep", "exclude", "split", "review"].includes(layer.disposition) ? layer.disposition : "review";
  dom.selectedLayerVisible.checked = Boolean(layer.visible);
  dom.layerSwatch.style.background = semanticColor(layer.semantic?.role);
  setConfidenceBadge(dom.layerConfidence, layer.semantic?.confidence);
}

function renderJointInspector() {
  const joint = getSelectedJoint();
  dom.jointSelectionEmpty.hidden = Boolean(joint);
  dom.jointFields.hidden = !joint;
  if (!joint) {
    setConfidenceBadge(dom.jointConfidence, NaN);
    return;
  }

  dom.selectedJointName.textContent = String(joint.id);
  dom.selectedJointState.textContent = joint.isManual ? "已人工校正" : joint.state || joint.source || "自动推断";
  dom.jointXInput.value = String(Math.round(joint.x * 10) / 10);
  dom.jointYInput.value = String(Math.round(joint.y * 10) / 10);
  dom.resetJointBtn.disabled = !joint.isManual;
  setConfidenceBadge(dom.jointConfidence, joint.confidence);
}

function semanticColor(role) {
  const text = String(role || "unknown");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
  const palette = ["#65c7ff", "#a998ff", "#54d89a", "#f0b85d", "#ff8ca0", "#57d5cc", "#7aa7ff"];
  return palette[Math.abs(hash) % palette.length];
}

function normalizeQaFlags(value) {
  const list = Array.isArray(value) ? value : value ? [value] : [];
  return list.map((flag, index) => {
    if (typeof flag === "string") return { code: flag, message: flag, severity: "warning" };
    return {
      ...flag,
      code: String(flag?.code || flag?.id || `QA-${index + 1}`),
      message: String(flag?.message || flag?.detail || flag?.label || flag?.code || "需要复核"),
      severity: String(flag?.severity || flag?.level || "warning").toLowerCase(),
    };
  });
}

function layerQaFlags(layer) {
  const flags = normalizeQaFlags(layer.qa_flags);
  if (layer.empty && !flags.some((flag) => flag.code === "EMPTY_LAYER")) {
    flags.push({ code: "EMPTY_LAYER", message: "空图层需要排除或复核", severity: "warning" });
  }
  if (layer.disposition === "review" && !flags.some((flag) => flag.code === "LAYER_REVIEW")) {
    flags.push({ code: "LAYER_REVIEW", message: "图层语义或侧别需要人工复核", severity: "warning" });
  }
  return flags;
}

function collectQaFlags() {
  const items = normalizeQaFlags(state.project?.qa_flags).map((flag) => ({ ...flag, layerId: null }));
  for (const layer of getLayers()) {
    layerQaFlags(effectiveLayer(layer)).forEach((flag) => items.push({ ...flag, layerId: String(layer.id), layerName: layer.name }));
  }
  const auditWarnings = state.project?.workflow?.audit_warnings;
  const compositeFlag = compositeQaFlag(auditWarnings);
  if (compositeFlag) items.unshift(compositeFlag);
  if (numberOr(auditWarnings?.empty_layer_count) > 0) {
    items.unshift({
      code: "EMPTY_LAYERS",
      message: `${numberOr(auditWarnings.empty_layer_count)} 个空图层不会参与绑定`,
      severity: "warning",
      layerId: null,
    });
  }
  const unresolvedCount = unresolvedJointIds(state.project, getJoints()).length;
  if (unresolvedCount) {
    items.push({
      code: "UNRESOLVED_JOINTS",
      message: `${unresolvedCount} 个启发式关节尚未复核，请在骨骼模式校正`,
      severity: "warning",
      layerId: null,
    });
  }
  return items;
}

function renderQa() {
  const flags = collectQaFlags();
  dom.qaCounter.textContent = String(flags.length);
  dom.qaList.replaceChildren();
  if (!flags.length) {
    const empty = document.createElement("div");
    empty.className = "selection-empty";
    empty.textContent = "当前项目没有 QA 警告。";
    dom.qaList.append(empty);
    return;
  }

  flags.slice(0, 30).forEach((flag) => {
    const item = document.createElement(flag.layerId ? "button" : "div");
    item.className = "qa-item";
    item.dataset.severity = flag.severity;
    if (flag.layerId) item.type = "button";
    item.append(createIcon("warning"));
    const content = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = flag.message;
    const meta = document.createElement("small");
    meta.textContent = flag.layerId ? `${flag.code} · ${flag.layerName || flag.layerId}` : flag.code;
    content.append(title, meta);
    item.append(content);
    if (flag.layerId) item.addEventListener("click", () => selectLayer(flag.layerId));
    dom.qaList.append(item);
  });
}

function flattenCapabilities(value, prefix = "", depth = 0) {
  if (depth > 4 || value == null) return [];
  if (typeof value !== "object" || Array.isArray(value)) {
    return [{ key: prefix || "value", value }];
  }
  if ("state" in value || "available" in value || "enabled" in value) {
    const stateValue = value.state ?? value.available ?? value.enabled;
    const confidence = Number(value.confidence);
    const display = Number.isFinite(confidence) ? `${stateValue} · ${Math.round(confidence * 100)}%` : stateValue;
    return [{ key: prefix || "capability", value: display, state: String(stateValue).toLowerCase() }];
  }
  return Object.entries(value).flatMap(([key, child]) => flattenCapabilities(child, prefix ? `${prefix}.${key}` : key, depth + 1));
}

function renderCapabilities() {
  const capabilities = flattenCapabilities(state.project?.capabilities).slice(0, 40);
  dom.capabilityList.replaceChildren();
  if (!capabilities.length) {
    const empty = document.createElement("div");
    empty.className = "selection-empty";
    empty.textContent = "暂无能力数据。";
    dom.capabilityList.append(empty);
    return;
  }

  capabilities.forEach((capability) => {
    const row = document.createElement("div");
    row.className = "capability-row";
    const key = document.createElement("span");
    key.textContent = capability.key;
    key.title = capability.key;
    const value = document.createElement("span");
    value.className = "capability-state";
    const rawState = capability.state || String(capability.value).split(" · ")[0].toLowerCase();
    value.dataset.state = rawState;
    value.textContent = formatCapabilityValue(capability.value);
    row.append(key, value);
    dom.capabilityList.append(row);
  });
}

function formatCapabilityValue(value) {
  if (typeof value === "boolean") return value ? "ready" : "missing";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "—");
}

function setEditMode(mode, { announceChange = true } = {}) {
  state.editMode = mode === "joints" ? "joints" : "layers";
  dom.canvasViewport.dataset.mode = state.editMode;
  const isLayers = state.editMode === "layers";
  dom.layerModeBtn.setAttribute("aria-pressed", String(isLayers));
  dom.jointModeBtn.setAttribute("aria-pressed", String(!isLayers));
  if (announceChange) announce(isLayers ? "已切换到图层编辑模式" : "已切换到关节编辑模式");
}

function applyPreviewOpacity() {
  dom.layerStack.style.opacity = String(state.previewOpacity);
  dom.previewOpacityValue.textContent = `${Math.round(state.previewOpacity * 100)}%`;
}

function setToggleButton(button, active) {
  button.classList.toggle("active", active);
  button.setAttribute("aria-pressed", String(active));
}

function setZoom(nextZoom) {
  state.zoom = clamp(nextZoom, 0.05, 6);
  applyZoom();
}

function applyZoom() {
  if (!state.project) return;
  const { width, height } = getCanvasSize();
  const padding = 48;
  dom.canvasSurface.style.transform = `scale(${state.zoom})`;
  dom.canvasSpace.style.width = `${Math.max(dom.canvasViewport.clientWidth, width * state.zoom + padding)}px`;
  dom.canvasSpace.style.height = `${Math.max(dom.canvasViewport.clientHeight, height * state.zoom + padding)}px`;

  const scaledWidth = width * state.zoom;
  const scaledHeight = height * state.zoom;
  const left = Math.max(24, (dom.canvasViewport.clientWidth - scaledWidth) / 2);
  const top = Math.max(24, (dom.canvasViewport.clientHeight - scaledHeight) / 2);
  dom.canvasSurface.style.left = `${left}px`;
  dom.canvasSurface.style.top = `${top}px`;
  dom.zoomValueBtn.textContent = `${Math.round(state.zoom * 100)}%`;
  updateStatusbar();
}

function fitCanvas() {
  if (!state.project) return;
  const { width, height } = getCanvasSize();
  const availableWidth = Math.max(100, dom.canvasViewport.clientWidth - 52);
  const availableHeight = Math.max(100, dom.canvasViewport.clientHeight - 52);
  state.fitZoom = clamp(Math.min(availableWidth / width, availableHeight / height), 0.05, 4);
  setZoom(state.fitZoom);
  dom.canvasViewport.scrollTo({ left: 0, top: 0, behavior: "auto" });
}

function updateStatusbar() {
  if (!state.project) {
    dom.canvasStatus.textContent = "画布 —";
    dom.selectionStatus.textContent = "未选择对象";
    dom.overrideStatus.textContent = "0 项校正";
    return;
  }
  const { width, height } = getCanvasSize();
  dom.canvasStatus.textContent = `${width}×${height} · ${Math.round(state.zoom * 100)}%`;
  const layer = getSelectedLayer();
  const joint = getSelectedJoint();
  dom.selectionStatus.textContent = state.editMode === "joints" && joint
    ? `关节 ${joint.id} · ${joint.x.toFixed(1)}, ${joint.y.toFixed(1)}`
    : layer ? `图层 ${layer.name || layer.id}` : "未选择对象";
  const jointCount = Object.keys(state.jointOverrides).length;
  const decisionCount = Object.keys(state.jointDecisions).length;
  const layerCount = Object.keys(state.layerOverrides).length;
  dom.overrideStatus.textContent = `${jointCount + decisionCount + layerCount} 项校正 · r${state.baseRevision ?? "—"}`;
}

async function saveOverrides() {
  if (!state.project || state.saving || !state.dirty) return;
  const snapshot = captureSaveSnapshot({
    projectId: state.selectedProjectId,
    baseRevision: state.baseRevision,
    editEpoch: state.editEpoch,
    draft: captureCurrentDraft(),
  });
  state.saving = true;
  dom.saveBtn.disabled = true;
  setSaveState("saving", "正在保存");
  hideAlert();

  const body = {
    base_revision: snapshot.baseRevision,
    ...snapshot.draft,
  };

  try {
    const payload = await apiRequest(`${API_BASE}/${encodeURIComponent(snapshot.projectId)}/overrides`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    if (state.selectedProjectId !== snapshot.projectId) return;
    const nextOverrides = payload?.overrides || payload || {};
    const reconciled = reconcileSaveResponse({
      snapshot,
      liveDraft: captureCurrentDraft(),
      serverDraft: draftFromServer(nextOverrides, snapshot.draft),
      currentEditEpoch: state.editEpoch,
    });
    state.baseRevision = nextOverrides.revision ?? payload?.revision ?? state.baseRevision;
    state.persistedDraft = reconciled.persistedDraft;
    applyDraftToState(reconciled.draft);
    state.conflictPatch = null;
    dom.revisionBadge.textContent = `r${state.baseRevision}`;
    if (reconciled.hasPendingEdits) {
      state.dirty = true;
      setSaveState("dirty", "仍有未保存编辑");
      announce("保存快照已完成；保存期间的新编辑仍待保存");
    } else {
      clearDirty();
    }
    renderLayerList();
    renderSkeleton();
    renderInspectors();
    renderQa();
    updateStatusbar();
  } catch (error) {
    const conflict = error.status === 409;
    if (conflict && state.selectedProjectId === snapshot.projectId) {
      state.conflictPatch = buildCurrentLocalPatchArtifact();
    }
    setSaveState("error", conflict ? "版本冲突" : "保存失败");
    showAlert(
      conflict
        ? "保存失败：服务端已有新版本。本地校正仍保留；可先导出 patch，或加载最新版本并将本地命令重放到其上。重叠字段以本地值为准。"
        : `保存校正失败：${error.message}`,
      { conflict },
    );
    announce(conflict ? "保存时发生版本冲突，本地校正已保留" : "保存失败");
    dom.saveBtn.disabled = false;
  } finally {
    state.saving = false;
    if (state.dirty) dom.saveBtn.disabled = false;
  }
}

function buildCurrentLocalPatchArtifact() {
  if (!state.project) return null;
  return createLocalPatchArtifact({
    projectId: state.selectedProjectId,
    baseRevision: state.baseRevision,
    baseDraft: state.persistedDraft || {},
    currentDraft: captureCurrentDraft(),
  });
}

function exportLocalPatch() {
  const artifact = buildCurrentLocalPatchArtifact();
  if (!artifact) return;
  state.conflictPatch = artifact;
  const blob = new Blob([`${JSON.stringify(artifact, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeProjectId = state.selectedProjectId.replace(/[^A-Za-z0-9_.-]+/g, "-");
  link.href = url;
  link.download = `${safeProjectId}.local-patch.r${state.baseRevision}.json`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  announce(`已导出包含 ${artifact.operations.length} 条命令的本地 patch`);
}

async function reloadLatestAndReplay() {
  const artifact = buildCurrentLocalPatchArtifact();
  if (!artifact || state.loading || state.saving) return;
  const projectId = state.selectedProjectId;
  const sequence = ++state.loadSequence;
  setLoading(true);
  dom.saveBtn.disabled = true;
  hideAlert();
  setSaveState("idle", "加载最新版本");
  try {
    const project = await apiRequest(`${API_BASE}/${encodeURIComponent(projectId)}`);
    if (sequence !== state.loadSequence || state.selectedProjectId !== projectId) return;
    initializeProject(project, projectId);
    applyDraftToState(applyDraftPatch(state.persistedDraft, artifact.operations));
    state.conflictPatch = null;
    if (artifact.operations.length) {
      markDirty(`已在 r${state.baseRevision} 上重放 ${artifact.operations.length} 条本地命令`);
    }
    renderLayerList();
    renderCanvasLayers();
    renderSkeleton();
    renderInspectors();
    renderQa();
    updateStatusbar();
  } catch (error) {
    state.conflictPatch = artifact;
    setSaveState("error", "重放失败");
    showAlert(`加载最新版本失败：${error.message}。本地校正仍保留，可先导出 patch。`, { conflict: true });
  } finally {
    if (sequence === state.loadSequence) {
      setLoading(false);
      if (state.dirty && !state.saving) dom.saveBtn.disabled = false;
    }
  }
}

function updateSelectedLayerSemantic() {
  const layer = getSelectedLayer();
  if (!layer) return;
  const id = String(layer.id);
  const override = ensureLayerOverride(id);
  const role = dom.semanticRoleInput.value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(role)) {
    dom.semanticRoleInput.setCustomValidity("请输入由字母、数字、点、下划线、冒号或短横线组成的语义 token");
    dom.semanticRoleInput.reportValidity();
    return;
  }
  dom.semanticRoleInput.setCustomValidity("");
  delete override.semantic;
  delete override.role;
  override.canonical_role = role;
  override.side = canonicalSide(dom.semanticSideSelect.value);
  markDirty("图层语义已校正");
  renderLayerList();
  renderLayerInspector();
}

function updateJointFromInputs() {
  const joint = getSelectedJoint();
  if (!joint) return;
  const { width, height } = getCanvasSize();
  const x = clamp(numberOr(dom.jointXInput.value, joint.x), 0, width);
  const y = clamp(numberOr(dom.jointYInput.value, joint.y), 0, height);
  setJointOverride(joint.id, x, y);
}

function resetSelectedJoint() {
  const joint = getSelectedJoint();
  if (!joint) return;
  delete state.jointOverrides[String(joint.id)];
  delete state.jointDecisions[String(joint.id)];
  markDirty(`关节 ${joint.id} 已恢复自动位置`);
  renderSkeleton();
  renderJointInspector();
}

function isTypingTarget(target) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
}

function onGlobalKeyDown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveOverrides();
    return;
  }
  if (isTypingTarget(event.target)) return;
  if (event.key === "0") {
    event.preventDefault();
    fitCanvas();
    return;
  }
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    setZoom(state.zoom * 1.15);
    return;
  }
  if (event.key === "-" || event.key === "_") {
    event.preventDefault();
    setZoom(state.zoom / 1.15);
    return;
  }
  if (state.editMode !== "joints" || !state.selectedJointId || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const step = event.shiftKey ? 10 : event.altKey ? 0.1 : 1;
  if (event.key === "ArrowLeft") nudgeSelectedJoint(-step, 0);
  if (event.key === "ArrowRight") nudgeSelectedJoint(step, 0);
  if (event.key === "ArrowUp") nudgeSelectedJoint(0, -step);
  if (event.key === "ArrowDown") nudgeSelectedJoint(0, step);
}

function bindEvents() {
  dom.refreshProjectsBtn.addEventListener("click", () => loadProjects());
  dom.projectSelect.addEventListener("change", (event) => loadProject(event.target.value));
  dom.dismissAlertBtn.addEventListener("click", hideAlert);
  dom.exportLocalPatchBtn.addEventListener("click", exportLocalPatch);
  dom.replayConflictBtn.addEventListener("click", reloadLatestAndReplay);
  dom.saveBtn.addEventListener("click", saveOverrides);

  dom.layerSearch.addEventListener("input", (event) => {
    state.search = event.target.value;
    dom.clearSearchBtn.hidden = !state.search;
    renderLayerList();
  });
  dom.clearSearchBtn.addEventListener("click", () => {
    state.search = "";
    dom.layerSearch.value = "";
    dom.clearSearchBtn.hidden = true;
    renderLayerList();
    dom.layerSearch.focus();
  });
  dom.showAllLayersBtn.addEventListener("click", () => bulkSetVisibility(true));
  dom.hideAllLayersBtn.addEventListener("click", () => bulkSetVisibility(false));

  dom.layerModeBtn.addEventListener("click", () => setEditMode("layers"));
  dom.jointModeBtn.addEventListener("click", () => setEditMode("joints"));
  dom.toggleCompositeBtn.addEventListener("click", () => {
    state.showComposite = !state.showComposite;
    dom.compositeImage.hidden = !state.showComposite || !dom.compositeImage.getAttribute("src");
    setToggleButton(dom.toggleCompositeBtn, state.showComposite);
  });
  dom.toggleSkeletonBtn.addEventListener("click", () => {
    state.showSkeleton = !state.showSkeleton;
    setToggleButton(dom.toggleSkeletonBtn, state.showSkeleton);
    renderSkeleton();
  });
  dom.previewOpacity.addEventListener("input", (event) => {
    state.previewOpacity = numberOr(event.target.value, 100) / 100;
    applyPreviewOpacity();
  });
  dom.zoomOutBtn.addEventListener("click", () => setZoom(state.zoom / 1.15));
  dom.zoomInBtn.addEventListener("click", () => setZoom(state.zoom * 1.15));
  dom.fitCanvasBtn.addEventListener("click", fitCanvas);
  dom.zoomValueBtn.addEventListener("click", fitCanvas);
  dom.canvasViewport.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    setZoom(state.zoom * (event.deltaY > 0 ? 0.92 : 1.08));
  }, { passive: false });

  dom.skeletonSvg.addEventListener("pointermove", updateJointFromPointer);
  dom.skeletonSvg.addEventListener("pointerup", (event) => {
    state.dragJointId = null;
    state.dragPointerStart = null;
    if (dom.skeletonSvg.hasPointerCapture(event.pointerId)) dom.skeletonSvg.releasePointerCapture(event.pointerId);
  });
  dom.skeletonSvg.addEventListener("pointercancel", () => {
    state.dragJointId = null;
    state.dragPointerStart = null;
  });

  dom.semanticRoleInput.addEventListener("change", updateSelectedLayerSemantic);
  dom.semanticSideSelect.addEventListener("change", updateSelectedLayerSemantic);
  dom.layerDispositionSelect.addEventListener("change", () => {
    const layer = getSelectedLayer();
    if (!layer) return;
    ensureLayerOverride(String(layer.id)).disposition = dom.layerDispositionSelect.value;
    markDirty("图层处理决策已更新");
    renderLayerList();
    renderLayerInspector();
    renderQa();
  });
  dom.selectedLayerVisible.addEventListener("change", (event) => {
    const layer = getSelectedLayer();
    if (layer) setLayerVisibility(String(layer.id), event.target.checked);
  });
  dom.jointXInput.addEventListener("change", updateJointFromInputs);
  dom.jointYInput.addEventListener("change", updateJointFromInputs);
  dom.resetJointBtn.addEventListener("click", resetSelectedJoint);
  dom.overrideNotes.addEventListener("input", (event) => {
    state.notes = event.target.value;
    markDirty("");
  });

  window.addEventListener("keydown", onGlobalKeyDown);
  window.addEventListener("resize", () => {
    if (state.project && Math.abs(state.zoom - state.fitZoom) < 0.002) fitCanvas();
    else applyZoom();
  });
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function init() {
  bindEvents();
  setEditMode("layers", { announceChange: false });
  setToggleButton(dom.toggleCompositeBtn, true);
  setToggleButton(dom.toggleSkeletonBtn, true);
  await loadProjects({ preserveSelection: false });
}

init();
