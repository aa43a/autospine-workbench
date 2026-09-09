export function toggleComponentBone(selected, id, allowed) {
  if (!allowed.includes(id)) throw Error('未知骨骼');
  if (selected.includes(id)) return selected.filter(bone => bone !== id);
  if (selected.length >= 4) throw Error('每个区域最多选择 4 根骨骼，请先取消一根。');
  return [...selected, id];
}

export function mountComponentBones(document, svg, onToggle) {
  const groups = [...svg.querySelectorAll('[data-bone]')];
  if (!groups.length) return null;
  const toolbar = document.createElement('div'), region = document.createElement('button'), bone = document.createElement('button');
  region.textContent = '① 选区域'; bone.textContent = '② 选骨骼'; region.type = bone.type = 'button';
  const selectedText = document.createElement('p'); selectedText.setAttribute('role','status');
  toolbar.append(region, bone, selectedText); svg.before(toolbar);
  const paths = [...svg.querySelectorAll('path[data-component]')];
  let mode = 'region';
  function setMode(value) {
    mode = value;
    region.setAttribute('aria-pressed',String(mode === 'region')); bone.setAttribute('aria-pressed',String(mode === 'bone'));
    for (const path of paths) { path.style.pointerEvents = mode === 'region' ? 'auto' : 'none'; path.setAttribute('tabindex',mode === 'region' ? '0' : '-1'); }
    for (const group of groups) { group.style.pointerEvents = mode === 'bone' ? 'auto' : 'none'; group.setAttribute('tabindex',mode === 'bone' ? '0' : '-1'); }
  }
  region.onclick = () => setMode('region'); bone.onclick = () => setMode('bone');
  for (const group of groups) {
    group.setAttribute('role','button'); group.setAttribute('aria-label', `绑定骨骼 ${group.dataset.bone}`);
    group.onclick = () => onToggle(group.dataset.bone);
    group.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); group.onclick(); } };
  }
  setMode('region');
  return { setMode, render(ids, locked = false) {
    bone.disabled = locked;
    selectedText.textContent = locked ? '低透明度残余保持未归属。' : `当前骨骼：${ids.join('、') || '尚未选择'}；再次点击取消。`;
    if (locked) setMode('region');
    for (const group of groups) {
      const selected = ids.includes(group.dataset.bone); group.setAttribute('aria-pressed',String(selected));
      group.querySelector('[data-visible]').setAttribute('stroke',selected ? '#ffbf47' : '#65d6ff');
      group.querySelector('text').style.display = selected ? '' : 'none';
    }
  } };
}
