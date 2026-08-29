import { deriveCandidateId } from "./motion-policy-hash.js";

export async function deriveInventory(foot, footSha, depth, depthSha) {
  const footRows = foot.samples.filter((row) => row.state !== "unconstrained");
  const feet = await Promise.all(footRows.map(async (sample) => ({
    candidateId: await deriveCandidateId("foot_lock", {
      report_sha256: footSha,
      source_frame_index: sample.source_frame_index,
      tick: sample.tick,
    }),
    kind: "foot_lock",
    tick: sample.tick,
    sourceFrameIndex: sample.source_frame_index,
    footState: sample.state,
    sample,
  })));
  const depthPromises = [];
  for (const pair of depth.pairs) {
    pair.events.forEach((event, eventIndex) => depthPromises.push((async () => ({
      candidateId: await deriveCandidateId("depth_order", {
        report_sha256: depthSha,
        pair_id: pair.pair_id,
        event_index: eventIndex,
        source_frame_index: event.source_frame_index,
        tick: event.tick,
        from_front_slot: event.from_front_slot,
        to_front_slot: event.to_front_slot,
      }),
      kind: "depth_order",
      tick: event.tick,
      sourceFrameIndex: event.source_frame_index,
      pairId: pair.pair_id,
      eventIndex,
      slots: pair.slots.map((slot) => slot.slot_id),
      event,
    }))()));
  }
  const candidates = feet.concat(await Promise.all(depthPromises));
  candidates.sort((a, b) => a.candidateId.localeCompare(b.candidateId));
  if (new Set(candidates.map((row) => row.candidateId)).size !== candidates.length) {
    throw new Error("Candidate identity collision");
  }
  return {
    candidates,
    unconstrainedTicks: foot.samples.filter((row) => row.state === "unconstrained").map((row) => row.tick),
    evidence: {
      foot: structuredClone({
        policy: foot.policy,
        reference: foot.reference,
        summary: foot.summary,
        timing: foot.timing,
        samples: foot.samples,
      }),
      depth: structuredClone({
        hysteresis: depth.hysteresis,
        summary: depth.summary,
        timing: depth.timing,
        pairs: depth.pairs,
      }),
    },
  };
}
