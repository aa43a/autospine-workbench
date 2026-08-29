export const ASSIST_PROFILE = "safe-assist-v1";
export const ASSIST_REASON = "assisted-foot-safe-v1";
const SAFETY_RATIO = 0.8;

export function isSafeAssistedCandidate(candidate, model) {
  if (!candidate || candidate.kind !== "foot_lock" || candidate.footState !== "candidate") return false;
  const sample = model?.samples?.find((row) => row.candidateId === candidate.candidateId);
  const ratioLimit = model?.contractLimits?.correctionReferenceRatio;
  const residualLimit = model?.contractLimits?.maximumResidualPx;
  if (!sample || !positive(ratioLimit) || !positive(residualLimit) ||
      !finite(sample.correctionX) || !finite(sample.correctionY) ||
      !finite(sample.correctionReferenceRatio) || !finite(sample.maximumResidualPx) ||
      sample.correctionReferenceRatio < 0 || sample.maximumResidualPx < 0 ||
      sample.correctionReferenceRatio > ratioLimit * SAFETY_RATIO ||
      sample.maximumResidualPx > residualLimit * SAFETY_RATIO) return false;
  return Array.isArray(sample.observations) && sample.observations.length > 0 &&
    sample.observations.every(validObservation);
}

export function safeCandidateIdsForSampleRange(model, state, startIndex, endIndex) {
  if (!model?.samples?.length || !state?.decisions) return [];
  const start = clampIndex(startIndex, model.samples.length);
  const end = clampIndex(endIndex, model.samples.length);
  const from = Math.min(start, end);
  const to = Math.max(start, end);
  const candidates = model.candidatesById || new Map(
    state.inventory.candidates.map((row) => [row.candidateId, row]),
  );
  const ids = [];
  for (let index = from; index <= to; index += 1) {
    const id = model.samples[index]?.candidateId;
    if (!id || state.decisions.has(id) || ids.includes(id)) continue;
    if (isSafeAssistedCandidate(candidates.get(id), model)) ids.push(id);
  }
  return ids;
}

export function allSafeCandidateIds(model, state) {
  if (!model?.samples?.length || !state?.decisions) return [];
  return safeCandidateIdsForSampleRange(model, state, 0, model.samples.length - 1);
}

export function assistedCoverage(model, state) {
  const candidates = state?.inventory?.candidates || [];
  const safeIds = candidates.filter((row) => isSafeAssistedCandidate(row, model))
    .map((row) => row.candidateId);
  const adopted = safeIds.filter((id) => state.decisions.has(id)).length;
  return {
    total: candidates.length,
    safe: safeIds.length,
    adopted,
    safePending: safeIds.length - adopted,
    exceptions: candidates.length - safeIds.length,
  };
}

function validObservation(row) {
  const current = row?.currentEndpointPx ?? row?.current_endpoint_px;
  const desired = row?.desiredCorrectionPx ?? row?.desired_correction_px;
  const residual = row?.residualMagnitudePx ?? row?.residual_magnitude_px;
  return vector(current) && vector(desired) && finite(residual) && residual >= 0;
}
function vector(value) { return Array.isArray(value) && value.length === 2 && value.every(finite); }
function finite(value) { return Number.isFinite(value); }
function positive(value) { return Number.isFinite(value) && value > 0; }
function clampIndex(value, length) {
  const rounded = Number.isFinite(value) ? Math.round(value) : 0;
  return Math.max(0, Math.min(length - 1, rounded));
}
