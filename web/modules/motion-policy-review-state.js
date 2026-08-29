const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ACTIONS = new Set(["accept", "adjust", "reject", "unobservable"]);

export function createReviewState(inventory) {
  return {
    inventory,
    decisions: new Map(),
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
  state.humanConfirmed = false;
  return validateDecision(candidate, next);
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
