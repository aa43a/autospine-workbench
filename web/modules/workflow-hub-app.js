import {
  catalogStats, filterEntries, groupEntries, validateCatalog,
} from "./workflow-hub-model.js";
import { renderGroups, renderLoadError } from "./workflow-hub-view.js";

const elements = {
  results: document.querySelector("#workflowResults"),
  resultStatus: document.querySelector("#resultStatus"),
  liveRegion: document.querySelector("#liveRegion"),
  search: document.querySelector("#searchInput"),
  stage: document.querySelector("#stageFilter"),
  status: document.querySelector("#statusFilter"),
  kind: document.querySelector("#kindFilter"),
  reset: document.querySelector("#resetFilters"),
  currentStage: document.querySelector("#currentStage"),
  total: document.querySelector("#totalCount"),
  available: document.querySelector("#availableCount"),
  external: document.querySelector("#externalCount"),
  planned: document.querySelector("#plannedCount"),
};

let catalog = null;

function announce(message) {
  elements.liveRegion.textContent = "";
  window.setTimeout(() => { elements.liveRegion.textContent = message; }, 0);
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

function filters() {
  return {
    query: elements.search.value,
    stage: elements.stage.value,
    status: elements.status.value,
    kind: elements.kind.value,
  };
}

function render() {
  if (!catalog) return;
  const matching = filterEntries(catalog.entries, filters());
  const groups = groupEntries(matching, catalog.stages);
  renderGroups(elements.results, groups, announce, copyText);
  elements.resultStatus.textContent = `显示 ${matching.length} / ${catalog.entries.length} 项，分布于 ${groups.length} 个阶段。`;
}

function populateStages(stages) {
  for (const stage of stages) {
    const option = document.createElement("option");
    option.value = stage.id;
    option.textContent = `${stage.id} · ${stage.label}`;
    elements.stage.append(option);
  }
}

function renderSummary(value) {
  const stats = catalogStats(value.entries);
  elements.currentStage.textContent = value.current_stage;
  elements.total.textContent = String(stats.total);
  elements.available.textContent = String(stats.available);
  elements.external.textContent = String(stats.external);
  elements.planned.textContent = String(stats.planned);
}

function resetFilters() {
  elements.search.value = "";
  elements.stage.value = "all";
  elements.status.value = "all";
  elements.kind.value = "all";
  render();
  elements.search.focus();
}

async function start() {
  try {
    const response = await fetch("./workflow-catalog.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    catalog = validateCatalog(await response.json());
    populateStages(catalog.stages);
    renderSummary(catalog);
    render();
  } catch (error) {
    renderLoadError(elements.results, error instanceof Error ? error.message : String(error));
    elements.resultStatus.textContent = "目录不可用。";
  }
}

for (const control of [elements.search, elements.stage, elements.status, elements.kind]) {
  control.addEventListener("input", render);
  control.addEventListener("change", render);
}
elements.reset.addEventListener("click", resetFilters);

start();
