import { createMotionPolicyAutoApi } from "./motion-policy-auto-api.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

const STORAGE_KEY = "autospine.motion-policy.last-project.v1";

export function createMotionPolicyAutoController(elements, dependencies = {}) {
  const api = dependencies.api || createMotionPolicyAutoApi();
  const storage = dependencies.storage || globalThis.localStorage;
  const onLoad = dependencies.onLoad;
  const onReset = dependencies.onReset || (() => {});
  const onAssistChange = dependencies.onAssistChange || (() => {});
  let generation = 0;
  let mode = "auto";
  let packages = [];
  let skippedCount = 0;
  const completed = new Set();

  elements.autoProjectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.autoReloadProject.addEventListener("click", () => loadSelected("正在重新加载"));
  elements.autoApplySafe.addEventListener("change", () => {
    onAssistChange(elements.autoApplySafe.checked);
    setStatus(elements.autoLoadStatus, elements.autoApplySafe.checked
      ? "时间轴自动采用安全建议已开启。"
      : "时间轴现在只预览，不会自动采用候选。", "warning");
  });

  return { start, reload: loadSelected, markCompleted, continueTo, enterExpertMode };

  async function start() {
    mode = "auto";
    const current = ++generation;
    setBusy(true);
    setStatus(elements.autoLoadStatus, "正在寻找可直接使用的项目…", "warning");
    try {
      const result = await api.list();
      if (current !== generation) return;
      packages = result.packages;
      skippedCount = result.skipped_count ?? 0;
      renderOptions(result.recommended_package_id);
      if (!packages.length) {
        elements.expertInputs.open = true;
        const skipped = skippedCount > 0 ? `；${skippedCount} 个复核包校验失败` : "";
        throw new Error(`没有发现完整的自动复核包${skipped}；已展开专业输入。`);
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
    const applySafe = elements.autoApplySafe.checked;
    onReset();
    setBusy(true);
    setStatus(elements.autoLoadStatus, `${prefix}：${selected.project_id} / ${selected.motion_id}…`, "warning");
    try {
      const detail = await api.package(packageId);
      if (current !== generation || elements.autoProjectSelect.value !== packageId) return;
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

  function renderOptions(recommended) {
    elements.autoProjectSelect.replaceChildren();
    for (const row of packages) {
      const option = elements.autoProjectSelect.ownerDocument.createElement("option");
      option.value = row.package_id;
      option.dataset.baseLabel = `${row.project_id} · ${row.motion_id} · ${row.inventory.total_count} 项`;
      option.textContent = optionLabel(option.dataset.baseLabel, row.package_id);
      elements.autoProjectSelect.append(option);
    }
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* storage is optional */ }
    const selected = packages.some((row) => row.package_id === saved) ? saved : recommended;
    elements.autoProjectSelect.value = selected || packages[0]?.package_id || "";
  }

  function markCompleted(packageId) {
    const current = packages.find((row) => row.package_id === packageId);
    if (!current) return null;
    completed.add(packageId);
    for (const option of elements.autoProjectSelect.children) {
      option.textContent = optionLabel(option.dataset.baseLabel, option.value);
    }
    const start = packages.indexOf(current);
    for (let offset = 1; offset < packages.length; offset += 1) {
      const candidate = packages[(start + offset) % packages.length];
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
    if (!packages.some((row) => row.package_id === packageId)) {
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

  function optionLabel(base, packageId) {
    return completed.has(packageId) ? `${base}（本轮已完成）` : base;
  }

  function setBusy(busy) {
    elements.autoProjectSelect.disabled = busy || packages.length === 0;
    elements.autoReloadProject.disabled = busy || !elements.autoProjectSelect.value;
    elements.autoApplySafe.disabled = busy;
    elements.expertInputs.inert = busy;
    elements.autoStartPanel.toggleAttribute("aria-busy", busy);
  }
}
