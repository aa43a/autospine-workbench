const SHA = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ROLES = new Set([
  "humanoid.root", "humanoid.spine.lower", "humanoid.spine.upper", "humanoid.neck",
  "humanoid.head", "humanoid.clavicle.left", "humanoid.arm.upper.left",
  "humanoid.arm.lower.left", "humanoid.hip.left", "humanoid.leg.upper.left",
  "humanoid.leg.lower.left", "humanoid.clavicle.right", "humanoid.arm.upper.right",
  "humanoid.arm.lower.right", "humanoid.hip.right", "humanoid.leg.upper.right",
  "humanoid.leg.lower.right",
]);
const SOURCE_FIELDS = {
  p8: new Set([
    "projected_motion_sha256", "bundle_sha256", "camera_sha256", "run_sha256",
    "legacy_motion_sha256", "p7_motion_sha256", "p7_bundle_sha256", "p7_run_sha256",
  ]),
  p5: new Set([
    "target_profile_sha256", "instance_sha256", "run_sha256", "retarget_report_sha256",
    "mesh_regression_sha256", "bundle_sha256",
  ]),
  p3: new Set([
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
    "visuals_sha256", "bundle_sha256",
  ]),
};
const FOOT_SOURCE_FIELDS = new Set([
  "projected_motion_sha256", "projected_bundle_sha256", "camera_sha256",
  "p7_motion_sha256", "p7_bundle_sha256", "p7_run_sha256", "target_profile_sha256",
  "motion_instance_sha256", "retarget_bundle_sha256", "retarget_run_document_sha256",
  "p3_rig_sha256", "p3_bundle_sha256", "instance_motion_ir_sha256",
  "instance_motion_bundle_sha256",
]);

export const MAX_POLICY_BYTES = 1024 * 1024;
export const MAX_CANDIDATE_BYTES = 16 * 1024 * 1024;

export function parseJsonFile(text, label, maximumBytes) {
  if (new TextEncoder().encode(text).length > maximumBytes) {
    throw new Error(`${label} 超过 ${maximumBytes} bytes 上限`);
  }
  const value = JSON.parse(text);
  return object(value, label);
}

export function validateDepthPolicyInput(raw) {
  const proposal = raw.format === "autospine-depth-pair-policy-proposal";
  const approved = raw.format === "autospine-depth-pair-policy";
  if (!proposal && !approved) throw new Error("不支持的 depth policy 格式");
  exact(raw, new Set([
    "format", "format_version", "policy_id", "project_id", "clip_id", "source",
    "review", "hysteresis", "pairs", ...(proposal ? ["proposal"] : []),
  ]), "Depth policy");
  if (raw.format_version !== 1) throw new Error("Depth policy 版本必须为 1");
  for (const key of ["policy_id", "project_id", "clip_id"]) identifier(raw[key], key);
  validateSource(raw.source);
  validateHysteresis(raw.hysteresis);
  validatePairs(raw.pairs);
  const review = object(raw.review, "review");
  exact(review, new Set(["status", "method"]), "review");
  if (proposal) {
    if (review.status !== "pending_human_review" || review.method !== "human") {
      throw new Error("Depth policy 草案必须保持 pending_human_review/human");
    }
    object(raw.proposal, "proposal");
  } else if (review.status !== "approved" || review.method !== "human") {
    throw new Error("正式 Depth policy 必须已由人工批准");
  }
  return { document: raw, proposal, approved };
}

export function approveDepthPolicy(proposal) {
  const checked = validateDepthPolicyInput(proposal);
  if (!checked.proposal) throw new Error("只能把待复核草案投影为正式 policy");
  return {
    format: "autospine-depth-pair-policy",
    format_version: proposal.format_version,
    policy_id: proposal.policy_id,
    project_id: proposal.project_id,
    clip_id: proposal.clip_id,
    source: structuredClone(proposal.source),
    review: { status: "approved", method: "human" },
    hysteresis: structuredClone(proposal.hysteresis),
    pairs: structuredClone(proposal.pairs),
  };
}

export function unwrapCandidate(raw, kind) {
  const expected = kind === "foot" ? "autospine-foot-lock-candidates" : "autospine-depth-order-candidates";
  if (raw.format === expected) return { document: raw, reportSha256: null };
  const report = raw.report;
  if (!report || report.format !== expected) throw new Error(`文件不是 ${expected} 或其 CLI envelope`);
  const reportSha256 = raw.report_sha256;
  sha(reportSha256, `${kind} report_sha256`);
  return { document: report, reportSha256 };
}

export function validateCandidatePair(foot, depth, footSha, depthSha) {
  sha(footSha, "foot report SHA-256");
  sha(depthSha, "depth report SHA-256");
  if (foot.format !== "autospine-foot-lock-candidates" || foot.format_version !== 1) {
    throw new Error("Foot candidates 格式或版本不受支持");
  }
  if (depth.format !== "autospine-depth-order-candidates" || depth.format_version !== 1) {
    throw new Error("Depth candidates 格式或版本不受支持");
  }
  if (foot.project_id !== depth.project_id || foot.clip_id !== depth.clip_id) {
    throw new Error("Foot/Depth project_id 或 clip_id 不一致");
  }
  identifier(foot.project_id, "project_id");
  identifier(foot.clip_id, "clip_id");
  if (!Array.isArray(foot.samples) || foot.samples.length < 2 || foot.samples.length > 4096) {
    throw new Error("Foot sample 数量无效");
  }
  if (!Array.isArray(depth.pairs) || depth.pairs.length < 1 || depth.pairs.length > 64) {
    throw new Error("Depth pair 数量无效");
  }
  const footSource = object(foot.source, "Foot source");
  exact(footSource, FOOT_SOURCE_FIELDS, "Foot source");
  for (const [field, value] of Object.entries(footSource)) sha(value, `foot.${field}`);
  const depthSource = object(depth.source, "Depth source");
  exact(depthSource, new Set(["p8", "p5", "p3", "depth_pair_policy_sha256"]), "Depth source");
  validateSource({ p8: depthSource.p8, p5: depthSource.p5, p3: depthSource.p3 });
  sha(depthSource.depth_pair_policy_sha256, "depth_pair_policy_sha256");
  if (typeof depth.timing?.loop !== "boolean") throw new Error("Depth timing.loop 必须是 boolean");
  let previousTick = -1;
  for (const sample of foot.samples) {
    if (!Number.isInteger(sample.tick) || sample.tick <= previousTick || !Number.isInteger(sample.source_frame_index)) throw new Error("Foot sample tick/frame 必须是递增整数");
    if (!["unconstrained", "candidate", "rejected_limit", "rejected_conflict"].includes(sample.state)) throw new Error("Foot sample state 无效");
    previousTick = sample.tick;
  }
  const firstSamples = depth.pairs[0]?.samples;
  if (!Array.isArray(firstSamples) || firstSamples.length !== foot.samples.length) {
    throw new Error("Foot/Depth 帧计划长度不一致");
  }
  if (foot.samples.some((row, index) => row.tick !== firstSamples[index]?.tick)) {
    throw new Error("Foot/Depth tick 计划不一致");
  }
  crossSources(foot.source, depth.source);
  let previousPair = "";
  for (const pair of depth.pairs) {
    validateDepthCandidatePair(pair, foot.samples);
    if (pair.pair_id <= previousPair) throw new Error("Depth candidate pairs 必须唯一排序");
    previousPair = pair.pair_id;
  }
  return {
    footSha256: footSha,
    depthSha256: depthSha,
    projectId: foot.project_id,
    clipId: foot.clip_id,
    loop: Boolean(depth.timing?.loop),
    source: {
      foot_lock_candidates_sha256: footSha,
      depth_order_candidates_sha256: depthSha,
      depth_pair_policy_sha256: depth.source.depth_pair_policy_sha256,
      p8: structuredClone(depth.source.p8),
      p5: structuredClone(depth.source.p5),
      p3: structuredClone(depth.source.p3),
    },
  };
}

export function validatePolicyCandidateBinding(policy, depth, approvedPolicySha256) {
  sha(approvedPolicySha256, "approved depth policy SHA-256");
  if (approvedPolicySha256 !== depth.source?.depth_pair_policy_sha256) {
    throw new Error("已批准 policy SHA 与 Depth candidates 的 policy SHA 不一致");
  }
  if (policy.project_id !== depth.project_id || policy.clip_id !== depth.clip_id) {
    throw new Error("已批准 policy 与 Depth candidates 的 project/clip 不一致");
  }
  for (const stage of ["p8", "p5", "p3"]) {
    for (const field of SOURCE_FIELDS[stage]) {
      if (policy.source[stage][field] !== depth.source?.[stage]?.[field]) {
        throw new Error(`已批准 policy 与 Depth candidates 的 ${stage}.${field} 不一致`);
      }
    }
  }
  const hysteresisFields = ["unit", "enter_threshold", "exit_threshold", "minimum_hold_frames"];
  if (hysteresisFields.some((field) => policy.hysteresis[field] !== depth.hysteresis?.[field])) {
    throw new Error("已批准 policy 与 Depth candidates 的 hysteresis 不一致");
  }
  if (policy.pairs.length !== depth.pairs?.length) {
    throw new Error("已批准 policy 与 Depth candidates 的 pair 数量不一致");
  }
  for (let index = 0; index < policy.pairs.length; index += 1) {
    const expected = policy.pairs[index];
    const actual = depth.pairs[index];
    if (expected.pair_id !== actual?.pair_id || expected.setup_front_slot !== actual?.setup_front_slot ||
        expected.slots.length !== actual?.slots?.length || expected.slots.some((slot, slotIndex) => (
          slot.slot_id !== actual.slots[slotIndex]?.slot_id ||
          slot.depth_role !== actual.slots[slotIndex]?.depth_role
        ))) {
      throw new Error(`已批准 policy 与 Depth candidates 的 pair[${index}] 不一致`);
    }
  }
}

function validateHysteresis(row) {
  object(row, "hysteresis");
  exact(row, new Set(["unit", "enter_threshold", "exit_threshold", "minimum_hold_frames"]), "hysteresis");
  const enter = finite(row.enter_threshold, "enter_threshold");
  const exit = finite(row.exit_threshold, "exit_threshold");
  if (row.unit !== "root_reference_normalized_depth" || !(enter > exit && exit >= 0 && enter <= 1024)) {
    throw new Error("Depth hysteresis 阈值或单位无效");
  }
  if (!Number.isInteger(row.minimum_hold_frames) || row.minimum_hold_frames < 1 || row.minimum_hold_frames > 4096) {
    throw new Error("minimum_hold_frames 无效");
  }
}

function validatePairs(rows) {
  if (!Array.isArray(rows) || rows.length < 1 || rows.length > 64) throw new Error("Depth pair 数量无效");
  let previous = "";
  for (const row of rows) {
    exact(object(row, "pair"), new Set(["pair_id", "slots", "setup_front_slot"]), "pair");
    identifier(row.pair_id, "pair_id");
    if (row.pair_id <= previous) throw new Error("Depth pairs 必须按 pair_id 唯一排序");
    previous = row.pair_id;
    if (!Array.isArray(row.slots) || row.slots.length !== 2) throw new Error("每个 pair 必须恰有两个 slots");
    const slotIds = row.slots.map((slot) => {
      exact(object(slot, "slot"), new Set(["slot_id", "depth_role"]), "slot");
      identifier(slot.slot_id, "slot_id");
      if (!ROLES.has(slot.depth_role)) throw new Error("depth_role 不是 canonical role");
      return slot.slot_id;
    });
    if (slotIds[0] >= slotIds[1] || !slotIds.includes(row.setup_front_slot)) throw new Error("Slot 顺序或 setup front 无效");
  }
}

function validateSource(source) {
  object(source, "source");
  exact(source, new Set(["p8", "p5", "p3"]), "source");
  for (const stage of ["p8", "p5", "p3"]) {
    const row = object(source[stage], stage);
    exact(row, SOURCE_FIELDS[stage], `${stage} source`);
    for (const [key, value] of Object.entries(row)) sha(value, `${stage}.${key}`);
  }
}

function validateDepthCandidatePair(pair, footSamples) {
  identifier(pair.pair_id, "depth pair_id");
  if (!Array.isArray(pair.slots) || pair.slots.length !== 2) throw new Error("Depth candidate slots 无效");
  const ids = pair.slots.map((slot) => (identifier(slot.slot_id, "depth slot"), slot.slot_id));
  if (!ids.includes(pair.setup_front_slot)) throw new Error("Depth setup_front_slot 不在 pair 内");
  if (!Array.isArray(pair.samples) || pair.samples.length !== footSamples.length) throw new Error("Depth pair 帧计划不完整");
  if (pair.samples.some((sample, index) => sample.tick !== footSamples[index].tick)) throw new Error("Depth pair tick 计划不一致");
  if (!Array.isArray(pair.events) || pair.events.length > 4096) throw new Error("Depth events 数量无效");
  for (const event of pair.events) {
    if (!ids.includes(event.from_front_slot) || !ids.includes(event.to_front_slot)) throw new Error("Depth event slot 不在 pair 内");
    if (!Number.isInteger(event.tick) || !Number.isInteger(event.source_frame_index)) throw new Error("Depth event tick/frame 必须是整数");
  }
}

function crossSources(left, right) {
  const pairs = [
    ["projected_motion_sha256", "p8", "projected_motion_sha256"], ["projected_bundle_sha256", "p8", "bundle_sha256"],
    ["camera_sha256", "p8", "camera_sha256"], ["p7_motion_sha256", "p8", "p7_motion_sha256"],
    ["p7_motion_sha256", "p8", "legacy_motion_sha256"],
    ["p7_bundle_sha256", "p8", "p7_bundle_sha256"], ["p7_run_sha256", "p8", "p7_run_sha256"],
    ["target_profile_sha256", "p5", "target_profile_sha256"], ["motion_instance_sha256", "p5", "instance_sha256"],
    ["retarget_bundle_sha256", "p5", "bundle_sha256"], ["retarget_run_document_sha256", "p5", "run_sha256"],
    ["p3_rig_sha256", "p3", "rig_sha256"], ["p3_bundle_sha256", "p3", "bundle_sha256"],
    ["instance_motion_ir_sha256", "p8", "p7_motion_sha256"], ["instance_motion_bundle_sha256", "p8", "p7_bundle_sha256"],
  ];
  if (pairs.some(([a, stage, b]) => left?.[a] !== right?.[stage]?.[b])) throw new Error("Foot/Depth P8/P5/P3 exact source chain 不一致");
  sha(right?.depth_pair_policy_sha256, "depth_pair_policy_sha256");
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} 必须是对象`);
  return value;
}
function exact(value, expected, label) {
  const actual = new Set(Object.keys(value));
  if (actual.size !== expected.size || [...actual].some((key) => !expected.has(key))) throw new Error(`${label} 字段不受支持`);
}
function identifier(value, label) {
  if (typeof value !== "string" || !ID.test(value)) throw new Error(`${label} 不是安全标识符`);
}
function sha(value, label) {
  if (typeof value !== "string" || !SHA.test(value)) throw new Error(`${label} 不是小写 SHA-256`);
}
function finite(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} 必须是有限数字`);
  return value;
}
