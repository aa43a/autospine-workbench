import { API_BASE, apiRequest } from "./api.js";
import {
  clearMeshEvidence,
  mountMeshEvidenceBrowser,
  renderMeshEvidenceDetail,
  setMeshBundleOptions,
  setMeshEvidenceStatus,
  setMeshRigOptions,
} from "./mesh-evidence-markup.js";
import {
  meshBundleDetailUrl,
  meshBundleImageUrl,
  meshBundlesForRig,
  meshRigOptions,
  normalizeMeshBundleDetail,
  normalizeMeshBundleIndex,
  shortMeshSha,
} from "./mesh-evidence-state.js";

export function createMeshEvidenceBrowser({
  mount,
  request = apiRequest,
  apiBase = API_BASE,
}) {
  const elements = mountMeshEvidenceBrowser(mount);
  let projectId = "";
  let items = [];
  let selectedRig = "";
  let selectedBundle = "";
  let sequence = 0;

  elements.refreshBtn.addEventListener("click", () => loadIndex(projectId));
  elements.rigSelect.addEventListener("change", (event) => {
    sequence += 1;
    elements.refreshBtn.disabled = false;
    selectedRig = String(event.target.value || "");
    selectedBundle = "";
    const bundles = meshBundlesForRig(items, selectedRig);
    setMeshBundleOptions(elements, bundles);
    clearMeshEvidence(elements, selectedRig
      ? "请选择该 RigIR 下的精确 bundle SHA-256。"
      : "请选择 RigIR SHA-256。");
    setMeshEvidenceStatus(elements, "selection", "等待显式选择 bundle 地址。");
  });
  elements.bundleSelect.addEventListener("change", (event) => {
    sequence += 1;
    elements.refreshBtn.disabled = false;
    selectedBundle = String(event.target.value || "");
    elements.loadBtn.disabled = !selectedRig || !selectedBundle;
    clearMeshEvidence(elements, selectedBundle
      ? "地址已选择；点击“读取已验证证据”执行严格校验。"
      : "请选择 Bundle SHA-256。");
    setMeshEvidenceStatus(elements, "selection", "尚未读取所选 bundle。");
  });
  elements.loadBtn.addEventListener("click", loadDetail);

  async function loadIndex(nextProjectId) {
    projectId = String(nextProjectId || "");
    const token = ++sequence;
    items = [];
    selectedRig = "";
    selectedBundle = "";
    setMeshRigOptions(elements, []);
    setMeshBundleOptions(elements, []);
    clearMeshEvidence(elements, projectId
      ? "正在发现已发布的 mesh bundle 地址…"
      : "选择项目后发现已发布的不可变 mesh bundle。");
    if (!projectId) {
      setMeshEvidenceStatus(elements, "idle", "尚未选择项目。");
      elements.refreshBtn.disabled = true;
      return;
    }
    elements.refreshBtn.disabled = true;
    setMeshEvidenceStatus(elements, "loading", "正在读取 mesh bundle 地址列表…");
    try {
      const payload = await request(
        `${apiBase}/${encodeURIComponent(projectId)}/mesh-bundles`,
      );
      if (token !== sequence) return;
      items = normalizeMeshBundleIndex(payload, projectId);
      setMeshRigOptions(elements, meshRigOptions(items));
      setMeshBundleOptions(elements, []);
      if (!items.length) {
        clearMeshEvidence(elements, "该项目尚未发布 P3 mesh bundle。");
        setMeshEvidenceStatus(elements, "empty", "没有可发现的 mesh bundle 地址。");
      } else {
        clearMeshEvidence(elements, "请选择 RigIR SHA-256；工作台不会自动采用第一项。");
        setMeshEvidenceStatus(
          elements, "selection", `发现 ${items.length} 个不可变双 SHA 地址。`,
        );
      }
    } catch (error) {
      if (token !== sequence) return;
      clearMeshEvidence(elements, "无法读取 mesh bundle 地址；可使用刷新按钮重试。");
      setMeshEvidenceStatus(
        elements, "error", `Mesh bundle 地址加载失败：${error.message || "未知错误"}`,
      );
    } finally {
      if (token === sequence) elements.refreshBtn.disabled = false;
    }
  }

  async function loadDetail() {
    if (!selectedRig || !selectedBundle || !projectId) return;
    const bound = { projectId, rigSha: selectedRig, bundleSha: selectedBundle };
    if (!items.some((item) => item.rig_sha256 === bound.rigSha
        && item.bundle_sha256 === bound.bundleSha)) return;
    const token = ++sequence;
    elements.loadBtn.disabled = true;
    elements.refreshBtn.disabled = true;
    clearMeshEvidence(elements, "正在重算并验证所选 mesh bundle…");
    setMeshEvidenceStatus(elements, "loading", "正在执行完整性验证…");
    try {
      const payload = await request(meshBundleDetailUrl(
        apiBase, bound.projectId, bound.rigSha, bound.bundleSha,
      ));
      if (token !== sequence) return;
      const detail = normalizeMeshBundleDetail(payload, bound);
      renderMeshEvidenceDetail(elements, detail, (pngSha) => meshBundleImageUrl(
        apiBase, bound.projectId, bound.rigSha, bound.bundleSha, pngSha,
      ));
      const summary = detail.status === "reviewed-noop"
        ? "已验证 no-op bundle" : `已验证 ${detail.hinges.length} 个 hinge`;
      setMeshEvidenceStatus(
        elements, "ready",
        `${summary} · ${shortMeshSha(bound.rigSha)}/${shortMeshSha(bound.bundleSha)}`,
      );
    } catch (error) {
      if (token !== sequence) return;
      clearMeshEvidence(elements, "所选 bundle 未通过读取或完整性验证。");
      setMeshEvidenceStatus(
        elements, "error", `Mesh bundle 验证失败：${error.message || "未知错误"}`,
      );
    } finally {
      if (token === sequence) {
        elements.loadBtn.disabled = !selectedRig || !selectedBundle;
        elements.refreshBtn.disabled = false;
      }
    }
  }

  return { elements, syncProject: loadIndex, loadDetail };
}

export function bootstrapMeshEvidenceBrowser(root = document) {
  const projectSelect = root.getElementById("projectSelect");
  const inspector = root.querySelector(".inspector-panel");
  if (!projectSelect || !inspector) return null;
  let mount = root.getElementById("meshEvidenceMount");
  if (!mount) {
    mount = root.createElement("div");
    mount.id = "meshEvidenceMount";
    const notes = inspector.querySelector(".notes-section");
    if (notes) inspector.insertBefore(mount, notes);
    else inspector.append(mount);
  }
  const browser = createMeshEvidenceBrowser({ mount });
  let current = null;
  const sync = () => {
    const next = projectSelect.disabled ? "" : String(projectSelect.value || "");
    if (next === current) return;
    current = next;
    browser.syncProject(next);
  };
  projectSelect.addEventListener("change", sync);
  const observer = new MutationObserver(sync);
  observer.observe(projectSelect, { attributes: true, childList: true, subtree: true });
  queueMicrotask(sync);
  return { ...browser, observer };
}

if (typeof document !== "undefined") bootstrapMeshEvidenceBrowser(document);
