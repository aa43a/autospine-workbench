import { reconcileSaveResponse } from "./draft-transactions.js";

const SHA256 = /^[0-9a-f]{64}$/;

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function revision(value) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}

function requireRefreshedProject(project, projectId, savedRevision) {
  if (!plainObject(project) || String(project.id ?? "") !== String(projectId)) {
    throw new Error("刷新响应的项目标识不匹配");
  }
  const overrides = project.overrides;
  const resolved = project.resolved;
  const nextRevision = revision(overrides?.revision);
  if (!plainObject(overrides) || nextRevision == null || nextRevision < savedRevision) {
    throw new Error("刷新响应不是已保存 revision 的权威版本");
  }
  if (
    !plainObject(resolved)
    || resolved.project_id !== projectId
    || revision(resolved.revision) !== nextRevision
    || !SHA256.test(String(resolved.sha256 || ""))
  ) {
    throw new Error("刷新响应缺少权威 resolved snapshot");
  }
  return overrides;
}

function withoutResolvedSnapshot(project) {
  return { ...(plainObject(project) ? project : {}), resolved: null };
}

export async function refreshSavedProject({
  currentProject,
  projectId,
  savedOverrides,
  snapshot,
  requestProject,
  getLiveDraft,
  getEditEpoch,
  draftFromServer,
}) {
  const savedRevision = revision(savedOverrides?.revision);
  if (savedRevision == null) throw new Error("保存响应缺少有效 revision");
  let project;
  let overrides;
  let refreshError = null;
  try {
    project = await requestProject();
    overrides = requireRefreshedProject(project, projectId, savedRevision);
  } catch (error) {
    refreshError = error instanceof Error ? error : new Error(String(error));
    project = withoutResolvedSnapshot(currentProject);
    overrides = savedOverrides;
  }
  const reconciled = reconcileSaveResponse({
    snapshot,
    liveDraft: getLiveDraft(),
    serverDraft: draftFromServer(overrides, snapshot.draft),
    currentEditEpoch: getEditEpoch(),
  });
  return { project, overrides, reconciled, refreshError };
}
