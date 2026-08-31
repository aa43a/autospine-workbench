import { createMotionPolicyDraftApi } from "./motion-policy-draft-api.js";
import { createMotionPolicyAutoApi } from "./motion-policy-auto-api.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

const IDS = [
  "draftPolicyPanel", "draftPolicyBadge", "draftProjectSelect", "draftReloadBtn",
  "draftPolicyEvidence", "draftCharacterComposite", "draftPairFacts",
  "draftApproveBtn", "draftPolicyStatus",
];

export function createMotionPolicyDraftController(doc, dependencies = {}) {
  const elements = Object.fromEntries(IDS.map((id) => [id, doc.getElementById(id)]));
  const api = dependencies.api || createMotionPolicyDraftApi();
  const packageApi = dependencies.packageApi || createMotionPolicyAutoApi();
  const packageInventory = dependencies.packageInventory || (() => null);
  const confirmAction = dependencies.confirmAction || ((message) => globalThis.confirm(message));
  const onPromoted = dependencies.onPromoted || (() => null);
  const onCurrentDraft = dependencies.onCurrentDraft || (() => {});
  const onPublishingChange = dependencies.onPublishingChange || (() => {});
  const requestedProject = projectFromSearch(
    dependencies.locationSearch ?? globalThis.location?.search ?? "",
  );
  let drafts = [];
  let detail = null;
  let adopted = false;
  let promotionReceipt = null;
  let generation = 0;

  elements.draftProjectSelect.addEventListener("change", loadSelected);
  elements.draftReloadBtn.addEventListener("click", start);
  elements.draftApproveBtn.addEventListener("click", adopt);

  return { start, clear };

  async function start() {
    const token = ++generation;
    clearEvidence();
    setBusy(true);
    setStatus(elements.draftPolicyStatus, "正在查找当前绑定的待确认草案…", "warning");
    try {
      const knownPackages = packageInventory();
      const [draftList, packageList] = knownPackages
        ? [await api.list(requestedProject), knownPackages]
        : await Promise.all([
          api.list(requestedProject), packageApi.list(requestedProject),
        ]);
      if (token !== generation) return;
      const promoted = new Set(packageList.packages.filter(
        (row) => row.authoring_alignment === "current",
      ).map((row) => `${row.project_id}\0${row.motion_id}`));
      drafts = draftList.drafts.filter((row) =>
        (requestedProject === null || row.project_id === requestedProject) &&
        !promoted.has(`${row.project_id}\0${row.promotion_motion_id}`));
      renderOptions(draftList.recommended_draft_id);
      const current = currentDrafts();
      if (!current.length) {
        elements.draftPolicyPanel.hidden = true;
        return;
      }
      elements.draftPolicyPanel.hidden = false;
      onCurrentDraft();
      if (!elements.draftProjectSelect.value) {
        setStatus(elements.draftPolicyStatus, "发现多个当前草案；请选择一个项目后查看遮挡关系。", "warning");
        return;
      }
      await loadSelected();
    } catch (error) {
      if (token === generation) {
        elements.draftPolicyPanel.hidden = false;
        setStatus(elements.draftPolicyStatus, errorMessage(error), "error");
      }
    } finally {
      if (token === generation) setBusy(false);
    }
  }

  async function loadSelected() {
    const token = ++generation;
    const draftId = elements.draftProjectSelect.value;
    const selected = drafts.find((row) => row.draft_id === draftId);
    clearEvidence();
    if (!selected || selected.authoring_alignment !== "current") return;
    setBusy(true);
    setStatus(elements.draftPolicyStatus, `正在读取 ${selected.project_id} 的遮挡关系…`, "warning");
    try {
      const loaded = await api.detail(draftId, selected.project_id);
      if (token !== generation || elements.draftProjectSelect.value !== draftId) return;
      if (loaded.authoring_alignment !== "current") throw new Error("草案已成为历史版本，请重新生成当前链草案");
      detail = loaded;
      renderEvidence(loaded);
      elements.draftApproveBtn.disabled = false;
      elements.draftPolicyBadge.textContent = "1 次确认";
      setStatus(elements.draftPolicyStatus, "来源和身份已自动核验；请只确认画面中的前后关系。", "success");
    } catch (error) {
      if (token === generation) setStatus(elements.draftPolicyStatus, errorMessage(error), "error");
    } finally {
      if (token === generation) setBusy(false);
    }
  }

  async function adopt() {
    if (!detail || elements.draftApproveBtn.disabled) return;
    if (promotionReceipt) {
      await resumePromotedPackage(promotionReceipt);
      return;
    }
    const pair = detail.semantic_summary.pairs[0];
    const front = pair.setup_front_slot;
    const other = pair.slots.find((slot) => slot.slot_id !== front)?.slot_id || "另一图层";
    if (!confirmAction(`确认当前 setup 中“${front}”位于“${other}”前方，并采用该草案绑定的系统防抖参数生成 Depth 候选？`)) return;
    const token = ++generation;
    onPublishingChange(true);
    setBusy(true);
    elements.draftPolicyBadge.textContent = "正在生成";
    setStatus(elements.draftPolicyStatus, "正在重放当前链、生成 Depth candidates 并执行精确复验…", "warning");
    try {
      promotionReceipt = await api.adopt(detail);
      if (token !== generation) return;
      await loadPromotedPackage(promotionReceipt, token);
    } catch (error) {
      if (token === generation) {
        if (promotionReceipt) {
          elements.draftPolicyBadge.textContent = "已生成，待同步";
          elements.draftApproveBtn.textContent = "重新同步已生成候选";
          setStatus(elements.draftPolicyStatus,
            `正式 policy 与候选已经提交，但自动载入失败：${errorMessage(error)}。可安全重试同步，不会再次提交决定。`,
            "error");
        } else {
          elements.draftPolicyBadge.textContent = "未生成";
          setStatus(elements.draftPolicyStatus, errorMessage(error), "error");
        }
      }
    } finally {
      onPublishingChange(false);
      if (token === generation) setBusy(false);
    }
  }

  async function resumePromotedPackage(receipt) {
    const token = ++generation;
    onPublishingChange(true);
    setBusy(true);
    elements.draftPolicyBadge.textContent = "正在同步";
    setStatus(elements.draftPolicyStatus, "正在读回已经生成的 exact P9 复核包…", "warning");
    try {
      await loadPromotedPackage(receipt, token);
    } catch (error) {
      if (token === generation) {
        elements.draftPolicyBadge.textContent = "已生成，待同步";
        setStatus(elements.draftPolicyStatus,
          `已生成的候选仍未能自动载入：${errorMessage(error)}。本次没有重复提交决定。`,
          "error");
      }
    } finally {
      onPublishingChange(false);
      if (token === generation) setBusy(false);
    }
  }

  async function loadPromotedPackage(receipt, token) {
    const packageDetail = await packageApi.package(
      receipt.package_id, detail.project_id,
    );
    if (token !== generation) return;
    if (packageDetail.project_id !== detail.project_id ||
        packageDetail.motion_id !== receipt.motion_id ||
        packageDetail.authoring_alignment !== "current") {
      throw new Error("已生成复核包与当前项目身份不一致");
    }
    setStatus(elements.draftPolicyStatus, "正式 policy 与 Depth 候选已生成；正在进入 P9 视觉采用。", "success");
    await onPromoted(packageDetail);
    if (token !== generation) return;
    elements.draftApproveBtn.disabled = true;
    adopted = true;
    elements.draftApproveBtn.textContent = "已生成候选";
    elements.draftPolicyBadge.textContent = receipt.reused ? "已复验" : "已生成";
  }

  function renderOptions(recommended) {
    elements.draftProjectSelect.replaceChildren();
    const current = currentDrafts();
    const recommendedCurrent = current.find((row) => row.draft_id === recommended)?.draft_id;
    const selected = recommendedCurrent || (current.length === 1 ? current[0].draft_id : "");
    if (!selected && current.length > 1) {
      const placeholder = doc.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "请选择待确认项目";
      placeholder.disabled = true;
      elements.draftProjectSelect.append(placeholder);
    }
    for (const row of drafts) {
      const option = doc.createElement("option");
      option.value = row.draft_id;
      option.textContent = `${row.project_id} · ${row.clip_id} · ${row.pair_count} 组遮挡关系` +
        (row.authoring_alignment === "historical" ? "（历史，只读）" : "");
      option.disabled = row.authoring_alignment !== "current";
      elements.draftProjectSelect.append(option);
    }
    elements.draftProjectSelect.value = selected;
  }

  function renderEvidence(value) {
    elements.draftCharacterComposite.src = `/api/projects/${encodeURIComponent(value.project_id)}/composite`;
    elements.draftCharacterComposite.alt = `${value.project_id} 的角色合成图`;
    elements.draftPairFacts.replaceChildren();
    for (const pair of value.semantic_summary.pairs) {
      for (const slot of pair.slots) {
        addFact(
          slot.slot_id,
          `语义角色：${slot.depth_role}`,
          false,
          `/api/projects/${encodeURIComponent(value.project_id)}/layers/` +
            `${encodeURIComponent(slot.slot_id)}/image`,
          `${slot.slot_id} 的透明独立图层`,
        );
      }
      const front = pair.slots.find((slot) => slot.slot_id === pair.setup_front_slot);
      addFact("当前 setup 前景", `${pair.setup_front_slot} · ${front?.depth_role || "未知角色"}`, true);
    }
    elements.draftPolicyEvidence.hidden = false;
  }

  function addFact(title, value, front = false, imageSrc = null, imageAlt = "") {
    const card = doc.createElement("div");
    card.className = `draft-pair-fact${front ? " draft-front-fact" : ""}`;
    const strong = doc.createElement("strong");
    const span = doc.createElement("span");
    strong.textContent = title;
    span.textContent = value;
    card.append(strong, span);
    if (imageSrc) {
      const image = doc.createElement("img");
      image.className = "draft-slot-image";
      image.src = imageSrc;
      image.alt = imageAlt;
      image.loading = "lazy";
      card.append(image);
    }
    elements.draftPairFacts.append(card);
  }

  function currentDrafts() {
    return drafts.filter((row) => row.authoring_alignment === "current");
  }

  function clearEvidence() {
    detail = null;
    adopted = false;
    promotionReceipt = null;
    elements.draftPolicyEvidence.hidden = true;
    elements.draftPairFacts.replaceChildren();
    elements.draftCharacterComposite.removeAttribute("src");
    elements.draftApproveBtn.disabled = true;
    elements.draftApproveBtn.textContent = "确认前后关系并生成候选";
    elements.draftPolicyBadge.textContent = "等待人工确认";
  }

  function clear() {
    generation += 1;
    drafts = [];
    clearEvidence();
    elements.draftPolicyPanel.hidden = true;
    setBusy(false);
  }

  function setBusy(value) {
    elements.draftPolicyPanel.toggleAttribute("aria-busy", value);
    elements.draftProjectSelect.disabled = value || currentDrafts().length === 0;
    elements.draftReloadBtn.disabled = value;
    if (value) elements.draftApproveBtn.disabled = true;
    else if (detail && !adopted) elements.draftApproveBtn.disabled = false;
  }
}

function projectFromSearch(search) {
  const params = new URLSearchParams(String(search || ""));
  const value = params.get("project") ?? params.get("project_id");
  return value === null || value === "" ? null : value;
}
