import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { approveDepthPolicy } from "../modules/motion-policy-contracts.js";
import {
  authorizeCandidateInventory,
} from "../modules/motion-policy-candidate-preflight.js";
import {
  MotionPolicyPreflightError, PREFLIGHT_FORMAT, PREFLIGHT_INTENT, PREFLIGHT_URL,
  createMotionPolicyPreflightApi, normalizeCandidateInventory,
} from "../modules/motion-policy-preflight-api.js";
import { createPolicyStep } from "../modules/motion-policy-policy-step.js";
import {
  emptyInventory, fakeElement, fileFrom, fixtureUrl, jsonResponse, policyElements,
  preflightResult, waitFor,
} from "./motion-policy-review-fixtures.mjs";

test("preflight client sends exact JSON text and the required intent without reserialization", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const policyJson = JSON.stringify(approved).replace('"enter_threshold":0.05', '"enter_threshold":5e-2');
  const footJson = '{"format":"envelope","report":{"ratio":1.0}}';
  const depthJson = '{"format":"envelope","report":{"ratio":1e0}}';
  const declared = {
    policy_sha256: "9".repeat(64),
    foot_candidates_sha256: "8".repeat(64),
    depth_candidates_sha256: "7".repeat(64),
  };
  const calls = [];
  const api = createMotionPolicyPreflightApi(async (...args) => {
    calls.push(args);
    const body = JSON.parse(args[1].body);
    if (body.operation === "policy_identity") {
      return jsonResponse(200, preflightResult(
        "policy_identity", approved, { policy_sha256: declared.policy_sha256 },
      ));
    }
    return jsonResponse(200, preflightResult(
      "candidate_inventory", approved, declared,
      emptyInventory(),
    ));
  });
  const identity = await api.policyIdentity(policyJson, approved);
  assert.equal(identity.identities.policy_sha256, declared.policy_sha256);
  await api.candidateInventory(policyJson, footJson, depthJson, declared, approved);
  assert.equal(calls.length, 2);
  for (const [url, options] of calls) {
    assert.equal(url, PREFLIGHT_URL);
    assert.equal(options.method, "POST");
    assert.equal(options.headers["X-Autospine-Intent"], PREFLIGHT_INTENT);
  }
  const policyBody = JSON.parse(calls[0][1].body);
  assert.deepEqual(Object.keys(policyBody), ["format", "format_version", "operation", "policy_json"]);
  assert.equal(policyBody.format, PREFLIGHT_FORMAT);
  assert.equal(policyBody.policy_json, policyJson);
  assert.match(policyBody.policy_json, /5e-2/);
  const candidateBody = JSON.parse(calls[1][1].body);
  assert.equal(candidateBody.policy_json, policyJson);
  assert.equal(candidateBody.foot_candidates_json, footJson);
  assert.equal(candidateBody.depth_candidates_json, depthJson);
  assert.match(candidateBody.foot_candidates_json, /1\.0/);
  assert.match(candidateBody.depth_candidates_json, /1e0/);
});

test("tampered or incomplete Python results fail closed", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const declared = {
    policy_sha256: "1".repeat(64),
    foot_candidates_sha256: "2".repeat(64),
    depth_candidates_sha256: "3".repeat(64),
  };
  const tampered = preflightResult(
    "candidate_inventory", approved,
    { ...declared, depth_candidates_sha256: "4".repeat(64) },
    emptyInventory(),
  );
  assert.throws(() => normalizeCandidateInventory(tampered, approved, declared), /当前输入快照/);
  const incomplete = structuredClone(tampered);
  incomplete.identities = declared;
  delete incomplete.inventory.unconstrained_count;
  assert.throws(() => normalizeCandidateInventory(incomplete, approved, declared), /字段不完整/);

  let calls = 0;
  const api = createMotionPolicyPreflightApi(async () => {
    calls += 1;
    return jsonResponse(400, {
      error: "invalid_motion_policy_preflight_request",
      message: "The motion-policy preflight request is invalid.",
    });
  });
  await assert.rejects(
    () => api.policyIdentity(JSON.stringify(approved), approved),
    (error) => error instanceof MotionPolicyPreflightError && error.status === 400,
  );
  assert.equal(calls, 1);

  const elements = policyElements();
  const gates = [];
  const incompleteApi = createMotionPolicyPreflightApi(async () => jsonResponse(200, {
    ...preflightResult("policy_identity", approved, {}),
  }));
  createPolicyStep(elements, (open) => gates.push(open), {
    api: incompleteApi, renderDetails: () => {}, download: () => assert.fail("must fail closed"),
  });
  const formalJson = JSON.stringify(approved);
  elements.policyFile.files = [fileFrom(formalJson)];
  elements.policyFile.dispatchEvent(new Event("change"));
  await waitFor(() => elements.policyStatus.dataset.tone === "error");
  assert.equal(gates.includes(true), false);
  assert.equal(elements.policyIdentitySha.textContent, "等待本机 Python 预检");
});

test("late policy preflight cannot overwrite newer DOM selection or unlock its gate", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const firstJson = JSON.stringify(approved).replace('"enter_threshold":0.05', '"enter_threshold":5e-2');
  const secondJson = JSON.stringify(approved).replace('"enter_threshold":0.05', '"enter_threshold":0.0500');
  const firstSha = "a".repeat(64);
  const secondSha = "b".repeat(64);
  let releaseFirst;
  const calls = [];
  const api = createMotionPolicyPreflightApi(async (_url, options) => {
    const body = JSON.parse(options.body);
    calls.push(body.policy_json);
    if (body.policy_json === firstJson) {
      return new Promise((resolve) => { releaseFirst = resolve; });
    }
    return jsonResponse(200, preflightResult(
      "policy_identity", approved, { policy_sha256: secondSha },
    ));
  });
  const elements = policyElements();
  const gates = [];
  const step = createPolicyStep(elements, (open) => gates.push(open), {
    api, renderDetails: () => {}, download: () => assert.fail("formal policy must not download"),
  });

  elements.policyFile.files = [fileFrom(firstJson)];
  elements.policyFile.dispatchEvent(new Event("change"));
  await waitFor(() => calls.length === 1);
  elements.policyFile.files = [fileFrom(secondJson)];
  elements.policyFile.dispatchEvent(new Event("change"));
  await waitFor(() => elements.policyIdentitySha.textContent === secondSha);
  elements.policySha.value = secondSha;
  elements.policySha.dispatchEvent(new Event("input"));
  assert.equal(gates.at(-1), true);
  assert.equal(step.binding().policyJson, secondJson);

  releaseFirst(jsonResponse(200, preflightResult(
    "policy_identity", approved, { policy_sha256: firstSha },
  )));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements.policyIdentitySha.textContent, secondSha);
  assert.equal(gates.at(-1), true);
  assert.deepEqual(calls, [firstJson, secondJson]);
});

test("approved proposal preflights and downloads one identical fixed JSON text", async () => {
  const proposalJson = await readFile(fixtureUrl, "utf8");
  const proposal = JSON.parse(proposalJson);
  const approved = approveDepthPolicy(proposal);
  const serverSha = "c".repeat(64);
  const sent = [];
  const downloads = [];
  const api = createMotionPolicyPreflightApi(async (_url, options) => {
    const body = JSON.parse(options.body);
    sent.push(body.policy_json);
    return jsonResponse(200, preflightResult(
      "policy_identity", approved, { policy_sha256: serverSha },
    ));
  });
  const elements = policyElements();
  const gates = [];
  createPolicyStep(elements, (open) => gates.push(open), {
    api,
    renderDetails: () => {},
    download: (filename, text) => downloads.push({ filename, text }),
  });
  elements.policyFile.files = [fileFrom(proposalJson)];
  elements.policyFile.dispatchEvent(new Event("change"));
  await waitFor(() => elements.policyApproval.hidden === false);
  assert.equal(sent.length, 0);
  elements.approvePolicyConfirm.checked = true;
  elements.approvePolicyConfirm.dispatchEvent(new Event("change"));
  elements.downloadPolicyBtn.dispatchEvent(new Event("click"));
  await waitFor(() => downloads.length === 1);
  assert.equal(sent[0], downloads[0].text);
  assert.equal(JSON.parse(downloads[0].text).review.status, "approved");
  assert.equal("proposal" in JSON.parse(downloads[0].text), false);
  assert.equal(elements.policyIdentitySha.textContent, serverSha);
  assert.equal(elements.policySha.value, "");
  assert.equal(gates.includes(true), false);
});

test("automatic approved policy fills the exact Python identity without a file or SHA field", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const exactJson = JSON.stringify(approved);
  const serverSha = "d".repeat(64);
  const elements = policyElements();
  const gates = [];
  const step = createPolicyStep(elements, (open) => gates.push(open), {
    api: {
      policyIdentity: async (text, document) => {
        assert.equal(text, exactJson);
        assert.deepEqual(document, approved);
        return { identities: { policy_sha256: serverSha } };
      },
    },
    renderDetails: () => {},
    download: () => assert.fail("automatic load must not download a policy"),
  });

  const binding = await step.loadApprovedText(exactJson, serverSha);
  assert.equal(binding.policySha, serverSha);
  assert.equal(binding.policyJson, exactJson);
  assert.equal(elements.policySha.value, serverSha);
  assert.equal(elements.policyIdentitySha.textContent, serverSha);
  assert.equal(gates.at(-1), true);

  step.clear();
  assert.equal(gates.at(-1), false);
  assert.equal(elements.policySha.value, "");
});

test("late candidate preflight is discarded after a DOM identity change", async () => {
  const proposal = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const approved = approveDepthPolicy(proposal);
  const declared = {
    policy_sha256: "1".repeat(64),
    foot_candidates_sha256: "2".repeat(64),
    depth_candidates_sha256: "3".repeat(64),
  };
  let release;
  const calls = [];
  const api = createMotionPolicyPreflightApi(async (_url, options) => {
    calls.push(JSON.parse(options.body));
    return new Promise((resolve) => { release = resolve; });
  });
  const shaInput = fakeElement({ value: declared.foot_candidates_sha256 });
  const snapshot = {
    policy: approved,
    policyJson: '{"threshold":1.0}',
    foot: { document: {} }, depth: { document: {} },
    footJson: '{"report":{"threshold":1.0}}',
    depthJson: '{"report":{"threshold":1e0}}',
    policySha: declared.policy_sha256,
    footSha: declared.foot_candidates_sha256,
    depthSha: declared.depth_candidates_sha256,
  };
  const pending = authorizeCandidateInventory({
    api, snapshot, isCurrent: () => shaInput.value === snapshot.footSha,
  });
  await waitFor(() => calls.length === 1);
  shaInput.value = "4".repeat(64);
  shaInput.dispatchEvent(new Event("input"));
  release(jsonResponse(200, preflightResult(
    "candidate_inventory", approved, declared,
    emptyInventory(),
  )));
  assert.equal(await pending, null);
  assert.equal(calls[0].foot_candidates_json, snapshot.footJson);
  assert.equal(calls[0].depth_candidates_json, snapshot.depthJson);
});
