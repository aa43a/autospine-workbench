import { parseCandidateText, readCandidateFile } from "./motion-policy-candidate-files.js";
import { createMotionPolicyAutoController } from "./motion-policy-auto-controller.js";
import { authorizeCandidateInventory } from "./motion-policy-candidate-preflight.js";
import { createMotionPolicyDecisionController } from "./motion-policy-decision-controller.js";
import { createLoadGuard, sameIdentitySnapshot } from "./motion-policy-load-guard.js";
import { createMotionPolicyPreflightApi } from "./motion-policy-preflight-api.js";
import { createMotionPolicyPageLock } from "./motion-policy-page-lock.js";
import { createPolicyStep } from "./motion-policy-policy-step.js";
import { errorMessage, setStatus } from "./motion-policy-review-utils.js";

const ids = [
  "policyFile", "policySha", "policyIdentitySha", "policyStatus", "policyDetails",
  "policyApproval", "approvePolicyConfirm", "downloadPolicyBtn", "stepOneMarker",
  "stepTwoMarker", "candidateStep", "candidateLockHint", "candidateForm", "footFile",
  "footSha", "depthFile", "depthSha", "loadCandidatesBtn", "candidateStatus",
  "autoStartPanel", "autoProjectSelect", "autoApplySafe", "autoReloadProject",
  "autoLoadStatus", "expertInputs",
];
const elements = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));
const guards = { foot: createLoadGuard(), depth: createLoadGuard(), inventory: createLoadGuard() };
const api = createMotionPolicyPreflightApi();
const publicationLock = createMotionPolicyPageLock(document);
let auto = null;
const review = createMotionPolicyDecisionController(document, {
  onPublished: (receipt) => auto?.markCompleted(receipt.packageId) || null,
  onContinue: (packageId) => auto?.continueTo(packageId) || false,
  onPublishingChange: (locked) => publicationLock.setLocked(locked),
});
let footInput = null;
let depthInput = null;

const policyStep = createPolicyStep(elements, (open) => {
  if (open) unlockCandidateStep();
  else lockCandidateStep();
}, { api });
auto = createMotionPolicyAutoController(elements, {
  onReset: resetAutomaticLoad,
  onLoad: loadAutomaticPackage,
  onAssistChange: (enabled) => {
    const toggle = document.getElementById("approveOnScrub");
    if (toggle) toggle.checked = enabled;
  },
});

elements.expertInputs.addEventListener("input", () => auto.enterExpertMode(), true);
elements.expertInputs.addEventListener("change", () => auto.enterExpertMode(), true);
document.getElementById("approveOnScrub")?.addEventListener("change", (event) => {
  elements.autoApplySafe.checked = event.currentTarget.checked;
});

elements.footFile.addEventListener("change", () => loadCandidateFile("foot"));
elements.depthFile.addEventListener("change", () => loadCandidateFile("depth"));
elements.footSha.addEventListener("input", clearLoadedReview);
elements.depthSha.addEventListener("input", clearLoadedReview);
elements.candidateForm.addEventListener("submit", (event) => loadInventory(event, {
  assistOnScrub: elements.autoApplySafe.checked,
}));

async function loadCandidateFile(kind) {
  clearLoadedReview(false);
  const fileInput = kind === "foot" ? elements.footFile : elements.depthFile;
  const shaInput = kind === "foot" ? elements.footSha : elements.depthSha;
  if (kind === "foot") footInput = null;
  else depthInput = null;
  const loaded = await readCandidateFile({
    kind, fileInput, shaInput, guard: guards[kind], statusElement: elements.candidateStatus,
  });
  if (!loaded) return;
  if (kind === "foot") footInput = loaded;
  else depthInput = loaded;
}

async function loadInventory(event, {
  assistOnScrub = true, throwOnError = false, isCurrent = () => true,
  packageDetail = null,
} = {}) {
  event?.preventDefault();
  if (!isCurrent()) return false;
  clearLoadedReview(false);
  const token = guards.inventory.begin();
  const snapshot = identitySnapshot();
  const stillCurrent = () => isCurrent() && guards.inventory.isCurrent(token) &&
    sameIdentitySnapshot(snapshot, identitySnapshot());
  setCandidateBusy(true);
  try {
    if (!snapshot.policy) throw new Error("第 1 步尚未完成精确 policy SHA 绑定");
    if (!snapshot.foot || !snapshot.depth) throw new Error("请先加载两份 candidate 文件");
    setStatus(elements.candidateStatus, "正在执行本机 Python 完整候选预检并构建视觉证据…", "warning");
    if (!stillCurrent()) return false;
    const inventory = await authorizeCandidateInventory({
      api,
      snapshot,
      isCurrent: stillCurrent,
    });
    if (!inventory || !stillCurrent()) return false;
    review.load(inventory, { assistOnScrub, packageDetail });
    setStatus(elements.candidateStatus,
      `已绑定 ${inventory.projectId} / ${inventory.clipId}；${inventory.candidates.length} 项已组织为连续视觉证据。`,
      "success");
    return true;
  } catch (error) {
    if (stillCurrent()) {
      setStatus(elements.candidateStatus, errorMessage(error), "error");
    }
    if (throwOnError) throw error;
    return false;
  } finally {
    if (stillCurrent()) {
      setCandidateBusy(false);
    }
  }
}

async function loadAutomaticPackage(packageDetail, {
  applySafe = true, isCurrent = () => true,
} = {}) {
  if (!isCurrent()) return false;
  const binding = await policyStep.loadApprovedText(
    packageDetail.policy_json, packageDetail.identities.policy_sha256,
  );
  if (!binding || !isCurrent()) return false;
  const nextFootInput = parseCandidateText(
    "foot", packageDetail.foot_candidates_json, packageDetail.identities.foot_candidates_sha256,
  );
  const nextDepthInput = parseCandidateText(
    "depth", packageDetail.depth_candidates_json, packageDetail.identities.depth_candidates_sha256,
  );
  if (!isCurrent()) return false;
  footInput = nextFootInput;
  depthInput = nextDepthInput;
  elements.footSha.value = packageDetail.identities.foot_candidates_sha256;
  elements.depthSha.value = packageDetail.identities.depth_candidates_sha256;
  if (!isCurrent()) return false;
  const loaded = await loadInventory(null, {
    assistOnScrub: applySafe, throwOnError: true, isCurrent, packageDetail,
  });
  if (!isCurrent()) return false;
  if (!loaded) throw new Error("自动项目加载已被新的选择替代");
  return true;
}

function resetAutomaticLoad() {
  guards.foot.invalidate();
  guards.depth.invalidate();
  guards.inventory.invalidate();
  footInput = null;
  depthInput = null;
  policyStep.clear();
}

function identitySnapshot() {
  let binding = null;
  try { binding = policyStep.binding(); } catch { /* policy gate is closed */ }
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

function unlockCandidateStep() {
  const wasLocked = elements.candidateStep.classList.contains("locked");
  elements.stepOneMarker.classList.add("complete");
  elements.stepOneMarker.removeAttribute("aria-current");
  elements.stepTwoMarker.setAttribute("aria-current", "step");
  elements.candidateStep.classList.remove("locked");
  elements.candidateLockHint.textContent = "正式 policy 已批准；请加载对应 Foot / Depth candidates。";
  candidateFields().forEach((field) => { field.disabled = false; });
  if (wasLocked) setStatus(elements.candidateStatus, "等待 Foot / Depth candidates。", "warning");
}

function lockCandidateStep() {
  guards.foot.invalidate();
  guards.depth.invalidate();
  guards.inventory.invalidate();
  elements.stepOneMarker.classList.remove("complete");
  elements.stepOneMarker.setAttribute("aria-current", "step");
  elements.stepTwoMarker.removeAttribute("aria-current");
  elements.candidateStep.classList.add("locked");
  elements.candidateForm.reset();
  elements.candidateForm.removeAttribute("aria-busy");
  footInput = null;
  depthInput = null;
  review.clear();
  candidateFields().forEach((field) => { field.disabled = true; });
  setStatus(elements.candidateStatus, "等待第 1 步。", "warning");
}

function clearLoadedReview(announce = true) {
  guards.inventory.invalidate();
  review.clear();
  elements.candidateForm.removeAttribute("aria-busy");
  if (!elements.candidateStep.classList.contains("locked")) elements.loadCandidatesBtn.disabled = false;
  if (announce) setStatus(elements.candidateStatus, "候选输入已变化；请重新校验来源。", "warning");
}

function setCandidateBusy(busy) {
  elements.candidateForm.toggleAttribute("aria-busy", busy);
  if (!elements.candidateStep.classList.contains("locked")) elements.loadCandidatesBtn.disabled = busy;
}

function candidateFields() {
  return [elements.footFile, elements.footSha, elements.depthFile, elements.depthSha, elements.loadCandidatesBtn];
}

auto.start();
