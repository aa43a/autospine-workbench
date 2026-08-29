import {
  MAX_POLICY_BYTES, approveDepthPolicy, parseJsonFile, validateDepthPolicyInput,
} from "./motion-policy-contracts.js";
import { createLoadGuard } from "./motion-policy-load-guard.js";
import { createMotionPolicyPreflightApi } from "./motion-policy-preflight-api.js";
import { renderPolicyDetails } from "./motion-policy-review-view.js";
import {
  downloadJsonText, errorMessage, jsonText, requireFile, setStatus,
} from "./motion-policy-review-utils.js";

const SHA = /^[0-9a-f]{64}$/;

export function createPolicyStep(elements, onGateChange, dependencies = {}) {
  const guard = createLoadGuard();
  const api = dependencies.api || createMotionPolicyPreflightApi();
  const renderDetails = dependencies.renderDetails || renderPolicyDetails;
  const download = dependencies.download || downloadJsonText;
  let policy = null;
  let policyJson = null;
  let approvedPolicy = null;
  let identitySha = null;

  elements.policyFile.addEventListener("change", loadPolicy);
  elements.policySha.addEventListener("input", syncGate);
  elements.approvePolicyConfirm.addEventListener("change", () => {
    elements.downloadPolicyBtn.disabled = !elements.approvePolicyConfirm.checked;
    if (!elements.approvePolicyConfirm.checked) guard.invalidate();
  });
  elements.downloadPolicyBtn.addEventListener("click", downloadApprovedPolicy);

  function binding() {
    const explicitSha = elements.policySha.value.trim();
    const issue = gateIssue(approvedPolicy, identitySha, explicitSha);
    if (issue) throw new Error(issue);
    return { policy: approvedPolicy, policyJson, policySha: explicitSha };
  }

  async function loadPolicy() {
    const token = guard.begin();
    resetPolicy();
    onGateChange(false);
    try {
      const file = requireFile(elements.policyFile, "Depth policy");
      if (file.size > MAX_POLICY_BYTES) throw new Error("Depth policy 文件超过 1 MiB 上限");
      const text = await file.text();
      if (!currentFile(token, file)) return;
      const raw = parseJsonFile(text, "Depth policy", MAX_POLICY_BYTES);
      const checked = validateDepthPolicyInput(raw);
      if (checked.approved) {
        setStatus(elements.policyStatus, "正在请求本机 Python 只读 policy identity 预检…", "warning");
        const result = await api.policyIdentity(text, checked.document);
        if (!currentFile(token, file)) return;
        commitApproved(checked.document, text, result.identities.policy_sha256);
        setStatus(elements.policyStatus, "正式 policy 已通过本机 Python 预检；请显式填写返回的 SHA 以解锁第 2 步。", "warning");
      } else {
        policy = checked.document;
        renderDetails(elements.policyDetails, policy);
        elements.policyDetails.hidden = false;
        elements.policyApproval.hidden = false;
        setStatus(elements.policyStatus, "草案已加载；请逐项核对，页面没有替你批准。", "warning");
      }
    } catch (error) {
      if (guard.isCurrent(token)) setStatus(elements.policyStatus, errorMessage(error), "error");
    }
  }

  async function downloadApprovedPolicy() {
    const token = guard.begin();
    const proposal = policy;
    onGateChange(false);
    elements.downloadPolicyBtn.disabled = true;
    try {
      if (!elements.approvePolicyConfirm.checked || !proposal) throw new Error("尚未明确人工批准");
      const approved = approveDepthPolicy(proposal);
      const approvedJson = jsonText(approved);
      setStatus(elements.policyStatus, "正在请求本机 Python 只读 policy identity 预检…", "warning");
      const result = await api.policyIdentity(approvedJson, approved);
      if (!guard.isCurrent(token) || policy !== proposal || !elements.approvePolicyConfirm.checked) return;
      commitApproved(approved, approvedJson, result.identities.policy_sha256);
      download(`${approved.project_id}.depth-pair-policy.json`, approvedJson);
      setStatus(elements.policyStatus, "正式 policy 已由 Python 预检并下载；请把返回的 SHA 显式填入 SHA 输入框。", "success");
    } catch (error) {
      if (guard.isCurrent(token)) setStatus(elements.policyStatus, errorMessage(error), "error");
    } finally {
      if (guard.isCurrent(token) && policy === proposal && !approvedPolicy) {
        elements.downloadPolicyBtn.disabled = !elements.approvePolicyConfirm.checked;
      }
    }
  }

  function commitApproved(document, exactJson, sha) {
    policy = document;
    policyJson = exactJson;
    approvedPolicy = document;
    identitySha = sha;
    renderDetails(elements.policyDetails, document);
    elements.policyDetails.hidden = false;
    elements.policyApproval.hidden = true;
    elements.policySha.disabled = false;
    elements.policyIdentitySha.textContent = sha;
    syncGate();
  }

  function syncGate() {
    const issue = gateIssue(approvedPolicy, identitySha, elements.policySha.value.trim());
    elements.policySha.setCustomValidity(issue);
    onGateChange(!issue);
  }

  function resetPolicy() {
    policy = null;
    policyJson = null;
    approvedPolicy = null;
    identitySha = null;
    elements.policySha.value = "";
    elements.policySha.disabled = true;
    elements.policySha.setCustomValidity("");
    elements.policyIdentitySha.textContent = "等待本机 Python 预检";
    elements.policyDetails.hidden = true;
    elements.policyApproval.hidden = true;
    elements.approvePolicyConfirm.checked = false;
    elements.downloadPolicyBtn.disabled = true;
  }

  function currentFile(token, file) {
    return guard.isCurrent(token) && elements.policyFile.files?.[0] === file;
  }

  return { binding };
}

export function gateIssue(policy, identitySha, explicitSha) {
  if (!policy || !SHA.test(identitySha || "")) return "尚无合同有效的正式 policy";
  if (!SHA.test(explicitSha)) return "请显式填写完整小写 policy SHA-256";
  if (explicitSha !== identitySha) return "填写的 policy SHA 与本机 Python 预检返回值不一致";
  return "";
}
