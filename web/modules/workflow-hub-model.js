export const STAGE_ORDER = Object.freeze([
  "P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10",
]);

export const STATUS_LABELS = Object.freeze({
  available: "可直接使用",
  external_required: "需要外部前置",
  planned: "计划中",
});

export const KIND_LABELS = Object.freeze({
  page: "操作页面",
  cli: "CLI 命令",
  planned: "规划能力",
});

const VALID_KINDS = new Set(Object.keys(KIND_LABELS));
const VALID_STATUSES = new Set(Object.keys(STATUS_LABELS));
const VALID_STAGES = new Set(STAGE_ORDER);

export function commandHelp(entry) {
  return entry.kind === "cli"
    ? `python -B -m autospine_workbench ${entry.command} --help`
    : "";
}

export function validateCatalog(catalog) {
  if (!catalog || typeof catalog !== "object") throw new TypeError("目录必须是对象");
  if (!Array.isArray(catalog.entries)) throw new TypeError("目录缺少 entries 数组");
  if (!Array.isArray(catalog.stages)) throw new TypeError("目录缺少 stages 数组");
  const ids = new Set();
  for (const entry of catalog.entries) {
    for (const field of ["id", "stage", "title", "summary", "kind", "status", "doc"]) {
      if (typeof entry[field] !== "string" || entry[field].trim() === "") {
        throw new TypeError(`${entry.id || "未知条目"} 缺少 ${field}`);
      }
    }
    if (ids.has(entry.id)) throw new TypeError(`重复条目 ID：${entry.id}`);
    if (!VALID_STAGES.has(entry.stage)) throw new TypeError(`${entry.id} 的阶段无效`);
    if (!VALID_KINDS.has(entry.kind)) throw new TypeError(`${entry.id} 的类型无效`);
    if (!VALID_STATUSES.has(entry.status)) throw new TypeError(`${entry.id} 的状态无效`);
    if (entry.kind === "cli" && !entry.command) throw new TypeError(`${entry.id} 缺少 command`);
    if (entry.kind === "page" && !entry.href) throw new TypeError(`${entry.id} 缺少 href`);
    ids.add(entry.id);
  }
  return catalog;
}

function normalized(value) {
  return String(value || "").normalize("NFKC").toLocaleLowerCase("zh-CN").trim();
}

export function filterEntries(entries, filters = {}) {
  const query = normalized(filters.query);
  return entries.filter((entry) => {
    if (filters.stage && filters.stage !== "all" && entry.stage !== filters.stage) return false;
    if (filters.status && filters.status !== "all" && entry.status !== filters.status) return false;
    if (filters.kind && filters.kind !== "all" && entry.kind !== filters.kind) return false;
    if (!query) return true;
    const searchable = normalized([
      entry.title, entry.summary, entry.stage, entry.kind, entry.status,
      entry.command, entry.doc, STATUS_LABELS[entry.status], KIND_LABELS[entry.kind],
    ].join(" "));
    return searchable.includes(query);
  });
}

export function groupEntries(entries, stageDefinitions) {
  const labels = new Map(stageDefinitions.map((stage) => [stage.id, stage.label]));
  return STAGE_ORDER.map((stage) => ({
    stage,
    label: labels.get(stage) || stage,
    entries: entries.filter((entry) => entry.stage === stage),
  })).filter((group) => group.entries.length > 0);
}

export function catalogStats(entries) {
  return {
    total: entries.length,
    available: entries.filter((entry) => entry.status === "available").length,
    external: entries.filter((entry) => entry.status === "external_required").length,
    planned: entries.filter((entry) => entry.status === "planned").length,
  };
}
