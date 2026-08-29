const METRICS = [
  ["correctionX", (row) => row.correctionX, true],
  ["correctionY", (row) => row.correctionY, true],
  ["correctionMagnitude", (row) => row.correctionMagnitude, false],
  ["correctionReferenceRatio", (row) => row.correctionReferenceRatio, false],
  ["maximumResidualPx", (row) => row.maximumResidualPx, false],
  ["jumpPx", (row) => row.jumpPx, false],
];
export function buildMotionPolicyEvidenceModel(inventory, { maxOrdinaryItems = 24 } = {}) {
  if (!Number.isInteger(maxOrdinaryItems) || maxOrdinaryItems < 1 || maxOrdinaryItems > 24) {
    throw new Error("普通复核区间上限必须是 1–24");
  }
  const foot = inventory?.evidence?.foot;
  const depth = inventory?.evidence?.depth;
  if (!foot || !Array.isArray(foot.samples) || !depth || !Array.isArray(depth.pairs) ||
      !Array.isArray(inventory?.candidates)) throw new Error("候选证据不完整");
  const candidatesById = candidateMap(inventory.candidates);
  const samples = normalizeSamples(foot.samples, inventory.candidates);
  const contactSegments = deriveContactSegments(samples);
  addJumps(samples);
  const { metrics, windows: attentionWindows } = deriveAttention(samples, contactSegments);
  const reviewSegments = [
    ...footReviewSegments(samples, attentionWindows, maxOrdinaryItems),
    ...depthReviewSegments(depth, inventory.candidates),
  ].sort(segmentOrder);
  const candidateIds = reviewSegments.flatMap((row) => row.candidateIds);
  requireExactCoverage(candidateIds, candidatesById);
  return {
    snapshotKey: inventory.snapshotKey ?? null, projectId: inventory.projectId ?? null,
    clipId: inventory.clipId ?? null, candidatesById, candidateIds, samples, metrics,
    contractLimits: {
      correctionReferenceRatio: finiteOrNull(foot.policy?.correction_limit?.maximum),
      maximumResidualPx: finiteOrNull(foot.policy?.residual_limit?.maximum),
      referencePx: finiteOrNull(foot.reference?.value_px),
      depthEnterThreshold: finiteOrNull(depth.hysteresis?.enter_threshold),
      depthExitThreshold: finiteOrNull(depth.hysteresis?.exit_threshold),
      depthMinimumHoldFrames: Number.isInteger(depth.hysteresis?.minimum_hold_frames)
        ? depth.hysteresis.minimum_hold_frames : null,
    },
    contactSegments, attentionWindows, reviewSegments,
  };
}
function candidateMap(candidates) {
  const result = new Map();
  for (const candidate of candidates) {
    if (!candidate || typeof candidate.candidateId !== "string" || result.has(candidate.candidateId) ||
        !["foot_lock", "depth_order"].includes(candidate.kind)) {
      throw new Error("候选身份无效或重复");
    }
    result.set(candidate.candidateId, candidate);
  }
  return result;
}
function normalizeSamples(rawSamples, candidates) {
  const footByTime = new Map();
  for (const candidate of candidates.filter((row) => row.kind === "foot_lock")) {
    const key = timeKey(candidate.sourceFrameIndex, candidate.tick);
    if (footByTime.has(key)) throw new Error("同一帧存在重复 Foot candidate");
    footByTime.set(key, candidate);
  }
  const ordered = [...rawSamples].sort(timeOrder);
  const seen = new Set();
  return ordered.map((raw, sampleIndex) => {
    const key = timeKey(raw.source_frame_index, raw.tick);
    if (seen.has(key)) throw new Error("Foot evidence 帧时间重复");
    seen.add(key);
    const candidate = footByTime.get(key) || null;
    if ((raw.state === "unconstrained") === Boolean(candidate)) {
      throw new Error("Foot evidence 与 exact candidate 清单不一致");
    }
    const correction = vectorOrNull(raw.correction_candidate_px);
    return {
      sampleIndex, sourceFrameIndex: raw.source_frame_index, tick: raw.tick,
      supportState: raw.support_state, state: raw.state,
      activeContactIds: Array.isArray(raw.active_contact_ids) ? [...raw.active_contact_ids] : [],
      observations: structuredClone(raw.observations || []),
      candidateId: candidate?.candidateId ?? null,
      correctionX: correction?.[0] ?? null, correctionY: correction?.[1] ?? null,
      correctionMagnitude: finiteOrNull(raw.correction_magnitude_px),
      correctionReferenceRatio: finiteOrNull(raw.correction_reference_ratio),
      maximumResidualPx: finiteOrNull(raw.maximum_residual_px), jumpPx: null,
    };
  });
}
function deriveContactSegments(samples) {
  const result = [];
  let start = 0;
  for (let index = 1; index <= samples.length; index += 1) {
    if (index < samples.length && samePhase(samples[index - 1], samples[index])) continue;
    const first = samples[start];
    const last = samples[index - 1];
    const segment = {
      segmentId: `contact-${String(result.length + 1).padStart(3, "0")}`,
      startSampleIndex: start, endSampleIndex: index - 1,
      startFrame: first.sourceFrameIndex, endFrame: last.sourceFrameIndex,
      startTick: first.tick, endTick: last.tick, sampleCount: index - start,
      supportState: first.supportState, state: first.state,
      activeContactIds: [...first.activeContactIds],
    };
    for (let cursor = start; cursor < index; cursor += 1) samples[cursor].contactSegmentId = segment.segmentId;
    result.push(segment);
    start = index;
  }
  return result;
}
function addJumps(samples) {
  for (let index = 1; index < samples.length; index += 1) {
    const left = samples[index - 1];
    const right = samples[index];
    if (left.contactSegmentId !== right.contactSegmentId || left.correctionX == null ||
        right.correctionX == null) continue;
    right.jumpPx = Math.hypot(right.correctionX - left.correctionX, right.correctionY - left.correctionY);
  }
}
function deriveAttention(samples, contactSegments) {
  const marks = new Map();
  const mark = (index, reason) => {
    if (!marks.has(index)) marks.set(index, new Set());
    marks.get(index).add(reason);
  };
  for (const segment of contactSegments) {
    mark(segment.startSampleIndex, "boundary");
    mark(segment.endSampleIndex, "boundary");
  }
  samples.forEach((row, index) => {
    if (String(row.state).startsWith("rejected_")) mark(index, row.state);
    if (index && row.contactSegmentId === samples[index - 1].contactSegmentId) {
      for (const field of ["correctionX", "correctionY"]) {
        const left = samples[index - 1][field];
        const right = row[field];
        if (left != null && right != null && ((left < 0 && right >= 0) || (left > 0 && right <= 0))) {
          mark(index, `zero:${field}`);
        }
      }
    }
  });
  const metrics = {};
  for (const [name, read, absolute] of METRICS) {
    const rows = metricRows(samples, read, absolute);
    metrics[name] = metricSummary(rows, absolute);
    if (!rows.length) continue;
    const byValue = [...rows].sort((a, b) => a.value - b.value || a.index - b.index);
    mark(byValue[0].index, `extreme:${name}:min`);
    mark(byValue.at(-1).index, `extreme:${name}:max`);
    const scores = rows.map((row) => row.score);
    const threshold = percentile(scores, 0.95);
    if (Math.max(...scores) > Math.min(...scores)) {
      rows.filter((row) => row.score >= threshold).forEach((row) => mark(
        row.index, name === "jumpPx" ? "jump:p95" : `p95:${name}`,
      ));
    }
  }
  return { metrics, windows: mergeAttention(marks, samples) };
}
function mergeAttention(marks, samples) {
  const ranges = [...marks].sort((a, b) => a[0] - b[0]).map(([index, reasons]) => ({
    start: Math.max(0, index - 1), end: Math.min(samples.length - 1, index + 1), reasons: new Set(reasons),
  }));
  const merged = [];
  for (const range of ranges) {
    const previous = merged.at(-1);
    if (!previous || range.start > previous.end + 1) merged.push(range);
    else {
      previous.end = Math.max(previous.end, range.end);
      range.reasons.forEach((reason) => previous.reasons.add(reason));
    }
  }
  return merged.map((range, index) => segmentShape(
    `attention-${String(index + 1).padStart(3, "0")}`,
    "foot_lock", samples.slice(range.start, range.end + 1), true, [...range.reasons].sort(),
    { startSampleIndex: range.start, endSampleIndex: range.end },
  ));
}
function footReviewSegments(samples, windows, maximum) {
  const covered = new Set();
  const result = windows.map((window, index) => {
    for (let cursor = window.startSampleIndex; cursor <= window.endSampleIndex; cursor += 1) covered.add(cursor);
    return segmentShape(`foot-attention-${String(index + 1).padStart(3, "0")}`, "foot_lock",
      samples.slice(window.startSampleIndex, window.endSampleIndex + 1), true, window.reasons);
  });
  let batch = [];
  const flush = () => {
    if (!batch.length) return;
    result.push(segmentShape(`foot-ordinary-${String(result.filter((row) => !row.attention).length + 1).padStart(3, "0")}`,
      "foot_lock", batch, false, []));
    batch = [];
  };
  samples.forEach((row, index) => {
    if (covered.has(index) || !row.candidateId ||
        (batch.length && batch.at(-1).contactSegmentId !== row.contactSegmentId)) flush();
    if (!covered.has(index) && row.candidateId) batch.push(row);
    if (batch.length === maximum) flush();
  });
  flush();
  return result;
}
function depthReviewSegments(depth, candidates) {
  const byPair = new Map(depth.pairs.map((pair) => [pair.pair_id, []]));
  for (const candidate of candidates.filter((row) => row.kind === "depth_order")) {
    if (!byPair.has(candidate.pairId)) throw new Error("Depth candidate pair 不在 exact evidence 中");
    byPair.get(candidate.pairId).push(candidate);
  }
  return depth.pairs.map((pair, index) => {
    const rows = byPair.get(pair.pair_id).sort(timeOrder);
    for (const candidate of rows) {
      const event = pair.events?.[candidate.eventIndex];
      if (!event || event.tick !== candidate.tick || event.source_frame_index !== candidate.sourceFrameIndex) {
        throw new Error("Depth event 与 exact candidate 不一致");
      }
    }
    const times = rows.length ? rows : [...(pair.samples || [])].sort(timeOrder).map((row) => ({
      sourceFrameIndex: row.source_frame_index, tick: row.tick,
    }));
    return segmentShape(`depth-pair-${String(index + 1).padStart(3, "0")}`, "depth_order", times,
      rows.length > 0, [rows.length ? "depth_pair_events" : "depth_pair_no_events"], {
        pairId: pair.pair_id, candidateIds: rows.map((row) => row.candidateId),
        metrics: {
          eventCount: rows.length, sampleCount: pair.samples?.length || 0,
          scoreDelta: metricSummary(metricRows(pair.samples || [], (row) => row.score_delta_first_minus_second, true), true),
        },
      });
  });
}
function segmentShape(segmentId, kind, rows, attention, reasons, extra = {}) {
  const first = rows[0] || {};
  const last = rows.at(-1) || first;
  const states = uniqueValues(rows.map((row) => row.state));
  const supportStates = uniqueValues(rows.map((row) => row.supportState));
  return {
    segmentId, kind, attention, reasons: [...reasons],
    startFrame: first.sourceFrameIndex ?? first.source_frame_index ?? null,
    endFrame: last.sourceFrameIndex ?? last.source_frame_index ?? null,
    startTick: first.tick ?? null, endTick: last.tick ?? null,
    candidateIds: extra.candidateIds || rows.map((row) => row.candidateId).filter(Boolean),
    states, supportStates,
    rejectedCount: rows.filter((row) => String(row.state).startsWith("rejected_")).length,
    metrics: extra.metrics || summarizeRows(rows), ...extra,
  };
}
function summarizeRows(rows) {
  return Object.fromEntries(METRICS.map(([name, read, absolute]) => [
    name, metricSummary(metricRows(rows, read, absolute), absolute),
  ]));
}
function metricRows(rows, read, absolute) {
  return rows.map((row, index) => ({ index: row.sampleIndex ?? index, value: read(row) }))
    .filter((row) => Number.isFinite(row.value))
    .map((row) => ({ ...row, score: absolute ? Math.abs(row.value) : row.value }));
}
function metricSummary(rows, absolute = false) {
  if (!rows.length) return { count: 0, minimum: null, maximum: null, p95: null, p95Mode: absolute ? "absolute" : "value" };
  const values = rows.map((row) => row.value);
  return {
    count: rows.length, minimum: Math.min(...values), maximum: Math.max(...values),
    p95: percentile(rows.map((row) => row.score), 0.95),
    p95Mode: absolute ? "absolute" : "value",
  };
}
function percentile(values, quantile) {
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * quantile;
  const lower = Math.floor(position); const upper = Math.ceil(position);
  return lower === upper ? sorted[lower] : sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}
function samePhase(left, right) {
  return right.sourceFrameIndex === left.sourceFrameIndex + 1 && right.tick > left.tick &&
    right.supportState === left.supportState && right.state === left.state &&
    right.activeContactIds.join("\u0000") === left.activeContactIds.join("\u0000");
}
function requireExactCoverage(ids, candidatesById) {
  const unique = new Set(ids);
  if (ids.length !== candidatesById.size || unique.size !== ids.length ||
      [...candidatesById.keys()].some((id) => !unique.has(id))) throw new Error("复核分段没有精确且唯一地覆盖候选清单");
}
function segmentOrder(left, right) {
  return (left.startTick ?? Number.MAX_SAFE_INTEGER) - (right.startTick ?? Number.MAX_SAFE_INTEGER) ||
    left.kind.localeCompare(right.kind) || left.segmentId.localeCompare(right.segmentId);
}
function timeOrder(left, right) { return left.tick - right.tick ||
  (left.source_frame_index ?? left.sourceFrameIndex) - (right.source_frame_index ?? right.sourceFrameIndex); }
function timeKey(frame, tick) { return `${frame}|${tick}`; }
function uniqueValues(values) { return [...new Set(values.filter((value) => value != null && value !== ""))]; }
function finiteOrNull(value) { return Number.isFinite(value) ? value : null; }
function vectorOrNull(value) { return Array.isArray(value) && value.length === 2 &&
  value.every(Number.isFinite) ? [...value] : null; }
