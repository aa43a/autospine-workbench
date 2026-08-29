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
  let packages = [];

  elements.autoProjectSelect.addEventListener("change", () => loadSelected("项目已切换"));
  elements.autoReloadProject.addEventListener("click", () => loadSelected("正在重新加载"));
  elements.autoApplySafe.addEventListener("change", () => {
    onAssistChange(elements.autoApplySafe.checked);
    setStatus(elements.autoLoadStatus, elements.autoApplySafe.checked
      ? "时间轴自动采用安全建议已开启。"
      : "时间轴现在只预览，不会自动采用候选。", "warning");
  });

  return { start, reload: loadSelected };

  async function start() {
    const current = ++generation;
    setBusy(true);
    setStatus(elements.autoLoadStatus, "正在寻找可直接使用的项目…", "warning");
    try {
      const result = await api.list();
      if (current !== generation) return;
      packages = result.packages;
      renderOptions(result.recommended_package_id);
      if (!packages.length) {
        elements.expertInputs.open = true;
        throw new Error("没有发现完整的自动复核包；已展开专业输入。 ");
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
    const current = inheritedGeneration ?? ++generation;
    const packageId = elements.autoProjectSelect.value;
    const selected = packages.find((row) => row.package_id === packageId);
    if (!selected) return;
    onReset();
    setBusy(true);
    setStatus(elements.autoLoadStatus, `${prefix}：${selected.project_id} / ${selected.motion_id}…`, "warning");
    try {
      const detail = await api.package(packageId);
      if (current !== generation || elements.autoProjectSelect.value !== packageId) return;
      await onLoad(detail, {
        applySafe: elements.autoApplySafe.checked,
        isCurrent: () => current === generation &&
          elements.autoProjectSelect.value === packageId,
      });
      if (current !== generation || elements.autoProjectSelect.value !== packageId) return;
      try { storage?.setItem(STORAGE_KEY, packageId); } catch { /* storage is optional */ }
      setStatus(elements.autoLoadStatus,
        `${detail.project_id} 已自动完成文件、SHA 与来源校验；可拖动时间轴或一键采用安全建议。`, "success");
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
      option.textContent = `${row.project_id} · ${row.motion_id} · ${row.inventory.total_count} 项`;
      elements.autoProjectSelect.append(option);
    }
    let saved = null;
    try { saved = storage?.getItem(STORAGE_KEY); } catch { /* storage is optional */ }
    const selected = packages.some((row) => row.package_id === saved) ? saved : recommended;
    elements.autoProjectSelect.value = selected || packages[0]?.package_id || "";
  }

  function setBusy(busy) {
    elements.autoProjectSelect.disabled = busy || packages.length === 0;
    elements.autoReloadProject.disabled = busy || !elements.autoProjectSelect.value;
    elements.autoStartPanel.toggleAttribute("aria-busy", busy);
  }
}
