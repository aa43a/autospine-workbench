import { shortMeshSha } from "./mesh-evidence-state.js";

export function mountMeshEvidenceBrowser(mount) {
  const doc = mount.ownerDocument || document;
  const section = node(doc, "section", {
    class: "inspector-section mesh-evidence",
    id: "meshEvidence",
    "aria-labelledby": "meshEvidenceHeading",
  });
  const heading = node(doc, "div", { class: "section-heading-row" });
  const title = node(doc, "h3", { id: "meshEvidenceHeading" }, "P3 Mesh 证据");
  const badge = node(doc, "span", {
    class: "mesh-evidence-badge", "data-status": "idle",
  }, "只读");
  heading.append(title, badge);

  const intro = node(doc, "p", { class: "mesh-evidence-intro" },
    "显式选择 RigIR 与 bundle 的内容地址；读取不会写入校正或复用决定。");
  const status = node(doc, "p", {
    class: "mesh-evidence-status", id: "meshEvidenceStatus",
    role: "status", "aria-live": "polite", "data-kind": "idle",
  }, "选择项目后发现已发布的不可变 mesh bundle。");

  const controls = node(doc, "div", {
    class: "mesh-evidence-controls", "aria-label": "P3 mesh bundle 精确地址",
  });
  const rigLabel = node(doc, "label", { for: "meshEvidenceRigSelect" });
  const rigSelect = node(doc, "select", { id: "meshEvidenceRigSelect" });
  rigSelect.disabled = true;
  rigLabel.append(node(doc, "span", {}, "RigIR SHA-256"), rigSelect);
  const bundleLabel = node(doc, "label", { for: "meshEvidenceBundleSelect" });
  const bundleSelect = node(doc, "select", { id: "meshEvidenceBundleSelect" });
  bundleSelect.disabled = true;
  bundleLabel.append(node(doc, "span", {}, "Bundle SHA-256"), bundleSelect);
  const actions = node(doc, "div", { class: "mesh-evidence-actions" });
  const loadBtn = node(doc, "button", {
    class: "button button-primary", id: "meshEvidenceLoadBtn", type: "button",
  }, "读取已验证证据");
  loadBtn.disabled = true;
  const refreshBtn = node(doc, "button", {
    class: "button button-secondary", id: "meshEvidenceRefreshBtn", type: "button",
  }, "刷新地址列表");
  actions.append(loadBtn, refreshBtn);
  controls.append(rigLabel, bundleLabel, actions);

  const identity = node(doc, "dl", {
    class: "mesh-evidence-identities", id: "meshEvidenceIdentities",
    "aria-label": "Bundle 内容身份",
  });
  identity.hidden = true;
  const empty = node(doc, "p", {
    class: "mesh-evidence-empty", id: "meshEvidenceEmpty",
  }, "尚未选择并读取 mesh bundle。");
  const hinges = node(doc, "div", {
    class: "mesh-evidence-hinges", id: "meshEvidenceHinges", role: "list",
    "aria-label": "Hinge mesh 可视证据",
  });
  section.append(heading, intro, status, controls, identity, empty, hinges);
  mount.replaceChildren(section);
  return {
    section, badge, status, rigSelect, bundleSelect, loadBtn, refreshBtn,
    identity, empty, hinges,
  };
}

export function setMeshEvidenceStatus(elements, kind, message) {
  elements.status.dataset.kind = kind;
  elements.status.textContent = message;
  elements.badge.dataset.status = kind;
  elements.badge.textContent = kind === "ready" ? "已验证 · 只读" : "只读";
}

export function setMeshRigOptions(elements, rigShas, selected = "") {
  selectOptions(elements.rigSelect, "请选择 RigIR SHA-256", rigShas, selected);
  elements.rigSelect.disabled = rigShas.length === 0;
}

export function setMeshBundleOptions(elements, bundleShas, selected = "") {
  selectOptions(elements.bundleSelect, "请选择 Bundle SHA-256", bundleShas, selected);
  elements.bundleSelect.disabled = bundleShas.length === 0;
  elements.loadBtn.disabled = !selected;
}

export function clearMeshEvidence(elements, message = "尚未选择并读取 mesh bundle。") {
  elements.identity.hidden = true;
  elements.identity.replaceChildren();
  elements.hinges.replaceChildren();
  elements.empty.hidden = false;
  elements.empty.textContent = message;
}

export function renderMeshEvidenceDetail(elements, detail, imageUrl) {
  const doc = elements.section.ownerDocument;
  elements.identity.replaceChildren();
  for (const [label, key] of [
    ["Base P2 RigIR", "base_rig_sha256"],
    ["Base P2 bundle", "base_bundle_sha256"],
    ["Layer Manifest", "layer_manifest_sha256"],
    ["Resolved snapshot", "resolved_project_sha256"],
    ["P3 mesh RigIR", "rig_sha256"],
    ["Compile run", "run_sha256"],
    ["Action probes", "probes_sha256"],
    ["Visual evidence", "visuals_sha256"],
    ["Published bundle", "bundle_sha256"],
  ]) {
    const row = node(doc, "div", {});
    row.append(node(doc, "dt", {}, label), node(doc, "dd", {}, detail.source[key]));
    elements.identity.append(row);
  }
  elements.identity.hidden = false;
  elements.hinges.replaceChildren();
  if (detail.status === "reviewed-noop") {
    elements.empty.hidden = false;
    elements.empty.textContent = "该发布结果已复核为 no-op：RigIR 中没有 mesh hinge target。";
    return;
  }
  elements.empty.hidden = true;
  for (const hinge of detail.hinges) {
    elements.hinges.append(hingeCard(doc, hinge, imageUrl));
  }
}

function hingeCard(doc, hinge, imageUrl) {
  const card = node(doc, "article", { class: "mesh-evidence-card", role: "listitem" });
  const heading = node(doc, "div", { class: "mesh-evidence-card-heading" });
  heading.append(
    node(doc, "h4", {}, hinge.attachment_id),
    node(doc, "span", {}, hinge.side === "left" ? "角色左侧" : "角色右侧"),
  );
  const safe = hinge.continuous_safe_angle_deg;
  const metrics = node(doc, "dl", { class: "mesh-evidence-metrics" });
  for (const [label, value] of [
    ["网格", `${hinge.vertex_count} 顶点 · ${hinge.triangle_count} 三角形`],
    ["骨链", `${hinge.proximal_bone_id} → ${hinge.distal_bone_id}`],
    ["连续安全角", `${signed(safe.minimum)}° ～ ${signed(safe.maximum)}°`],
  ]) {
    const row = node(doc, "div", {});
    row.append(node(doc, "dt", {}, label), node(doc, "dd", {}, value));
    metrics.append(row);
  }
  const gallery = node(doc, "div", { class: "mesh-evidence-gallery" });
  for (const [key, label] of [
    ["heatmap", "两骨权重热图"], ["setup", "Setup 姿势"],
    ["widest_safe", `最宽安全姿势 ${signed(hinge.images.widest_safe.angle_deg)}°`],
  ]) {
    const evidence = hinge.images[key];
    const figure = node(doc, "figure", {});
    const image = node(doc, "img", {
      src: imageUrl(evidence.png_sha256),
      alt: `${hinge.attachment_id} ${label}`,
      width: evidence.width, height: evidence.height,
      loading: "lazy", decoding: "async",
    });
    figure.append(image, node(doc, "figcaption", {},
      `${label} · ${shortMeshSha(evidence.png_sha256)}`));
    gallery.append(figure);
  }
  card.append(heading, metrics, gallery);
  return card;
}

function selectOptions(select, placeholder, values, selected) {
  const doc = select.ownerDocument;
  select.replaceChildren(node(doc, "option", { value: "" }, placeholder));
  for (const value of values) {
    select.append(node(doc, "option", { value }, `${shortMeshSha(value)} · ${value}`));
  }
  select.value = values.includes(selected) ? selected : "";
}

function signed(value) {
  return Number(value) > 0 ? `+${value}` : String(value);
}

function node(doc, tag, attributes = {}, text = null) {
  const element = doc.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  if (text != null) element.textContent = text;
  return element;
}
