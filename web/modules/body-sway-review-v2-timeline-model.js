"use strict";

const ACTIONS = new Set(["approve", "reject", "unobservable"]);
const STATE_PRIORITY = {
  approve: 0,
  pending: 1,
  unobservable: 2,
  reject: 3,
  incomplete: 4,
};

export function buildReviewTimelineGroups(cases) {
  if (!Array.isArray(cases) || !cases.length) {
    throw new Error("时间轴需要至少一个采样帧");
  }
  if ((cases.length - 1) % 2 !== 0 || cases[0]?.animation !== null) {
    throw new Error("采样帧必须以唯一 Setup 开始并按基础/摆动成对排列");
  }
  const setup = requireCase(cases[0]);
  if (setup.tick !== 0 || setup.time_seconds !== 0) {
    throw new Error("Setup 采样必须位于零时刻");
  }
  const groups = [group(`setup:${setup.case_id}`, "setup", setup, [setup])];
  const seen = new Set([setup.case_id]);
  let previousTick = -1;
  let previousTime = -1;
  for (let index = 1; index < cases.length; index += 2) {
    const base = requireCase(cases[index]);
    const sway = requireCase(cases[index + 1]);
    if (seen.has(base.case_id) || seen.has(sway.case_id)
        || base.case_id === sway.case_id) {
      throw new Error("时间轴包含重复 case ID");
    }
    seen.add(base.case_id);
    seen.add(sway.case_id);
    if (base.animation !== "p10.base" || sway.animation !== "p10.body-sway"
        || base.tick !== sway.tick || base.time_seconds !== sway.time_seconds) {
      throw new Error("基础动作与身体摆动采样未严格配对");
    }
    if (base.tick <= previousTick || base.time_seconds <= previousTime) {
      throw new Error("动作采样时间轴未严格递增");
    }
    previousTick = base.tick;
    previousTime = base.time_seconds;
    groups.push(group(
      `time:${base.tick}:${base.time_seconds}`, "comparison", base, [base, sway],
    ));
  }
  return groups.map((row, index) => Object.freeze({
    ...row,
    index,
    cases: Object.freeze([...row.cases]),
  }));
}

export function createDefaultApproveDraft(cases) {
  if (!Array.isArray(cases)) throw new Error("默认草稿需要采样帧");
  const draft = {};
  for (const row of cases) {
    requireCase(row);
    if (Object.hasOwn(draft, row.case_id)) throw new Error("默认草稿包含重复 case ID");
    draft[row.case_id] = { action: "approve", notes: "" };
  }
  return draft;
}

export function clampTimelineIndex(value, groupCount) {
  if (!Number.isInteger(groupCount) || groupCount < 1) return 0;
  const numeric = Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : 0;
  return Math.max(0, Math.min(groupCount - 1, numeric));
}

export function groupIndexForCase(groups, caseId) {
  return groups.findIndex((row) => row.cases.some(
    (candidate) => candidate.case_id === caseId,
  ));
}

export function timelineCoverage(groups, visitedGroupIds) {
  const visited = visitedGroupIds instanceof Set
    ? visitedGroupIds : new Set(visitedGroupIds || []);
  const visitedCount = groups.filter((row) => visited.has(row.id)).length;
  return Object.freeze({
    visitedCount,
    groupCount: groups.length,
    complete: groups.length > 0 && visitedCount === groups.length,
  });
}

export function groupDraftState(groupRow, decisions) {
  let result = "approve";
  for (const row of groupRow.cases) {
    const status = caseDraftState(decisions?.[row.case_id]);
    if (STATE_PRIORITY[status] > STATE_PRIORITY[result]) result = status;
  }
  return result;
}

export function timelineExceptions(groups, decisions) {
  const rows = [];
  groups.forEach((groupRow, groupIndex) => {
    for (const row of groupRow.cases) {
      const choice = decisions?.[row.case_id];
      if (choice?.action === "reject" || choice?.action === "unobservable") {
        rows.push(Object.freeze({
          groupIndex,
          row,
          action: choice.action,
          notes: choice.notes || "",
          incomplete: !choice.notes?.trim(),
        }));
      }
    }
  });
  return rows;
}

function group(id, kind, row, cases) {
  return {
    id,
    kind,
    tick: row.tick,
    timeSeconds: row.time_seconds,
    cases,
  };
}

function requireCase(row) {
  if (!row || typeof row !== "object" || typeof row.case_id !== "string"
      || !row.case_id || !Number.isInteger(row.tick)
      || !Number.isFinite(row.time_seconds)) {
    throw new Error("时间轴包含无效采样帧");
  }
  return row;
}

function caseDraftState(choice) {
  if (!choice || !ACTIONS.has(choice.action)) return "pending";
  if (choice.action !== "approve" && !choice.notes?.trim()) return "incomplete";
  return choice.action;
}
