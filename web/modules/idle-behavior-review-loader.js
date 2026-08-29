"use strict";

import { createIdleBehaviorReviewApi } from "./idle-behavior-review-api.js";

const STORAGE_KEY = "autospine.idle-behavior.last-package.v1";

export function createIdleBehaviorReviewLoader(elements, dependencies = {}) {
  const api = dependencies.api || createIdleBehaviorReviewApi();
  const storage = dependencies.storage || globalThis.localStorage;
  const onLoad = dependencies.onLoad || (() => {});
  const onReset = dependencies.onReset || (() => {});
  let generation = 0;
  let packages = [];
  let skippedCount = 0;
  let mutationLocked = false;
  let lockedPackageId = null;

  elements.projectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.reloadButton.addEventListener("click", () => loadSelected("正在重新读取"));

  return {
    start, reload: loadSelected, currentPackageId, setMutationLocked,
  };

  async function start() {
    const current = ++generation;
    setBusy(true);
    status("正在寻找已经完成 P9 的项目…", "warning");
    try {
      const result = await api.list();
      if (current !== generation) return;
      packages = result.packages;
      skippedCount = result.skipped_count;
      const selected = initialSelection(result.recommended_package_id);
      renderOptions(Boolean(packages.length > 1 && !selected));
      if (!packages.length) {
        onReset();
        status(emptyMessage(), "error");
        return;
      }
      if (!selected) {
        elements.projectSelect.value = "";
        onReset();
        status("发现同一动作的多个有效版本，请先选择要继续的项目。", "warning");
        return;
      }
      elements.projectSelect.value = selected;
      await loadSelected("已自动选择", current);
    } catch (error) {
      if (current === generation) {
        onReset();
        status(message(error), "error");
      }
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  async function loadSelected(prefix = "正在加载", inherited = null) {
    if (mutationLocked) {
      if (lockedPackageId) elements.projectSelect.value = lockedPackageId;
      return false;
    }
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
      await onLoad(entry, { isCurrent: () => isCurrent(current, packageId) });
      if (!isCurrent(current, packageId)) return false;
      try { storage?.setItem(STORAGE_KEY, packageId); } catch { /* optional */ }
      const skipped = skippedCount
        ? `；另有 ${skippedCount} 个版本因校验失败已跳过` : "";
      status(`已加载候选和人工基线${skipped}。无需选择文件或填写 SHA。`,
        skippedCount ? "warning" : "success");
      return true;
    } catch (error) {
      if (isCurrent(current, packageId)) {
        onReset();
        status(message(error), "error");
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  function renderOptions(requireChoice) {
    elements.projectSelect.replaceChildren();
    if (requireChoice) {
      const placeholder = elements.projectSelect.ownerDocument.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "请选择一个精确动作版本";
      placeholder.disabled = true;
      elements.projectSelect.append(placeholder);
    }
    for (const row of packages) {
      const option = elements.projectSelect.ownerDocument.createElement("option");
      option.value = row.package_id;
      const label = `${row.project_id} · ${row.motion_id} · ${row.clip_id}`;
      const ambiguous = packages.some((peer) => peer !== row
        && peer.project_id === row.project_id
        && peer.motion_id === row.motion_id && peer.clip_id === row.clip_id);
      const peers = packages.filter((peer) => peer.project_id === row.project_id
        && peer.motion_id === row.motion_id && peer.clip_id === row.clip_id)
        .sort((left, right) => left.package_id.localeCompare(right.package_id));
      option.textContent = ambiguous
        ? `${label} · 版本 ${peers.indexOf(row) + 1} · ${uniquePrefix(row.package_id, peers)}`
        : label;
      elements.projectSelect.append(option);
    }
  }

  function initialSelection(recommended) {
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* optional */ }
    if (packages.some((row) => row.package_id === saved)) return saved;
    if (packages.some((row) => row.package_id === recommended)) return recommended;
    return packages.length === 1 ? packages[0].package_id : null;
  }

  function currentPackageId() {
    return elements.projectSelect.value || null;
  }

  function setMutationLocked(locked) {
    if (locked && !mutationLocked) lockedPackageId = currentPackageId();
    if (!locked && mutationLocked && lockedPackageId) {
      elements.projectSelect.value = lockedPackageId;
    }
    mutationLocked = Boolean(locked);
    if (!mutationLocked) lockedPackageId = null;
    setBusy(false);
  }

  function isCurrent(current, packageId) {
    return current === generation && elements.projectSelect.value === packageId;
  }

  function setBusy(busy) {
    const blocked = busy || mutationLocked;
    elements.panel.toggleAttribute("aria-busy", blocked);
    elements.projectSelect.disabled = blocked || !packages.length;
    elements.reloadButton.disabled = blocked || !elements.projectSelect.value;
  }

  function status(text, tone) {
    elements.status.textContent = text;
    elements.status.dataset.tone = tone;
  }

  function emptyMessage() {
    const suffix = skippedCount ? `；${skippedCount} 个版本未通过校验` : "";
    return `尚未发现已采用的 P9 动作${suffix}。请先完成动作策略发布。`;
  }
}

function message(error) {
  return error instanceof Error ? error.message : "P10 自动加载失败";
}

function uniquePrefix(packageId, peers) {
  for (let length = 8; length <= packageId.length; length += 1) {
    const prefix = packageId.slice(0, length);
    if (peers.every((peer) => peer.package_id === packageId
        || !peer.package_id.startsWith(prefix))) return prefix;
  }
  return packageId;
}
