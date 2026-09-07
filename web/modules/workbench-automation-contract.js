"use strict";

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SHA = /^[0-9a-f]{64}$/;
const JOB = /^job-[0-9a-f]{32}$/;
export const ACTIVE_JOBS = new Set(["pending", "running"]);
const STATUSES = new Set(["pending", "running", "needs_review", "succeeded", "blocked", "failed", "canceled"]);

export function projectIdentity(context) {
  return ID.test(context.projectId || "") && SHA.test(context.resolvedSha || "")
    ? `${context.projectId}:${context.resolvedSha}` : null;
}

export function automationEndpoint(projectId) {
  if (!ID.test(projectId || "")) throw new Error("invalid_project");
  return `/api/projects/${encodeURIComponent(projectId)}/automation`;
}

export function jobEndpoint(projectId, jobId) {
  if (!JOB.test(jobId || "")) throw new Error("invalid_job");
  return `${automationEndpoint(projectId)}/jobs/${jobId}`;
}

export function readOverview(payload, context) {
  const capabilities = payload?.capabilities;
  const queue = payload?.review_queue;
  for (const value of [capabilities, queue]) {
    if (value?.project_id !== context.projectId || value?.authority !== "none"
      || value?.profile !== "production_review"
      || value?.source_addresses?.resolved_project_sha256 !== context.resolvedSha) {
      throw new Error("project_snapshot_stale");
    }
  }
  if (capabilities.schema !== "autospine.project-capabilities/v1"
    || typeof capabilities.can_build_spine_preview !== "boolean"
    || queue.schema !== "autospine.review-queue/v1" || !Array.isArray(queue.items)) {
    throw new Error("invalid_overview");
  }
  for (const key of ["resolved_project_sha256", "layer_manifest_sha256", "input_identity_sha256"]) {
    if (!SHA.test(capabilities.source_addresses[key] || "")
      || capabilities.source_addresses[key] !== queue.source_addresses[key]) throw new Error("invalid_overview");
  }
  for (const row of queue.items) {
    if (!ID.test(row.entity_id || "") || !["rig", "joint", "semantic", "pivot", "binding", "split"].includes(row.type)
      || !Array.isArray(row.evidence)) throw new Error("invalid_review_item");
    for (const evidence of row.evidence) {
      const base = `/api/projects/${context.projectId}/`;
      if (evidence.kind === "composite_image" && evidence.url === `${base}composite`) continue;
      const match = /^layers\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\/image$/.exec(String(evidence.url).slice(base.length));
      if (evidence.kind !== "layer_image" || !String(evidence.url).startsWith(base) || !match) {
        throw new Error("invalid_evidence");
      }
    }
  }
  return { capabilities, items: queue.items };
}

export function readJob(payload, projectId, expectedJobId = null) {
  if (payload?.schema !== "autospine.pipeline-web-job/v1" || payload.project_id !== projectId
    || payload.authority !== "none" || !JOB.test(payload.job_id || "") || !STATUSES.has(payload.status)
    || expectedJobId && payload.job_id !== expectedJobId) throw new Error("invalid_job");
  if (payload.run && (payload.run.project_id !== projectId || payload.run.authority !== "none"
    || !STATUSES.has(payload.run.status))) throw new Error("invalid_run");
  return payload;
}

export function reviewTarget(item, context) {
  if (item.type === "joint") {
    return context.jointIds?.includes(item.entity_id) ? { type: "joint", id: item.entity_id } : null;
  }
  if (context.layerIds?.includes(item.entity_id)) return { type: "layer", id: item.entity_id };
  // A derived split child retains the parent's image evidence route.
  for (const evidence of item.evidence || []) {
    if (evidence.kind !== "layer_image") continue;
    const match = /\/layers\/([^/]+)\/image$/.exec(evidence.url);
    if (match && context.layerIds?.includes(match[1])) return { type: "layer", id: match[1] };
  }
  return null;
}
