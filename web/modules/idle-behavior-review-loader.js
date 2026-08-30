"use strict";

import { createIdleBehaviorReviewApi } from "./idle-behavior-review-api.js";

const STORAGE_KEY = "autospine.idle-behavior.last-package.v1";
const SHA = /^[0-9a-f]{64}$/;

export function createIdleBehaviorReviewLoader(elements, dependencies = {}) {
  const api = dependencies.api || createIdleBehaviorReviewApi();
  const storage = dependencies.storage || globalThis.localStorage;
  const search = handoffSearch(dependencies);
  const onLoad = dependencies.onLoad || (() => {});
  const onReset = dependencies.onReset || (() => {});
  let generation = 0;
  let packages = [];
  let skippedCount = 0;
  let mutationLocked = false;
  let activePackageId = null;
  let lockedPackageId = null;

  elements.projectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.reloadButton.addEventListener("click", () => loadSelected("正在重新读取"));

  return { start, reload: loadSelected, currentPackageId, setMutationLocked };

  async function start() {
    const current = ++generation;
    let handoff;
    try { handoff = parseIdleReviewHandoff(search); } catch (error) {
      onReset();
      status(`交接地址无效：${message(error)}。页面不会猜测其他项目。`, "error");
      setBusy(false);
      return false;
    }
    return handoff.kind === "none"
      ? startFromInventory(current) : startDirect(handoff, current);
  }

  async function startDirect(handoff, current) {
    setBusy(true);
    status(handoff.kind === "canvas"
      ? "正在精确读取 P10.2 调整草稿…" : "正在直接读取所选项目…", "warning");
    let entry;
    let draft = null;
    try {
      if (handoff.kind === "canvas") {
        draft = await api.entryWithCanvasAdjustment(
          handoff.packageId, handoff.canvasAdjustmentSha256,
        );
        entry = draft.entry;
      } else entry = await api.entry(handoff.packageId);
      if (current !== generation) return false;
      activePackageId = handoff.packageId;
      await onLoad(entry, {
        canvasAdjustmentDraft: draft,
        packageRow: { package_id: handoff.packageId },
        isCurrent: () => current === generation && activePackageId === handoff.packageId,
      });
      if (current !== generation) return false;
      status("草稿已显示；正在补充项目列表…", "success");
    } catch (error) {
      if (current === generation) {
        activePackageId = null;
        onReset();
        status(`直达项目无法精确载入：${message(error)}。页面不会改用其他项目。`, "error");
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
    try {
      setBusy(true);
      await hydrateInventory(current, handoff.packageId, entry);
    } catch (error) {
      if (current === generation) {
        status(`草稿已显示，但项目列表暂不可用：${message(error)}`, "warning");
      }
    } finally {
      if (current === generation) setBusy(false);
    }
    return current === generation;
  }

  async function startFromInventory(current) {
    setBusy(true);
    status("正在寻找已经完成 P9 的项目…", "warning");
    try {
      const result = await api.list();
      if (current !== generation) return false;
      packages = result.packages;
      skippedCount = result.skipped_count;
      const selected = initialSelection(result.recommended_package_id);
      renderOptions(Boolean(packages.length > 1 || skippedCount > 0) && !selected);
      if (!packages.length) {
        onReset();
        status(emptyMessage(), "error");
        return false;
      }
      if (!selected) {
        elements.projectSelect.value = "";
        onReset();
        status(skippedCount
          ? `有 ${skippedCount} 个版本校验失败，列表可能不完整；请明确选择一个已验证项目。`
          : "发现同一动作的多个有效版本，请先选择要继续的项目。", "warning");
        return false;
      }
      elements.projectSelect.value = selected;
      return loadSelected("已自动选择", current);
    } catch (error) {
      if (current === generation) {
        onReset();
        status(message(error), "error");
      }
      return false;
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  async function hydrateInventory(current, packageId, entry) {
    const result = await api.list();
    if (current !== generation) return;
    packages = result.packages;
    skippedCount = result.skipped_count;
    renderOptions(false);
    const selected = packages.find((row) => row.package_id === packageId);
    const aligned = selected && inventoryMatchesEntry(selected, entry);
    elements.projectSelect.value = aligned ? packageId : "";
    activePackageId = aligned ? packageId : null;
    if (!aligned) onReset();
    status(aligned
      ? (skippedCount ? `当前项目已核对；另有 ${skippedCount} 个版本校验失败。`
        : "项目和草稿已精确核对。无需选择文件或填写 SHA。")
      : "项目清单与直达入口不一致；旧草稿已停用，请重新读取。",
    aligned && !skippedCount ? "success" : "warning");
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
    activePackageId = packageId;
    onReset();
    setBusy(true);
    status(`${prefix}：${selected.project_id} / ${selected.motion_id}…`, "warning");
    try {
      const entry = await api.entry(packageId);
      if (!isCurrent(current, packageId)) return false;
      await onLoad(entry, {
        canvasAdjustmentDraft: null, packageRow: selected,
        isCurrent: () => isCurrent(current, packageId),
      });
      if (!isCurrent(current, packageId)) return false;
      try { storage?.setItem(STORAGE_KEY, packageId); } catch { /* optional */ }
      const skipped = skippedCount ? `；另有 ${skippedCount} 个版本校验失败已跳过` : "";
      status(`已加载候选和人工基线${skipped}。无需选择文件或填写 SHA。`,
        skippedCount ? "warning" : "success");
      return true;
    } catch (error) {
      if (isCurrent(current, packageId)) {
        activePackageId = null;
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
      const peers = packages.filter((peer) => peer.project_id === row.project_id
        && peer.motion_id === row.motion_id && peer.clip_id === row.clip_id)
        .sort((left, right) => left.package_id.localeCompare(right.package_id));
      option.textContent = peers.length > 1
        ? `${label} · 版本 ${peers.indexOf(row) + 1} · ${uniquePrefix(row.package_id, peers)}`
        : label;
      elements.projectSelect.append(option);
    }
  }

  function initialSelection(recommended) {
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* optional */ }
    if (packages.some((row) => row.package_id === saved)) return saved;
    if (skippedCount > 0) return null;
    if (packages.some((row) => row.package_id === recommended)) return recommended;
    return packages.length === 1 ? packages[0].package_id : null;
  }

  function currentPackageId() { return activePackageId; }

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
    return current === generation && activePackageId === packageId
      && elements.projectSelect.value === packageId;
  }

  function setBusy(busy) {
    const blocked = busy || mutationLocked;
    elements.panel.toggleAttribute("aria-busy", blocked);
    elements.projectSelect.disabled = blocked || !packages.length;
    elements.reloadButton.disabled = blocked || !activePackageId;
  }

  function status(text, tone) {
    elements.status.textContent = text;
    elements.status.dataset.tone = tone;
  }

  function emptyMessage() {
    return skippedCount
      ? `发现 ${skippedCount} 个项目，但全部版本校验失败；请先检查动作策略来源。`
      : "尚未发现已采用的 P9 动作。请先完成动作策略发布。";
  }
}

export function parseIdleReviewHandoff(search) {
  const query = new URLSearchParams(search);
  const packages = query.getAll("package_id");
  const adjustments = query.getAll("canvas_adjustment_sha256");
  if (!packages.length && !adjustments.length) return { kind: "none" };
  if (packages.length !== 1 || adjustments.length > 1
      || !SHA.test(packages[0]) || (adjustments.length && !SHA.test(adjustments[0]))) {
    throw new Error("package_id 与调整候选必须是唯一的小写 SHA-256 对");
  }
  return adjustments.length
    ? { kind: "canvas", packageId: packages[0], canvasAdjustmentSha256: adjustments[0] }
    : { kind: "package", packageId: packages[0] };
}

function handoffSearch(dependencies) {
  if (dependencies.locationSearch !== undefined) return dependencies.locationSearch;
  if (dependencies.requestedPackageId !== undefined) {
    return `?package_id=${encodeURIComponent(dependencies.requestedPackageId)}`;
  }
  return globalThis.location?.search ?? "";
}

function inventoryMatchesEntry(row, entry) {
  return ["package_id", "project_id", "motion_id", "clip_id",
    "motion_policy_package_id", "p9_decision_sha256", "status"]
    .every((field) => row[field] === entry.package[field]);
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
