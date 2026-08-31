import {
  applyDraftPatch,
  captureSaveSnapshot,
  createDraftPatch,
  createLocalPatchArtifact,
  reconcileSaveResponse,
} from "../modules/draft-transactions.js";
import { createSkeletonRenderer } from "../modules/skeleton-renderer.js";

const results = document.getElementById("results");
let failures = 0;

function assert(name, condition, detail = "") {
  const item = document.createElement("li");
  item.className = condition ? "pass" : "fail";
  item.textContent = `${condition ? "PASS" : "FAIL"}: ${name}${detail ? ` — ${detail}` : ""}`;
  results.append(item);
  if (!condition) failures += 1;
}

const sentDraft = {
  joint_overrides: { elbow: { x: 10, y: 20 } },
  layer_overrides: {},
  notes: "sent",
};
const snapshot = captureSaveSnapshot({
  projectId: "sample",
  baseRevision: 2,
  editEpoch: 7,
  draft: sentDraft,
});
const liveDraft = {
  joint_overrides: { elbow: { x: 42, y: 20 } },
  layer_overrides: { sleeve: { disposition: "split" } },
  notes: "edited while saving",
};
const serverDraft = {
  joint_overrides: { elbow: { x: 10, y: 20, reason: "normalized" } },
  layer_overrides: {},
  notes: "sent",
};
const reconciled = reconcileSaveResponse({
  snapshot,
  liveDraft,
  serverDraft,
  currentEditEpoch: 10,
});

assert("保存期间的新关节位置不会被响应覆盖", reconciled.draft.joint_overrides.elbow.x === 42);
assert("服务端未冲突的规范化字段会被保留", reconciled.draft.joint_overrides.elbow.reason === "normalized");
assert("保存期间的新图层决策会保留", reconciled.draft.layer_overrides.sleeve.disposition === "split");
assert("editEpoch 改变后仍保持 dirty", reconciled.hasPendingEdits === true);

const removalPatch = createDraftPatch(
  { joint_overrides: { wrist: { x: 1, y: 2 } }, notes: "old" },
  { joint_overrides: {}, notes: "new" },
);
const replayed = applyDraftPatch(
  { joint_overrides: { wrist: { x: 9, y: 9 }, hip: { x: 3, y: 4 } }, notes: "remote" },
  removalPatch,
);
assert("重放可表达恢复自动位置（删除 override）", !("wrist" in replayed.joint_overrides));
assert("重放不会删除无关的远端校正", replayed.joint_overrides.hip.x === 3);
assert("重叠字段按本地命令覆盖", replayed.notes === "new");

const artifact = createLocalPatchArtifact({
  projectId: "sample",
  baseRevision: 2,
  baseDraft: sentDraft,
  currentDraft: liveDraft,
});
assert("导出 patch 带项目和基线 revision", artifact.project_id === "sample" && artifact.base_revision === 2);
assert("导出 patch 包含可重放命令", artifact.operations.length > 0);

const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
const boneGroup = document.createElementNS(svg.namespaceURI, "g");
const jointGroup = document.createElementNS(svg.namespaceURI, "g");
svg.append(boneGroup, jointGroup);
document.body.append(svg);
const renderer = createSkeletonRenderer({
  boneGroup,
  jointGroup,
  skeletonSvg: svg,
  clamp: (value, min, max) => Math.min(max, Math.max(min, value)),
  numberOr: (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback,
  formatConfidence: (value) => `${Math.round(Number(value) * 100)}%`,
  onJointPointerDown: () => {},
  onSelectJoint: () => {},
});
const renderSkeleton = (x) => renderer.render({
  visible: true,
  hasProject: true,
  joints: [{ id: "elbow", x, y: 20, confidence: 0.9 }],
  bones: [],
  selectedJointId: "elbow",
  canvasSize: { width: 100, height: 100 },
});
renderSkeleton(10);
const focusedHandle = jointGroup.firstElementChild;
focusedHandle.focus();
renderSkeleton(11);
assert("骨骼更新复用 keyed 关节节点", jointGroup.firstElementChild === focusedHandle);
assert("骨骼重绘后键盘焦点仍在关节上", document.activeElement === focusedHandle);
svg.remove();

document.title = failures ? `${failures} failed — Draft transaction tests` : "PASS — Draft transaction tests";
