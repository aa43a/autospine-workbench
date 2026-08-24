const SVG_NS = "http://www.w3.org/2000/svg";

function placeAt(parent, element, index) {
  if (parent.children[index] !== element) {
    parent.insertBefore(element, parent.children[index] || null);
  }
}

function removeStale(cache, activeKeys) {
  for (const [key, element] of cache) {
    if (activeKeys.has(key)) continue;
    element.remove();
    cache.delete(key);
  }
}

export function createSkeletonRenderer({
  boneGroup,
  jointGroup,
  skeletonSvg,
  clamp,
  numberOr,
  formatConfidence,
  onJointPointerDown,
  onSelectJoint,
}) {
  const bonesById = new Map();
  const jointsById = new Map();
  const jointParts = new WeakMap();

  function createJoint() {
    const group = document.createElementNS(SVG_NS, "g");
    group.classList.add("joint-handle");
    group.setAttribute("role", "button");
    group.setAttribute("tabindex", "0");

    const title = document.createElementNS(SVG_NS, "title");
    const halo = document.createElementNS(SVG_NS, "circle");
    halo.classList.add("joint-halo");
    const core = document.createElementNS(SVG_NS, "circle");
    core.classList.add("joint-core");
    group.append(title, halo, core);
    jointParts.set(group, { title, halo, core, label: null });

    group.addEventListener("pointerdown", onJointPointerDown);
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      onSelectJoint(group.dataset.jointId);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      onSelectJoint(group.dataset.jointId);
    });
    return group;
  }

  function updateJoint(group, joint, selected, radius) {
    const id = String(joint.id);
    const parts = jointParts.get(group);
    group.dataset.jointId = id;
    group.classList.toggle("low-confidence", numberOr(joint.confidence, 1) < 0.55);
    group.classList.toggle("manual", Boolean(joint.isManual));
    group.classList.toggle("selected", selected);
    group.setAttribute("aria-label", `关节 ${id}，位置 ${Math.round(joint.x)}, ${Math.round(joint.y)}，置信度 ${formatConfidence(joint.confidence)}`);
    group.setAttribute("transform", `translate(${joint.x} ${joint.y})`);
    parts.title.textContent = `${id} · ${formatConfidence(joint.confidence)}`;
    parts.halo.setAttribute("r", String(radius * 1.55));
    parts.core.setAttribute("r", String(radius));

    if (selected && !parts.label) {
      parts.label = document.createElementNS(SVG_NS, "text");
      parts.label.classList.add("joint-label");
      group.append(parts.label);
    } else if (!selected && parts.label) {
      parts.label.remove();
      parts.label = null;
    }
    if (parts.label) {
      parts.label.setAttribute("x", String(radius + 7));
      parts.label.setAttribute("y", "-8");
      parts.label.textContent = id;
    }
  }

  function render({ visible, hasProject, joints, bones, selectedJointId, canvasSize }) {
    skeletonSvg.classList.toggle("is-hidden", !visible);
    if (!hasProject) {
      boneGroup.replaceChildren();
      jointGroup.replaceChildren();
      bonesById.clear();
      jointsById.clear();
      return;
    }
    if (!visible) return;

    const jointMap = new Map(joints.map((joint) => [String(joint.id), joint]));
    const radius = clamp(Math.min(canvasSize.width, canvasSize.height) * 0.006, 4, 10);
    const activeBones = new Set();
    let boneIndex = 0;
    bones.forEach((bone, sourceIndex) => {
      const fromId = String(typeof bone.from === "object" ? bone.from.id : bone.from ?? bone.start_joint_id ?? bone.start ?? bone.parent ?? "");
      const toId = String(typeof bone.to === "object" ? bone.to.id : bone.to ?? bone.end_joint_id ?? bone.end ?? bone.child ?? "");
      const from = jointMap.get(fromId);
      const to = jointMap.get(toId);
      if (!from || !to) return;
      const id = String(bone.id ?? `${fromId}-${toId}-${sourceIndex}`);
      activeBones.add(id);
      let line = bonesById.get(id);
      if (!line) {
        line = document.createElementNS(SVG_NS, "line");
        line.classList.add("bone-line");
        bonesById.set(id, line);
      }
      line.dataset.boneId = id;
      line.classList.toggle("low-confidence", Math.min(numberOr(from.confidence, 1), numberOr(to.confidence, 1)) < 0.55);
      line.setAttribute("x1", String(from.x));
      line.setAttribute("y1", String(from.y));
      line.setAttribute("x2", String(to.x));
      line.setAttribute("y2", String(to.y));
      placeAt(boneGroup, line, boneIndex);
      boneIndex += 1;
    });
    removeStale(bonesById, activeBones);

    const activeJoints = new Set();
    joints.forEach((joint, index) => {
      const id = String(joint.id);
      activeJoints.add(id);
      let group = jointsById.get(id);
      if (!group) {
        group = createJoint();
        jointsById.set(id, group);
      }
      updateJoint(group, joint, id === selectedJointId, radius);
      placeAt(jointGroup, group, index);
    });
    removeStale(jointsById, activeJoints);
  }

  return { render };
}
