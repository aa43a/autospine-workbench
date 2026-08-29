const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ACTIONS = new Set(["accept", "adjust", "reject", "unobservable"]);

export function createReviewState(inventory) {
  return {
    inventory,
    snapshotKey: inventory.snapshotKey || null,
    decisions: new Map(),
    decisionSources: new Map(),
    decisionVersion: 0,
    batchHistory: [],
    nextBatchId: 1,
    releases: new Map(),
    revision: null,
    loopResetApproved: null,
    humanConfirmed: false,
  };
}

export function setDecision(state, candidate, patch) {
  const previous = state.decisions.get(candidate.candidateId) || {
    action: null, reason_code: "", payload: null,
  };
  const next = { ...previous, ...patch };
  if (next.action !== "adjust") next.payload = null;
  state.decisions.set(candidate.candidateId, next);
  state.decisionSources.set(candidate.candidateId, Object.freeze({ kind: "manual" }));
  state.decisionVersion += 1;
  state.humanConfirmed = false;
  return validateDecision(candidate, next);
}

export function setDecisionBatch(state, candidateIds, patch, options = {}) {
  const candidates = exactCandidates(state, candidateIds);
  const decision = batchDecision(patch);
  const source = batchSource(state, options);
  for (const candidate of candidates) {
    const issue = validateDecision(candidate, decision);
    if (issue) throw new Error(`${candidate.candidateId}: ${issue}`);
  }
  const batchId = `${source.kind === "assisted" ? "assist" : "batch"}-${state.nextBatchId}`;
  const before = candidates.map((candidate) => ({
    candidateId: candidate.candidateId,
    decision: cloneDecision(state.decisions.get(candidate.candidateId)),
    source: state.decisionSources.get(candidate.candidateId) || null,
  }));
  const overwriteCount = before.filter((row) => row.decision !== null).length;
  for (const candidate of candidates) {
    state.decisions.set(candidate.candidateId, { ...decision });
    state.decisionSources.set(
      candidate.candidateId,
      Object.freeze({ ...source, batchId }),
    );
  }
  state.nextBatchId += 1;
  state.decisionVersion += 1;
  state.batchHistory.push({
    batchId,
    candidateIds: Object.freeze(candidates.map((row) => row.candidateId)),
    decision: Object.freeze({ ...decision }),
    sourceKind: source.kind,
    provenance: Object.freeze({ ...source }),
    before,
    undone: false,
  });
  state.humanConfirmed = false;
  return Object.freeze({
    batchId,
    candidateIds: state.batchHistory.at(-1).candidateIds,
    overwriteCount,
  });
}

export function undoDecisionBatch(state, requestedBatchId = null) {
  const record = requestedBatchId === null
    ? [...state.batchHistory].reverse().find((row) => !row.undone)
    : state.batchHistory.find((row) => row.batchId === requestedBatchId);
  if (!record || record.undone) throw new Error("找不到可撤销的批量草稿");
  let restoredCount = 0;
  for (const before of record.before) {
    const source = state.decisionSources.get(before.candidateId);
    if (source?.batchId !== record.batchId) continue;
    if (before.decision === null) {
      state.decisions.delete(before.candidateId);
      state.decisionSources.delete(before.candidateId);
    } else {
      state.decisions.set(before.candidateId, cloneDecision(before.decision));
      if (before.source) state.decisionSources.set(before.candidateId, before.source);
      else state.decisionSources.delete(before.candidateId);
    }
    restoredCount += 1;
  }
  record.undone = true;
  if (restoredCount) {
    state.decisionVersion += 1;
    state.humanConfirmed = false;
  }
  return Object.freeze({
    batchId: record.batchId,
    restoredCount,
    skippedCount: record.candidateIds.length - restoredCount,
  });
}

export function setRelease(state, tick, value) {
  if (!state.inventory.unconstrainedTicks.includes(tick)) {
    throw new Error("Root release key 只能使用 unconstrained foot tick");
  }
  if (value === null) state.releases.delete(tick);
  else state.releases.set(tick, value);
  state.humanConfirmed = false;
}

export function reviewProgress(state) {
  let complete = 0;
  const errors = [];
  for (const candidate of state.inventory.candidates) {
    const message = validateDecision(candidate, state.decisions.get(candidate.candidateId));
    if (!message) complete += 1;
    else errors.push({ candidateId: candidate.candidateId, message });
  }
  for (const [tick, row] of state.releases) {
    const message = validateRelease(state.inventory.unconstrainedTicks, tick, row);
    if (message) errors.push({ candidateId: `release-${tick}`, message });
  }
  if (!Number.isInteger(state.revision) || state.revision < 1 || state.revision > 2147483647) {
    errors.push({ candidateId: "review", message: "Revision 必须是至少 1 的整数" });
  }
  if (typeof state.loopResetApproved !== "boolean") {
    errors.push({ candidateId: "loop", message: "必须明确选择是否批准 loop draw-order reset" });
  } else if (!state.inventory.loop && state.loopResetApproved) {
    errors.push({ candidateId: "loop", message: "非 loop clip 禁止批准 draw-order loop reset" });
  }
  return {
    complete,
    total: state.inventory.candidates.length,
    percent: state.inventory.candidates.length ? Math.round(complete * 100 / state.inventory.candidates.length) : 100,
    errors,
    ready: complete === state.inventory.candidates.length && errors.length === 0,
  };
}

export function buildReviewInput(state) {
  const progress = reviewProgress(state);
  if (!progress.ready) throw new Error("尚未完成全部人工决定与全局字段");
  if (!state.humanConfirmed) throw new Error("请先勾选最终人工确认");
  const decisions = state.inventory.candidates.map((candidate) => {
    const row = state.decisions.get(candidate.candidateId);
    return {
      candidate_id: candidate.candidateId,
      action: row.action,
      reason_code: row.reason_code,
      payload: row.action === "adjust" ? normalizedPayload(candidate, row.payload) : null,
    };
  });
  decisions.sort((a, b) => a.candidate_id.localeCompare(b.candidate_id));
  const releases = [...state.releases.entries()].map(([tick, row]) => ({
    tick,
    correction_xy_px: [finite(row.x), finite(row.y)],
    incoming_interpolation: row.interpolation,
    reason_code: row.reasonCode,
  })).sort((a, b) => a.tick - b.tick);
  return {
    review: { status: "approved", method: "human", revision: state.revision },
    decisions,
    root_release_keys: releases,
    draw_order_loop_reset: { mode: "explicit", approved: state.loopResetApproved },
  };
}

export function validateDecision(candidate, row) {
  if (!row || !ACTIONS.has(row.action)) return "尚未选择 action";
  if (!ID.test(row.reason_code || "")) return "reason_code 必须是安全标识符";
  if (row.action === "accept" && candidate.kind === "foot_lock" &&
      ["rejected_limit", "rejected_conflict"].includes(candidate.footState)) {
    return `${candidate.footState} foot 候选禁止 accept`;
  }
  if (row.action !== "adjust") return row.payload === null ? "" : "非 adjust 的 payload 必须为 null";
  if (candidate.kind === "foot_lock") {
    if (!row.payload || !validNumberInput(row.payload.x) || !validNumberInput(row.payload.y)) {
      return "Foot adjust 需要有限 final correction X/Y";
    }
    return "";
  }
  if (!row.payload || !candidate.slots.includes(row.payload.frontSlot)) {
    return "Depth adjust 的 final_front_slot 必须属于当前 pair";
  }
  return "";
}

function normalizedPayload(candidate, payload) {
  return candidate.kind === "foot_lock"
    ? { final_correction_xy_px: [finite(payload.x), finite(payload.y)] }
    : { final_front_slot: payload.frontSlot };
}

function exactCandidates(state, candidateIds) {
  if (!Array.isArray(candidateIds) || candidateIds.length === 0) {
    throw new Error("批量草稿必须包含至少一个 candidate ID");
  }
  const byId = new Map(state.inventory.candidates.map((row) => [row.candidateId, row]));
  const unique = new Set();
  return candidateIds.map((candidateId) => {
    if (typeof candidateId !== "string" || unique.has(candidateId)) {
      throw new Error("批量 candidate ID 必须是唯一字符串");
    }
    unique.add(candidateId);
    const candidate = byId.get(candidateId);
    if (!candidate) throw new Error(`未知 candidate ID: ${candidateId}`);
    return candidate;
  });
}

function batchDecision(patch) {
  if (!patch || !["accept", "reject", "unobservable"].includes(patch.action)) {
    throw new Error("批量草稿只允许 accept、reject 或 unobservable");
  }
  if (!ID.test(patch.reason_code || "")) {
    throw new Error("批量 reason_code 必须是非空安全标识符");
  }
  if (patch.payload !== undefined && patch.payload !== null) {
    throw new Error("批量草稿 payload 必须为 null");
  }
  return { action: patch.action, reason_code: patch.reason_code, payload: null };
}

function batchSource(state, options) {
  const kind = options?.sourceKind ?? "batch";
  if (!["batch", "assisted"].includes(kind)) throw new Error("批量来源无效");
  if (kind === "batch") return { kind };
  if (options.snapshotKey !== state.snapshotKey || options.profile !== "safe-assist-v1" ||
      typeof options.rule !== "string" || !ID.test(options.rule) ||
      !["timeline", "all-safe"].includes(options.trigger)) {
    throw new Error("自动辅助来源与当前 candidate snapshot 不一致");
  }
  return {
    kind, profile: options.profile, rule: options.rule,
    trigger: options.trigger, snapshotKey: options.snapshotKey,
  };
}

function cloneDecision(value) {
  if (!value) return null;
  return {
    action: value.action,
    reason_code: value.reason_code,
    payload: value.payload === null ? null : structuredClone(value.payload),
  };
}

function validateRelease(allowed, tick, row) {
  if (!allowed.includes(tick)) return "Release tick 不是 unconstrained tick";
  if (!row || !validNumberInput(row.x) || !validNumberInput(row.y)) return "Release correction 必须是有限 X/Y";
  if (!["linear", "stepped"].includes(row.interpolation)) return "Release interpolation 无效";
  if (!ID.test(row.reasonCode || "")) return "Release reason_code 无效";
  return "";
}

function finite(value) {
  if (typeof value !== "number" && typeof value !== "string") throw new Error("数值类型无效");
  if (typeof value === "string" && value.trim() === "") throw new Error("数值不能为空");
  const result = Number(value);
  if (!Number.isFinite(result) || Math.abs(result) > 1e12) throw new Error("数值超出合同范围");
  return Object.is(result, -0) ? 0 : result;
}

function validNumberInput(value) {
  if (typeof value !== "number" && typeof value !== "string") return false;
  if (typeof value === "string" && value.trim() === "") return false;
  const number = Number(value);
  return Number.isFinite(number) && Math.abs(number) <= 1e12;
}
