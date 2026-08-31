import { createMotionPolicyAutoApi } from "./motion-policy-auto-api.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

const STORAGE_KEY = "autospine.motion-policy.last-project.v1";

export function createMotionPolicyAutoController(elements, dependencies = {}) {
  const api = dependencies.api || createMotionPolicyAutoApi();
  const storage = dependencies.storage || globalThis.localStorage;
  const onLoad = dependencies.onLoad;
  const onReset = dependencies.onReset || (() => {});
  const onAssistChange = dependencies.onAssistChange || (() => {});
  const requestedProject = projectFromSearch(
    dependencies.locationSearch ?? globalThis.location?.search ?? "",
  );
  let generation = 0;
  let mode = "auto";
  let packages = [];
  let skippedCount = 0;
  let inventoryReady = false;
  const completed = new Set();

  elements.autoProjectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.autoReloadProject.addEventListener("click", () => loadSelected("正在重新加载"));
  elements.autoApplySafe.addEventListener("change", () => {
    onAssistChange(elements.autoApplySafe.checked);
    setStatus(elements.autoLoadStatus, elements.autoApplySafe.checked
      ? "时间轴自动采用安全建议已开启。"
      : "时间轴现在只预览，不会自动采用候选。", "warning");
  });

  return {
    start, reload: loadSelected, loadPromoted,
    packageInventory, markCompleted, continueTo, enterExpertMode,
    showPendingDraft,
  };

  async function start() {
    mode = "auto";
    const current = ++generation;
    setBusy(true);
    setStatus(elements.autoLoadStatus, "正在寻找可直接使用的项目…", "warning");
    try {
      const result = await api.list(requestedProject);
      if (current !== generation) return;
      inventoryReady = true;
      packages = requestedProject === null
        ? result.packages
        : result.packages.filter((row) => row.project_id === requestedProject);
      skippedCount = result.skipped_count ?? 0;
      renderOptions(result.recommended_package_id);
      if (!packages.length) {
        if (requestedProject !== null) {
          onReset();
          setStatus(elements.autoLoadStatus,
            `项目 ${requestedProject} 尚无当前绑定的 P9 复核包；不会切换到其他项目。`,
            "warning");
          return;
        }
        elements.expertInputs.open = true;
        const skipped = skippedCount > 0 ? `；${skippedCount} 个复核包校验失败` : "";
        throw new Error(`没有发现完整的自动复核包${skipped}；已展开专业输入。`);
      }
      if (!currentPackages().length) {
        onReset();
        const scope = requestedProject ? `项目 ${requestedProject} ` : "";
        setStatus(elements.autoLoadStatus,
          `${scope}只发现历史版本；请先为当前绑定生成 P9 复核包。`, "warning");
        return;
      }
      if (!elements.autoProjectSelect.value) {
        onReset();
        setStatus(elements.autoLoadStatus,
          "发现多个当前绑定的 P9 复核包；请选择角色与动作，选择后才会加载和预检。",
          "warning");
        return;
      }
      await loadSelected("已自动选择可用项目", current);
    } catch (error) {
      if (current === generation) {
        onReset();
        setStatus(elements.autoLoadStatus, errorMessage(error), "error");
      }
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  async function loadSelected(prefix = "正在加载", inheritedGeneration = null) {
    mode = "auto";
    const current = inheritedGeneration ?? ++generation;
    const packageId = elements.autoProjectSelect.value;
    const selected = packages.find((row) => row.package_id === packageId);
    if (!selected) return;
    if (selected.authoring_alignment !== "current") {
      onReset();
      setStatus(elements.autoLoadStatus,
        "该复核包属于历史绑定，仅供审计；请先为当前绑定生成 P9 复核包。", "warning");
      return;
    }
    const applySafe = elements.autoApplySafe.checked;
    onReset();
    setBusy(true);
    setStatus(elements.autoLoadStatus, `${prefix}：${selected.project_id} / ${selected.motion_id}…`, "warning");
    try {
      const detail = await api.package(packageId, selected.project_id);
      if (current !== generation || elements.autoProjectSelect.value !== packageId) return;
      if (detail.authoring_alignment !== "current") {
        throw new Error("复核包在加载期间已成为历史绑定；未进入预检或采用。");
      }
      await onLoad(detail, {
        applySafe,
        isCurrent: () => current === generation &&
          elements.autoProjectSelect.value === packageId,
      });
      if (current !== generation || elements.autoProjectSelect.value !== packageId) return;
      try { storage?.setItem(STORAGE_KEY, packageId); } catch { /* storage is optional */ }
      const skipped = skippedCount > 0
        ? `；另有 ${skippedCount} 个复核包无法自动加载，请展开专业输入排查`
        : "";
      setStatus(elements.autoLoadStatus,
        `${detail.project_id} 已自动完成文件、SHA 与来源校验；可拖动时间轴或一键采用安全建议${skipped}。`,
        skippedCount > 0 ? "warning" : "success");
    } catch (error) {
      if (current === generation) {
        onReset();
        setStatus(elements.autoLoadStatus, errorMessage(error), "error");
      }
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  async function loadPromoted(packageDetail) {
    mode = "auto";
    const current = ++generation;
    onReset();
    setBusy(true);
    setStatus(elements.autoLoadStatus, "正在同步新生成的 P9 复核包…", "warning");
    try {
      const result = await api.list(requestedProject);
      if (current !== generation) return false;
      inventoryReady = true;
      packages = requestedProject === null
        ? result.packages
        : result.packages.filter((row) => row.project_id === requestedProject);
      skippedCount = result.skipped_count ?? 0;
      const row = packages.find((item) => item.package_id === packageDetail?.package_id);
      if (!row || row.authoring_alignment !== "current" ||
          row.project_id !== packageDetail.project_id ||
          row.motion_id !== packageDetail.motion_id) {
        throw new Error("新生成的 P9 复核包未出现在当前项目清单中");
      }
      renderOptions(result.recommended_package_id);
      elements.autoProjectSelect.value = row.package_id;
      const applySafe = elements.autoApplySafe.checked;
      await onLoad(packageDetail, {
        applySafe,
        isCurrent: () => current === generation &&
          elements.autoProjectSelect.value === row.package_id,
      });
      if (current !== generation) return false;
      try { storage?.setItem(STORAGE_KEY, row.package_id); } catch { /* optional */ }
      setStatus(elements.autoLoadStatus,
        `${row.project_id} 的正式 policy 与候选已自动绑定；可直接浏览动作并采用安全建议。`,
        "success");
      return true;
    } catch (error) {
      if (current === generation) setStatus(elements.autoLoadStatus, errorMessage(error), "error");
      throw error;
    } finally {
      if (current === generation) setBusy(false);
    }
  }

  function renderOptions(recommended) {
    elements.autoProjectSelect.replaceChildren();
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* storage is optional */ }
    const current = currentPackages();
    const savedCurrent = current.find((row) => row.package_id === saved)?.package_id;
    const recommendedCurrent = current.find((row) => row.package_id === recommended)?.package_id;
    const selected = savedCurrent || recommendedCurrent ||
      (current.length === 1 ? current[0].package_id : "");
    if (!selected && current.length > 1) {
      const placeholder = elements.autoProjectSelect.ownerDocument.createElement("option");
      placeholder.value = "";
      placeholder.disabled = true;
      placeholder.dataset.baseLabel = "请选择角色与动作";
      placeholder.textContent = "请选择角色与动作";
      elements.autoProjectSelect.append(placeholder);
    }
    for (const row of packages) {
      const option = elements.autoProjectSelect.ownerDocument.createElement("option");
      option.value = row.package_id;
      option.dataset.baseLabel = `${row.project_id} · ${row.motion_id} · ${row.inventory.total_count} 项`;
      option.disabled = row.authoring_alignment !== "current";
      option.textContent = optionLabel(option.dataset.baseLabel, row.package_id);
      elements.autoProjectSelect.append(option);
    }
    elements.autoProjectSelect.value = selected;
  }

  function packageInventory() {
    if (!inventoryReady) return null;
    return { packages: packages.map((row) => ({ ...row })) };
  }

  function markCompleted(packageId) {
    const eligible = currentPackages();
    const current = eligible.find((row) => row.package_id === packageId);
    if (!current) return null;
    completed.add(packageId);
    for (const option of elements.autoProjectSelect.children) {
      option.textContent = optionLabel(option.dataset.baseLabel, option.value);
    }
    const start = eligible.indexOf(current);
    for (let offset = 1; offset < eligible.length; offset += 1) {
      const candidate = eligible[(start + offset) % eligible.length];
      if (!completed.has(candidate.package_id)) {
        return {
          packageId: candidate.package_id,
          projectId: candidate.project_id,
          motionId: candidate.motion_id,
        };
      }
    }
    return null;
  }

  async function continueTo(packageId) {
    if (!currentPackages().some((row) => row.package_id === packageId)) {
      throw new Error("下一个自动复核包已不可用，请重新加载项目清单");
    }
    elements.autoProjectSelect.value = packageId;
    await loadSelected("正在继续下一个本轮未处理样本");
    return true;
  }

  function enterExpertMode() {
    if (mode === "expert") return;
    mode = "expert";
    generation += 1;
    onReset();
    setBusy(false);
    setStatus(elements.autoLoadStatus,
      "已切换到专业模式；较早的自动加载结果不会覆盖当前输入。", "warning");
  }

  function showPendingDraft() {
    if (mode !== "auto") return;
    elements.expertInputs.open = false;
    const scope = requestedProject ? `项目 ${requestedProject} ` : "";
    setStatus(elements.autoLoadStatus,
      `${scope}尚无当前正式 P9 复核包；请先确认下方待处理的遮挡草案。`,
      "warning");
  }

  function optionLabel(base, packageId) {
    const row = packages.find((candidate) => candidate.package_id === packageId);
    if (row?.authoring_alignment === "historical") return `${base}（历史版本，只读）`;
    return completed.has(packageId) ? `${base}（本轮已完成）` : base;
  }

  function currentPackages() {
    return packages.filter((row) => row.authoring_alignment === "current");
  }

  function setBusy(busy) {
    elements.autoProjectSelect.disabled = busy || currentPackages().length === 0;
    elements.autoReloadProject.disabled = busy || !elements.autoProjectSelect.value;
    elements.autoApplySafe.disabled = busy;
    elements.expertInputs.inert = busy;
    elements.autoStartPanel.toggleAttribute("aria-busy", busy);
  }
}

function projectFromSearch(search) {
  const params = new URLSearchParams(String(search || ""));
  const value = params.get("project") ?? params.get("project_id");
  return value === null || value === "" ? null : value;
}
