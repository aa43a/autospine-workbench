import assert from "node:assert/strict";
import test from "node:test";

import {
  SeamAnchorReviewApiError,
} from "../modules/seam-anchor-review-api.js";
import {
  normalizeSeamPublicationReceipt,
} from "../modules/seam-anchor-review-publication.js";
import {
  SeamReviewSubmitControllerError,
} from "../modules/seam-anchor-review-submit-controller.js";
import {
  createSeamReviewSubmitFlow,
} from "../modules/seam-anchor-review-submit-flow.js";
import {
  assessDefinitiveNoCommit, isDefinitiveServerResponseFailure,
} from "../modules/seam-anchor-review-submit-reconciliation.js";
import {
  ADDRESS, SHA, decideAll, normalizedState,
} from "./seam-anchor-review-fixtures.js";

const CANDIDATE = "d".repeat(64);
const DECISION = "2".repeat(64);

function decisionReceipt() {
  return {
    candidate_sha256: CANDIDATE,
    decision_sha256: DECISION,
    revision: 1,
    status: "reviewed_anchor_set_ready_for_compile",
    release_gate: {
      status: "blocked",
      reason_codes: [
        "dynamic_seam_safety_unproven",
        "reviewed_seam_anchor_set_missing",
        "runtime_equivalence_unproven",
        "visual_seam_quality_unproven",
      ],
    },
    summary: {
      relationship_count: 6, accept_count: 6, adjust_count: 0,
      reject_count: 0, unobservable_count: 0, anchor_pair_count: 12,
    },
    reused: false,
  };
}

function publicationReceipt() {
  return {
    format: "autospine-reviewed-seam-anchor-set-receipt",
    format_version: 1,
    status: "passed",
    package_id: SHA.package,
    source: {
      project_id: "sample.project",
      candidate_sha256: CANDIDATE,
      review_revision: 1,
      decision_sha256: DECISION,
    },
    address: {
      project_id: "sample.project",
      reviewed_set_sha256: "4".repeat(64),
      bundle_sha256: "5".repeat(64),
    },
    verification: {
      status: "passed",
      replayed_from_exact_upstreams: true,
      head_observation: {
        method: "double_snapshot", scope: "compile_time", revision: 1,
        head_decision_sha256: DECISION, permanent_authority_claimed: false,
      },
    },
    release_gate: {
      status: "blocked",
      reason_codes: [
        "dynamic_seam_safety_unproven",
        "runtime_equivalence_unproven",
        "visual_seam_quality_unproven",
      ],
    },
    summary: { relationship_count: 6, anchor_pair_count: 12 },
  };
}

function emptyHistory() {
  return {
    candidate_sha256: CANDIDATE,
    current_revision: 0,
    head_decision_sha256: null,
    items: [],
  };
}

function revisionOneHistory() {
  return {
    candidate_sha256: CANDIDATE,
    current_revision: 1,
    head_decision_sha256: DECISION,
    items: [{
      revision: 1,
      decision_sha256: DECISION,
      status: "reviewed_anchor_set_ready_for_compile",
    }],
  };
}

function statusElement() {
  return { textContent: "", dataset: {} };
}

function flowElements() {
  const documentStub = { createElement: () => ({ textContent: "" }) };
  return {
    reviewerId: { value: "workbench-operator" }, reviewNotes: { value: "" },
    publicationPanel: { hidden: true, dataset: {} },
    publicationStage: statusElement(), publicationStatus: statusElement(),
    submitStatus: statusElement(), reviewedSetSha: statusElement(),
    reviewedSetBundleSha: statusElement(), retryPublicationBtn: { hidden: true },
    downloadPublicationBtn: { disabled: true }, nextDynamicSeamLink: { hidden: true },
    historyList: { replaceChildren() {} }, decisionDocument: statusElement(),
    useHeadBtn: { disabled: false }, baselineStatus: statusElement(),
    historySelectionStatus: statusElement(), reviewProgress: statusElement(),
    reviewProgressBar: { max: 1, value: 0 }, derivedStatus: statusElement(),
    releaseStatus: statusElement(),
    releaseReasons: { ownerDocument: documentStub, replaceChildren() {} },
    submitReviewBtn: { disabled: false, firstChild: { textContent: "" } },
  };
}

test("only a server response plus unchanged exact history proves no commit", () => {
  const response = new SeamAnchorReviewApiError(
    "The request could not be completed safely.", 500,
    { error: "seam_anchor_review_error" },
  );
  const wrapped = new SeamReviewSubmitControllerError(
    "P10.5b submission uncertain", "decision_request_failed", response,
  );
  const input = {
    error: wrapped, historyPayload: emptyHistory(),
    candidateSha256: CANDIDATE,
    baseline: { revision: 0, decisionSha256: null },
  };
  assert.equal(isDefinitiveServerResponseFailure(wrapped), true);
  assert.equal(assessDefinitiveNoCommit(input).status, "not_committed");
  assert.equal(assessDefinitiveNoCommit({
    ...input, historyPayload: revisionOneHistory(),
  }).status, "history_changed");
  const networkError = new TypeError("Failed to fetch");
  assert.equal(isDefinitiveServerResponseFailure(networkError), false);
  assert.equal(assessDefinitiveNoCommit({ ...input, error: networkError }), null);
});

test("flow preserves a draft after a definitive no-commit response", async () => {
  let state = decideAll(normalizedState());
  state = {
    ...state, baseline: { revision: 0, decisionSha256: null },
    reviewerId: "workbench-operator",
  };
  const originalDraft = JSON.stringify(state.decisions);
  const elements = flowElements();
  const applied = [];
  let decisionCalls = 0;
  let historyCalls = 0;
  let publicationCalls = 0;
  const api = {
    async submit() {
      decisionCalls += 1;
      if (decisionCalls === 1) {
        throw new SeamAnchorReviewApiError(
          "The request could not be completed safely.", 500,
          { error: "seam_anchor_review_error" },
        );
      }
      return decisionReceipt();
    },
    async loadHistory() {
      historyCalls += 1;
      return historyCalls === 1 ? emptyHistory() : revisionOneHistory();
    },
    async publish(_packageId, request) {
      publicationCalls += 1;
      return normalizeSeamPublicationReceipt(publicationReceipt(), request);
    },
  };
  let requestToken = 0;
  const requests = {
    next: () => ++requestToken,
    isCurrent: (token) => token === requestToken,
  };
  const historyController = {
    applyHistory(payload, options = {}) {
      applied.push(options);
      state = {
        ...state, history: payload, stale: false,
        baseline: options.autoBaseline ? {
          revision: payload.current_revision,
          decisionSha256: payload.head_decision_sha256,
        } : null,
      };
    },
  };
  const flow = createSeamReviewSubmitFlow({
    api, elements, requests, busy: { begin: () => 1, finish() {} },
    errorText: (error) => error.message, announce() {},
    getState: () => state, setState: (next) => { state = next; },
    getAddress: () => ADDRESS, getPackageId: () => SHA.package,
    getHistoryController: () => historyController,
  });

  await flow.submit();

  assert.equal(decisionCalls, 1);
  assert.equal(historyCalls, 1);
  assert.equal(publicationCalls, 0);
  assert.equal(flow.snapshot().phase, "decision_retry_available");
  assert.deepEqual(applied, [{ autoBaseline: true }]);
  assert.deepEqual(state.baseline, { revision: 0, decisionSha256: null });
  assert.equal(JSON.stringify(state.decisions), originalDraft);
  assert.match(elements.submitStatus.textContent, /未保存.*草稿已保留/);

  await flow.submit();

  assert.equal(decisionCalls, 2);
  assert.equal(publicationCalls, 1);
  assert.equal(flow.snapshot().phase, "complete");
  assert.equal(flow.snapshot().decisionCommitted, true);
});
