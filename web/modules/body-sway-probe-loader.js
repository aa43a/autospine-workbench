"use strict";

import { createBodySwayProbeApi } from "./body-sway-probe-api.js";
import {
  normalizeProbeInventory, requireInventoryEntryMatch,
} from "./body-sway-probe-contract.js";

const STORAGE_KEY = "autospine.body-sway-probe.last-package.v1";
const SHA = /^[0-9a-f]{64}$/;
const READY = new Set(["probe_ready"]);

export function createBodySwayProbeLoader(elements, dependencies = {}) {
  const api = dependencies.api || createBodySwayProbeApi();
  const storage = dependencies.storage || globalThis.localStorage;
  const search = dependencies.locationSearch ?? globalThis.location?.search ?? "";
  const onLoad = dependencies.onLoad || (() => {});
  const onReset = dependencies.onReset || (() => {});
  let generation = 0;
  let packages = [];
  let skippedCount = 0;

  elements.projectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.reloadButton.addEventListener("click", () => loadSelected("正在重新检查"));

  return Object.freeze({ start, reload: loadSelected, currentPackageId });

  async function start() {
    const current = ++generation;
    const direct = queryPackageId(search);
    if (direct) return startDirect(direct, current);
    return startFromInventory(current);
  }

  async function startDirect(packageId, current) {
    let loadedEntry = null;
    setBusy(true);
    status("正在直接读取 P10.1 交接的结构探针…", "warning");
    try {
      const entry = await api.entry(packageId);
      if (current !== generation) return false;
      loadedEntry = await onLoad(entry, {
        packageRow: { package_id: packageId },
        isCurrent: () => current === generation,
      });
      if (current !== generation) return false;
      status("结构检查已显示；正在补充项目列表…", "success");
    } catch (error) {
      if (current === generation) {
        onReset();
        status(`直达项目不可用：${errorText(error)}；正在读取可用项目…`, "warning");
        return startFromInventory(current);
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
    try {
      setBusy(true);
      await hydrateInventory(current, packageId, loadedEntry);
    } catch (error) {
      if (current === generation) {
        status(`结构检查已显示，但项目列表暂不可用：${errorText(error)}`, "warning");
      }
    } finally {
      if (current === generation) setBusy(false);
    }
    return current === generation;
  }

  async function startFromInventory(current) {
    setBusy(true);
    status("正在查找已完成 P10.1 的项目…", "warning");
    try {
      const inventory = normalizeProbeInventory(await api.list());
      if (current !== generation) return false;
      packages = inventory.packages;
      skippedCount = inventory.skippedCount;
      renderOptions();
      if (!packages.length) {
        onReset();
        status(
          inventory.skippedCount > 0
            ? `发现 ${inventory.skippedCount} 个项目，但全部版本校验失败；请返回 P10.1 检查来源后重试。`
            : "尚未发现身体摆动项目。请先完成 P10.1 设置。",
          "error",
        );
        return false;
      }
      const selected = initialSelection(
        inventory.recommendedPackageId, false, inventory.skippedCount,
      );
      if (!selected) {
        elements.projectSelect.value = "";
        onReset();
        status(
          inventory.skippedCount > 0
            ? `有 ${inventory.skippedCount} 个版本校验失败，列表可能不完整；请明确选择一个已验证项目。`
            : "发现多个可检查版本，请选择一个项目继续。",
          "warning",
        );
        return false;
      }
      elements.projectSelect.value = selected;
      return loadSelected("已自动选择", current);
    } catch (error) {
      if (current === generation) {
        onReset();
        status(errorText(error), "error");
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  async function hydrateInventory(current, selectedId, loadedEntry) {
    const inventory = normalizeProbeInventory(await api.list());
    if (current !== generation) return;
    packages = inventory.packages;
    skippedCount = inventory.skippedCount;
    renderOptions();
    const selected = packages.find((row) => row.package_id === selectedId);
    let aligned = false;
    if (selected && loadedEntry) {
      try {
        requireInventoryEntryMatch(selected, loadedEntry);
        aligned = true;
      } catch { /* exact mismatch is surfaced below */ }
    }
    elements.projectSelect.value = aligned ? selectedId : "";
    if (!aligned) onReset();
    status(
      aligned
        ? (inventory.skippedCount > 0
          ? `当前项目已精确核对；另有 ${inventory.skippedCount} 个版本校验失败。`
          : "结构检查与项目列表已加载。无需选择文件或填写 SHA。")
        : "P10.1 current head 或项目列表已变化；旧结果已停用，请重新读取。",
      aligned && inventory.skippedCount === 0 ? "success" : "warning",
    );
  }

  async function loadSelected(prefix = "正在检查", inherited = null) {
    const current = inherited ?? ++generation;
    const packageId = elements.projectSelect.value;
    const selected = packages.find((row) => row.package_id === packageId);
    if (!selected) return false;
    onReset();
    setBusy(true);
    status(`${prefix}：${selected.project_id} / ${selected.motion_id}…`, "warning");
    try {
      const entry = await api.entry(packageId);
      if (!isCurrent(current, packageId)) return false;
      await onLoad(entry, {
        packageRow: selected,
        isCurrent: () => isCurrent(current, packageId),
      });
      if (!isCurrent(current, packageId)) return false;
      try { storage?.setItem(STORAGE_KEY, packageId); } catch { /* optional */ }
      status("结构检查已读取；文件与精确身份由服务端自动绑定。", "success");
      return true;
    } catch (error) {
      if (isCurrent(current, packageId)) {
        onReset();
        status(`结构检查失败：${errorText(error)}`, "error");
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  function renderOptions() {
    const document = elements.projectSelect.ownerDocument;
    elements.projectSelect.replaceChildren();
    if (packages.length > 1 || skippedCount > 0) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "请选择项目与动作";
      placeholder.disabled = true;
      elements.projectSelect.append(placeholder);
    }
    for (const row of packages) {
      const option = document.createElement("option");
      option.value = row.package_id;
      option.textContent = `${row.project_id} · ${row.motion_id} · ${row.clip_id} · ${statusLabel(row.status)}`;
      elements.projectSelect.append(option);
    }
  }

  function initialSelection(recommended, allowQuery = true, skipped = skippedCount) {
    const query = allowQuery ? queryPackageId(search) : null;
    if (query && packages.some((row) => row.package_id === query)) return query;
    const recommendedRow = packages.find((row) => row.package_id === recommended);
    if (recommendedRow && READY.has(recommendedRow.status)) return recommended;
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* optional */ }
    const savedRow = packages.find((row) => row.package_id === saved);
    if (savedRow && READY.has(savedRow.status)) return saved;
    if (skipped > 0) return null;
    const ready = packages.filter((row) => READY.has(row.status));
    if (ready.length === 1) return ready[0].package_id;
    return packages.length === 1 ? packages[0].package_id : null;
  }

  function currentPackageId() {
    return elements.projectSelect.value || null;
  }

  function isCurrent(current, packageId) {
    return current === generation && elements.projectSelect.value === packageId;
  }

  function setBusy(busy) {
    elements.panel.toggleAttribute("aria-busy", busy);
    elements.projectSelect.disabled = busy || !packages.length;
    elements.reloadButton.disabled = busy || !elements.projectSelect.value;
  }

  function status(text, tone) {
    elements.status.textContent = text;
    elements.status.dataset.tone = tone;
  }
}

export function queryPackageId(search) {
  try {
    const values = new URLSearchParams(search).getAll("package_id");
    if (values.length !== 1) return null;
    const [value] = values;
    return value && SHA.test(value) ? value : null;
  } catch {
    return null;
  }
}

function statusLabel(value) {
  return ({
    probe_ready: "可检查", p10_1_review_required: "需先设置", not_applicable: "不适用",
  })[value] || value;
}

function errorText(error) {
  return error instanceof Error ? error.message : "结构探针加载失败";
}
