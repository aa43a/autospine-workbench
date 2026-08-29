export const fixtureUrl = new URL(
  "fixtures/p9-wave-left-depth-policy.proposal.json",
  import.meta.url,
);

export const POLICY_SHA =
  "f54ccb8e48a99a6df97a67b2d64de5a776f94b8bd7ba8cffe4382c7e0357c1ae";

export const EMPTY_CANDIDATE_IDS_SHA =
  "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26a8f32e528890e6533b29";

export function jsonResponse(status, payload) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: () => "application/json; charset=utf-8" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

export function preflightResult(operation, policy, identities, inventory = undefined) {
  return {
    format: "autospine-motion-policy-preflight-result",
    format_version: 1,
    status: "passed",
    operation,
    project_id: policy.project_id,
    clip_id: policy.clip_id,
    identities,
    ...(inventory ? { inventory } : {}),
  };
}

export function emptyInventory(overrides = {}) {
  return {
    total_count: 0,
    foot_count: 0,
    depth_count: 0,
    unconstrained_count: 0,
    candidate_ids_sha256: EMPTY_CANDIDATE_IDS_SHA,
    ...overrides,
  };
}

export function fakeElement(overrides = {}) {
  const element = new EventTarget();
  Object.assign(element, {
    checked: false,
    dataset: {},
    disabled: false,
    files: [],
    hidden: false,
    textContent: "",
    value: "",
    validationMessage: "",
    setCustomValidity(value) { this.validationMessage = value; },
  }, overrides);
  return element;
}

export function policyElements() {
  return {
    policyFile: fakeElement(),
    policySha: fakeElement({ disabled: true }),
    policyIdentitySha: fakeElement({ textContent: "等待本机 Python 预检" }),
    policyStatus: fakeElement(),
    policyDetails: fakeElement({ hidden: true }),
    policyApproval: fakeElement({ hidden: true }),
    approvePolicyConfirm: fakeElement(),
    downloadPolicyBtn: fakeElement({ disabled: true }),
  };
}

export function fileFrom(text) {
  return { size: Buffer.byteLength(text), text: async () => text };
}

export async function waitFor(predicate) {
  for (let index = 0; index < 50; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  throw new Error("timed out waiting for async test state");
}
