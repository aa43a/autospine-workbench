import { mountComponentBones, toggleComponentBone } from "./component-bone-overlay.js";
const ROLES = ['unknown', 'body.arm', 'body.leg', 'body.foot', 'wear.sleeve', 'wear.skirt', 'wear.pants', 'accessory.object'];
const SIDES = ['unknown', 'left', 'right', 'center', 'bilateral'];
const LABELS = { unknown:'未确定', left:'角色左侧', right:'角色右侧', center:'中心', bilateral:'双侧',
  'body.arm':'手臂', 'body.leg':'腿', 'body.foot':'脚', 'wear.sleeve':'衣袖', 'wear.skirt':'裙装', 'wear.pants':'裤装', 'accessory.object':'配饰或物件' };
const stable = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
export function validateComponentDraft(value, template) {
  const clone = JSON.parse(JSON.stringify(value));
  if (clone.schema !== template.schema || clone.project_id !== template.project_id || clone.authority !== 'none'
    || clone.production_authorized !== false || stable(clone.sources) !== stable(template.sources)
    || !Array.isArray(clone.records) || clone.records.length !== template.records.length) throw Error('草稿来源或区域集合不匹配');
  for (let i = 0; i < clone.records.length; i++) {
    const row = clone.records[i], expected = template.records[i];
    if (JSON.stringify(Object.keys(row).sort()) !== JSON.stringify(Object.keys(expected).sort())
      || row.layer_id !== expected.layer_id || row.component_id !== expected.component_id
      || !['pending', 'assigned'].includes(row.status) || !ROLES.includes(row.semantic) || !SIDES.includes(row.side)
      || !Array.isArray(row.bone_ids) || row.bone_ids.length > 4 || new Set(row.bone_ids).size !== row.bone_ids.length
      || row.bone_ids.some(id => !template.sources.bone_ids.includes(id))
      || (row.status === 'pending' && (row.semantic !== 'unknown' || row.side !== 'unknown' || row.bone_ids.length))
      || (row.status === 'assigned' && (row.component_id === 'low-alpha-residual' || row.semantic === 'unknown' || row.side === 'unknown' || !row.bone_ids.length))) throw Error('区域归属字段无效');
  }
  if (JSON.stringify(Object.keys(clone).sort()) !== JSON.stringify(Object.keys(template).sort())) throw Error('草稿字段无效');
  return clone;
}

export function prefillComponentSuggestions(draft, template, suggestions, only = null) {
  const next = validateComponentDraft(draft, template);
  if (!suggestions || suggestions.authority !== 'none' || suggestions.production_authorized !== false
    || suggestions.profile !== 'semantic-component-bone-samples-v1' || stable(suggestions.sources) !== stable(template.sources)) throw Error('建议来源不匹配');
  const seen = new Set();
  for (const advice of suggestions.records) {
    const key = `${advice.layer_id}:${advice.component_id}`;
    if (seen.has(key)) throw Error('重复的区域建议'); seen.add(key);
    const row = next.records.find(r => r.layer_id === advice.layer_id && r.component_id === advice.component_id);
    if (!row) throw Error('未知区域建议');
    if (row.status === 'pending' && advice.status === 'suggested' && (!only || key === only)) Object.assign(row, advice.proposal);
  }
  return validateComponentDraft(next, template);
}

export function mountComponentOwnership(document, template, suggestions = null) {
  let draft = structuredClone(template), saved = structuredClone(template);
  const views = [];
  const make = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const toolbar = make('section'), download = make('button', '下载全部归属草稿'), upload = make('input'), undo = make('button', '撤销至上次载入草稿'), notice = make('p');
  upload.type = 'file'; upload.accept = '.json'; upload.setAttribute('aria-label', '载入归属草稿'); notice.setAttribute('role', 'status');
  const layerPick = make('select'), nextRegion = make('button', '下一个未处理区域'), batch = make('button', '一键预填可靠建议');
  layerPick.setAttribute('aria-label', '选择待复核图层'); toolbar.className = 'ownership-toolbar';
  const sections = [...document.querySelectorAll('section[data-layer]')];
  for (const section of sections) { const option = make('option', section.querySelector('h2').textContent); option.value = section.dataset.layer; layerPick.append(option); }
  const regionPicks = new Map(); let activeKey = '';
  const focusLayer = () => { for (const section of sections) section.hidden = section.dataset.layer !== layerPick.value; };
  layerPick.onchange = () => { focusLayer(); regionPicks.get(layerPick.value)?.dispatchEvent(new Event('change')); };
  batch.disabled = !suggestions?.records.some(r => r.status === 'suggested');
  batch.onclick = () => { try { draft = prefillComponentSuggestions(draft, template, suggestions); refresh(); } catch(e) { notice.textContent = e.message; } };
  nextRegion.onclick = () => {
    const start = draft.records.findIndex(r => `${r.layer_id}:${r.component_id}` === activeKey);
    const order = [...draft.records.slice(start+1), ...draft.records.slice(0,start+1)];
    const next = order.find(r => r.status === 'pending' && r.component_id !== 'low-alpha-residual');
    if (!next) { notice.textContent = '普通区域均已填写；低透明度残余仍保留未归属。'; return; }
    layerPick.value = next.layer_id; focusLayer(); const control = regionPicks.get(next.layer_id); control.value = next.component_id; control.dispatchEvent(new Event('change'));
  };
  toolbar.append(layerPick, batch, nextRegion, download, upload, undo, notice); document.querySelector('main').before(toolbar);
  function refresh() {
    notice.textContent = `已指定 ${draft.records.filter(r => r.status === 'assigned').length}/${draft.records.length} 个区域；草稿不代表批准或 Mesh 验收。`;
    views.forEach(fn => fn());
  }
  download.onclick = () => {
    try {
      const value = validateComponentDraft(draft, template), url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
      const link = make('a'); link.href = url; link.download = `component-ownership-draft-${template.project_id}.json`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { notice.textContent = e.message; }
  };
  upload.onchange = async () => {
    try {
      const file = upload.files[0]; if (!file) return;
      if (file.size > 2*1024*1024) throw Error('草稿文件过大');
      const next = validateComponentDraft(JSON.parse(await file.text()), template);
      draft = next; saved = structuredClone(next); refresh();
    } catch (e) { notice.textContent = e.message; }
    upload.value = '';
  };
  undo.onclick = () => { draft = structuredClone(saved); refresh(); };
  for (const section of document.querySelectorAll('section[data-layer]')) {
    const layer = section.dataset.layer, pick = make('select'), role = make('select'), side = make('select'), bones = make('select');
    pick.setAttribute('aria-label', `${layer} 区域`); role.setAttribute('aria-label', `${layer} 语义`);
    side.setAttribute('aria-label', `${layer} 左右侧`); bones.setAttribute('aria-label', `${layer} 骨骼集合`); bones.multiple = true; bones.size = 5;
    function options(control, values) { for (const value of values) {
      const title = value === 'low-alpha-residual' ? '低透明度残余（未归属）' : /^component-\d+$/.test(value) ? `区域 ${Number(value.slice(10))+1}` : LABELS[value] || value;
      const option = make('option', title); option.value = value; control.append(option);
    } }
    options(pick, draft.records.filter(r => r.layer_id === layer).map(r => r.component_id)); options(role, ROLES); options(side, SIDES); options(bones, template.sources.bone_ids);
    const apply = make('button', '将当前选择写入草稿'), clear = make('button', '保留未归属'), message = make('p');
    const editor = make('div'), layout = make('div'); layout.className = 'ownership-layout';
    const svg = section.querySelector('svg'), canvasPane = make('div'); svg.before(layout); layout.append(canvasPane, editor); canvasPane.append(svg);
    const one = make('button', '使用当前区域建议'), adviceText = make('p');
    const manual = make('details'); manual.append(make('summary', '列表选择骨骼'), make('p', '骨骼最多 4 根；Ctrl/Command 多选。'), bones);
    editor.append(make('h3', '选区域 → 点选骨骼'), pick, adviceText, one, make('p','语义与侧别'), role, side, manual, apply, clear, message);
    regionPicks.set(layer, pick);
    const row = () => draft.records.find(r => r.layer_id === layer && r.component_id === pick.value);
    const bonePicker = mountComponentBones(document, svg, id => {
      if (row().component_id === 'low-alpha-residual') return;
      try {
        const ids = toggleComponentBone([...bones.selectedOptions].map(o => o.value), id, template.sources.bone_ids);
        for (const option of bones.options) option.selected = ids.includes(option.value);
        bonePicker.render(ids); message.textContent = '骨骼已点选，请点击“将当前选择写入草稿”。';
      } catch(e) { message.textContent = e.message; }
    });
    bones.onchange = () => bonePicker?.render([...bones.selectedOptions].map(o => o.value));
    function show() {
      const current = row(); role.value = current.semantic; side.value = current.side;
      if (layer === layerPick.value) activeKey = `${layer}:${pick.value}`;
      const advice = suggestions?.records.find(r => r.layer_id === layer && r.component_id === pick.value);
      one.disabled = current.status !== 'pending' || advice?.status !== 'suggested';
      adviceText.textContent = advice?.status === 'suggested'
        ? `建议：${LABELS[advice.proposal.semantic]} · ${LABELS[advice.proposal.side]} · ${advice.proposal.bone_ids.join(' → ')}。依据：语义提示与唯一区域骨段覆盖。`
        : '无可靠自动建议：请检查语义与几何，或保留未归属。';
      for (const option of bones.options) option.selected = current.bone_ids.includes(option.value);
      bonePicker?.render(current.bone_ids, current.component_id === 'low-alpha-residual');
      apply.disabled = current.component_id === 'low-alpha-residual';
      message.textContent = current.status === 'assigned' ? '已写入草稿，尚未采用' : '未归属';
      for (const path of section.querySelectorAll('path[data-component]')) {
        path.setAttribute('stroke', path.dataset.component === pick.value ? '#fff' : 'none');
        path.setAttribute('stroke-width', '2'); path.setAttribute('vector-effect','non-scaling-stroke');
        path.setAttribute('fill-opacity', path.dataset.component === pick.value ? '1' : '.35');
      }
    }
    pick.onchange = show;
    one.onclick = () => { try { draft = prefillComponentSuggestions(draft, template, suggestions, `${layer}:${pick.value}`); refresh(); } catch(e) { message.textContent = e.message; } };
    for (const path of section.querySelectorAll('path[data-component]')) {
      path.setAttribute('role','button'); path.setAttribute('tabindex','0'); path.setAttribute('aria-label',path.dataset.component);
      path.onclick = () => { pick.value = path.dataset.component; show(); if (pick.value !== 'low-alpha-residual') bonePicker?.setMode('bone'); };
      path.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); path.onclick(); } };
    }
    apply.onclick = () => {
      const next = structuredClone(draft), target = next.records.find(r => r.layer_id === layer && r.component_id === pick.value);
      Object.assign(target, { status: 'assigned', semantic: role.value, side: side.value, bone_ids: [...bones.selectedOptions].map(o => o.value) });
      try { draft = validateComponentDraft(next, template); refresh(); } catch (e) { message.textContent = '请选择明确语义、侧别及 1–4 根骨骼。' + e.message; }
    };
    clear.onclick = () => { Object.assign(row(), { status: 'pending', semantic: 'unknown', side: 'unknown', bone_ids: [] }); refresh(); };
    views.push(show);
  }
  refresh();
  focusLayer(); regionPicks.get(layerPick.value)?.dispatchEvent(new Event('change'));
}
