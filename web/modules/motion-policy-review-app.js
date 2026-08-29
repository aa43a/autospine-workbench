import { authorizeCandidateInventory } from "./motion-policy-candidate-preflight.js";
import { readCandidateFile } from "./motion-policy-candidate-files.js";
import { handleCandidateKeyboard } from "./motion-policy-keyboard.js";
import { createLoadGuard, sameIdentitySnapshot } from "./motion-policy-load-guard.js";
import { createMotionPolicyPreflightApi } from "./motion-policy-preflight-api.js";
import { createPolicyStep } from "./motion-policy-policy-step.js";
import {
  buildReviewInput, createReviewState, reviewProgress, setDecision, setRelease,
  validateDecision,
} from "./motion-policy-review-state.js";
import {
  renderCandidateList, renderReleaseList, setReleaseFields, updateCandidateCard,
} from "./motion-policy-review-view.js";
import {
  downloadJson, errorMessage as message, integerOrNull, setStatus as status,
} from "./motion-policy-review-utils.js";
const $ = (id) => document.getElementById(id);
const elements = Object.fromEntries([
  "policyFile", "policySha", "policyIdentitySha", "policyStatus", "policyDetails",
  "policyApproval", "approvePolicyConfirm", "downloadPolicyBtn", "stepOneMarker",
  "stepTwoMarker", "candidateStep", "candidateLockHint",
  "candidateForm", "footFile", "footSha", "depthFile", "depthSha", "loadCandidatesBtn",
  "candidateStatus", "reviewWorkspace", "candidateSearch", "kindFilter", "progressFilter",
  "candidateList", "coverageBadge", "reviewRevision", "loopResetFieldset", "releaseList",
  "reviewStatus", "finalConfirm", "downloadReviewBtn", "liveRegion",
].map((id) => [id, $(id)]));

let footInput = null;
let depthInput = null;
let state = null;
let candidatesById = new Map();
const candidateGuards = { foot: createLoadGuard(), depth: createLoadGuard() };
const inventoryGuard = createLoadGuard();
const preflightApi = createMotionPolicyPreflightApi();
const policyStep = createPolicyStep(elements, (open) => {
  if (open) unlockCandidateStep();
  else lockCandidateStep();
}, { api: preflightApi });

elements.footFile.addEventListener("change", () => loadCandidateFile("foot"));
elements.depthFile.addEventListener("change", () => loadCandidateFile("depth"));
elements.footSha.addEventListener("input", clearLoadedReview);
elements.depthSha.addEventListener("input", clearLoadedReview);
elements.candidateForm.addEventListener("submit", loadInventory);
elements.candidateList.addEventListener("change", handleCandidateChange);
elements.candidateList.addEventListener("input", handleCandidateChange);
elements.candidateList.addEventListener("keydown", (event) => {
  handleCandidateKeyboard(event, elements.candidateList, chooseKeyboardAction);
});
for (const control of [elements.candidateSearch, elements.kindFilter, elements.progressFilter]) {
  control.addEventListener("input", applyFilters);
}
elements.reviewRevision.addEventListener("input", () => {
  if (!state) return;
  state.revision = integerOrNull(elements.reviewRevision.value);
  invalidateConfirmation();
  refreshProgress();
});
elements.loopResetFieldset.addEventListener("change", (event) => {
  if (!state || event.target.name !== "loopReset") return;
  state.loopResetApproved = event.target.value === "true";
  invalidateConfirmation();
  refreshProgress();
});
elements.releaseList.addEventListener("change", handleReleaseChange);
elements.releaseList.addEventListener("input", handleReleaseChange);
elements.finalConfirm.addEventListener("change", () => {
  if (!state) return;
  state.humanConfirmed = elements.finalConfirm.checked;
  elements.downloadReviewBtn.disabled = !state.humanConfirmed || !reviewProgress(state).ready;
});
elements.downloadReviewBtn.addEventListener("click", downloadReviewInput);

async function loadCandidateFile(kind) {
  clearLoadedReview(false);
  const fileInput = kind === "foot" ? elements.footFile : elements.depthFile;
  const shaInput = kind === "foot" ? elements.footSha : elements.depthSha;
  if (kind === "foot") footInput = null;
  else depthInput = null;
  const loaded = await readCandidateFile({
    kind, fileInput, shaInput, guard: candidateGuards[kind],
    statusElement: elements.candidateStatus,
  });
  if (!loaded) return;
  if (kind === "foot") footInput = loaded;
  else depthInput = loaded;
}

async function loadInventory(event) {
  event.preventDefault();
  clearLoadedReview(false);
  const token = inventoryGuard.begin();
  const snapshot = currentIdentitySnapshot();
  setCandidateBusy(true);
  try {
    if (!snapshot.policy) throw new Error("第 1 步尚未完成精确 policy SHA 绑定");
    if (!snapshot.foot || !snapshot.depth) throw new Error("请先加载两份 candidate 文件");
    status(elements.candidateStatus, "正在执行本机 Python 完整候选预检并推导 candidate ID…", "warning");
    const inventory = await authorizeCandidateInventory({
      api: preflightApi,
      snapshot,
      isCurrent: () => inventoryGuard.isCurrent(token) &&
        sameIdentitySnapshot(snapshot, currentIdentitySnapshot()),
    });
    if (!inventory) return;
    state = createReviewState(inventory);
    candidatesById = new Map(inventory.candidates.map((row) => [row.candidateId, row]));
    renderCandidateList(elements.candidateList, inventory.candidates);
    renderReleaseList(elements.releaseList, inventory.unconstrainedTicks);
    elements.reviewRevision.value = "";
    elements.loopResetFieldset.querySelectorAll("input").forEach((input) => { input.checked = false; });
    elements.reviewWorkspace.hidden = false;
    status(elements.candidateStatus, `Python 预检已绑定 ${inventory.projectId} / ${inventory.clipId}；共 ${inventory.candidates.length} 项，不含自动决定。`, "success");
    applyFilters();
    refreshProgress();
  } catch (error) {
    if (inventoryGuard.isCurrent(token) &&
        sameIdentitySnapshot(snapshot, currentIdentitySnapshot())) {
      status(elements.candidateStatus, message(error), "error");
    }
  } finally {
    if (inventoryGuard.isCurrent(token) &&
        sameIdentitySnapshot(snapshot, currentIdentitySnapshot())) setCandidateBusy(false);
  }
}

function currentIdentitySnapshot() {
  let binding = null;
  try { binding = policyStep.binding(); } catch { /* closed policy gate */ }
  return {
    policy: binding?.policy || null,
    policyJson: binding?.policyJson || null,
    foot: footInput,
    depth: depthInput,
    footJson: footInput?.rawText || null,
    depthJson: depthInput?.rawText || null,
    policySha: elements.policySha.value.trim(),
    footSha: elements.footSha.value.trim(),
    depthSha: elements.depthSha.value.trim(),
  };
}

function handleCandidateChange(event) {
  if (!state) return;
  const target = event.target;
  const id = target.dataset.candidateId;
  if (!id) return;
  const candidate = candidatesById.get(id);
  const card = target.closest("[data-candidate-id]");
  const current = state.decisions.get(id) || { action: null, reason_code: "", payload: null };
  if (target.dataset.action) current.action = target.dataset.action;
  if (target.dataset.reason) current.reason_code = target.value.trim();
  if (current.action === "adjust") current.payload = adjustmentFromCard(candidate, card);
  else current.payload = null;
  setDecision(state, candidate, current);
  updateCandidateCard(card, current, validateDecision(candidate, current));
  invalidateConfirmation();
  applyFilters();
  refreshProgress();
}

function chooseKeyboardAction(id, action, card) {
  const candidate = candidatesById.get(id);
  const current = state.decisions.get(id) || { action: null, reason_code: "", payload: null };
  current.action = action;
  current.payload = action === "adjust" ? adjustmentFromCard(candidate, card) : null;
  setDecision(state, candidate, current);
  updateCandidateCard(card, current, validateDecision(candidate, current));
  invalidateConfirmation();
  applyFilters();
  refreshProgress();
}

function adjustmentFromCard(candidate, card) {
  if (candidate.kind === "foot_lock") {
    return { x: card.querySelector("[data-adjust-x]").value, y: card.querySelector("[data-adjust-y]").value };
  }
  return { frontSlot: card.querySelector("[data-adjust-front]").value };
}

function handleReleaseChange(event) {
  if (!state) return;
  const row = event.target.closest("[data-tick]");
  if (!row) return;
  const tick = Number(row.dataset.tick);
  const toggle = row.querySelector("[data-release-toggle]");
  setReleaseFields(row, toggle.checked);
  setRelease(state, tick, toggle.checked ? {
    x: row.querySelector("[data-release-x]").value,
    y: row.querySelector("[data-release-y]").value,
    interpolation: row.querySelector("[data-release-interpolation]").value,
    reasonCode: row.querySelector("[data-release-reason]").value.trim(),
  } : null);
  invalidateConfirmation();
  refreshProgress();
}

function applyFilters() {
  if (!state) return;
  const query = elements.candidateSearch.value.trim().toLowerCase();
  const kind = elements.kindFilter.value;
  const progress = elements.progressFilter.value;
  let visible = 0;
  for (const card of elements.candidateList.querySelectorAll("[data-candidate-id]")) {
    const candidate = candidatesById.get(card.dataset.candidateId);
    const decision = state.decisions.get(candidate.candidateId);
    const complete = !validateDecision(candidate, decision);
    const blocked = candidate.kind === "foot_lock" && candidate.footState.startsWith("rejected_");
    const haystack = [candidate.candidateId, candidate.kind, candidate.tick, candidate.footState, candidate.pairId, ...(candidate.slots || [])].join(" ").toLowerCase();
    const show = (!query || haystack.includes(query)) && (kind === "all" || candidate.kind === kind) &&
      (progress === "all" || (progress === "pending" && !complete) || (progress === "reviewed" && complete) || (progress === "blocked" && blocked));
    card.hidden = !show;
    if (show) visible += 1;
  }
  elements.liveRegion.textContent = `当前显示 ${visible} 项候选`;
}

function refreshProgress() {
  if (!state) return;
  const progress = reviewProgress(state);
  elements.coverageBadge.textContent = `${progress.complete} / ${progress.total} · ${progress.percent}%`;
  elements.finalConfirm.disabled = !progress.ready;
  if (!progress.ready) invalidateConfirmation();
  elements.downloadReviewBtn.disabled = !progress.ready || !state.humanConfirmed;
  status(elements.reviewStatus, progress.ready ? "覆盖率 100%，全局字段有效；等待最终人工确认。" : `${progress.complete}/${progress.total} 项有效；${progress.errors[0]?.message || "仍有未完成字段"}`, progress.ready ? "success" : "warning");
}

function invalidateConfirmation() {
  if (!state) return;
  state.humanConfirmed = false;
  elements.finalConfirm.checked = false;
  elements.downloadReviewBtn.disabled = true;
}

function downloadReviewInput() {
  try {
    const review = buildReviewInput(state);
    downloadJson(`${state.inventory.projectId}.motion-policy-review-input.json`, review);
    status(elements.reviewStatus, "严格四字段 review input 已下载；请交给 compile-motion-policy-decision 做最终合同校验。", "success");
  } catch (error) {
    status(elements.reviewStatus, message(error), "error");
  }
}

function unlockCandidateStep() {
  const wasLocked = elements.candidateStep.classList.contains("locked");
  elements.stepOneMarker.classList.add("complete");
  elements.stepOneMarker.removeAttribute("aria-current");
  elements.stepTwoMarker.setAttribute("aria-current", "step");
  elements.candidateStep.classList.remove("locked");
  elements.candidateLockHint.textContent = "第 1 步已具备人工批准的正式 policy；请运行 probe-depth-order 后加载两份候选。";
  for (const field of [elements.footFile, elements.footSha, elements.depthFile, elements.depthSha, elements.loadCandidatesBtn]) field.disabled = false;
  if (wasLocked) status(elements.candidateStatus, "等待 Foot / Depth candidates。", "warning");
}

function setCandidateBusy(busy) {
  elements.candidateForm.toggleAttribute("aria-busy", busy);
  if (!elements.candidateStep.classList.contains("locked")) {
    elements.loadCandidatesBtn.disabled = busy;
  }
}

function lockCandidateStep() {
  candidateGuards.foot.invalidate();
  candidateGuards.depth.invalidate();
  inventoryGuard.invalidate();
  elements.stepOneMarker.classList.remove("complete");
  elements.stepOneMarker.setAttribute("aria-current", "step");
  elements.stepTwoMarker.removeAttribute("aria-current");
  elements.candidateStep.classList.add("locked");
  elements.candidateForm.reset();
  elements.candidateForm.removeAttribute("aria-busy");
  footInput = null;
  depthInput = null;
  state = null;
  candidatesById = new Map();
  elements.coverageBadge.textContent = "0 / 0";
  elements.finalConfirm.checked = false;
  elements.reviewWorkspace.hidden = true;
  for (const field of [elements.footFile, elements.footSha, elements.depthFile, elements.depthSha, elements.loadCandidatesBtn]) field.disabled = true;
  status(elements.candidateStatus, "等待第 1 步。", "warning");
}

function clearLoadedReview(announce = true) {
  inventoryGuard.invalidate();
  state = null;
  candidatesById = new Map();
  elements.coverageBadge.textContent = "0 / 0";
  elements.finalConfirm.checked = false;
  elements.reviewWorkspace.hidden = true;
  elements.candidateForm.removeAttribute("aria-busy");
  if (!elements.candidateStep.classList.contains("locked")) elements.loadCandidatesBtn.disabled = false;
  if (announce) status(elements.candidateStatus, "候选输入已变化；请重新校验来源并生成 candidate ID。", "warning");
}
