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

export function mountComponentOwnership(document, template) {
  let draft = structuredClone(template), saved = structuredClone(template);
  const views = [];
  const make = (tag, text = '') => { const el = document.createElement(tag); el.textContent = text; return el; };
  const toolbar = make('section'), download = make('button', '下载全部归属草稿'), upload = make('input'), undo = make('button', '撤销至上次载入草稿'), notice = make('p');
  upload.type = 'file'; upload.accept = '.json'; upload.setAttribute('aria-label', '载入归属草稿'); notice.setAttribute('role', 'status');
  toolbar.append(download, upload, undo, notice); document.querySelector('main').before(toolbar);
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
    section.append(make('h3', '区域归属草稿'), pick, role, side, make('p', '骨骼最多 4 根；Ctrl/Command 多选。黄色残余在本版保留未归属。'), bones, apply, clear, message);
    const row = () => draft.records.find(r => r.layer_id === layer && r.component_id === pick.value);
    function show() {
      const current = row(); role.value = current.semantic; side.value = current.side;
      for (const option of bones.options) option.selected = current.bone_ids.includes(option.value);
      apply.disabled = current.component_id === 'low-alpha-residual';
      message.textContent = current.status === 'assigned' ? '已写入草稿，尚未采用' : '未归属';
      for (const path of section.querySelectorAll('path[data-component]')) {
        path.setAttribute('stroke', path.dataset.component === pick.value ? '#fff' : 'none');
        path.setAttribute('stroke-width', '.6');
      }
    }
    pick.onchange = show;
    for (const path of section.querySelectorAll('path[data-component]')) path.onclick = () => { pick.value = path.dataset.component; show(); };
    apply.onclick = () => {
      const next = structuredClone(draft), target = next.records.find(r => r.layer_id === layer && r.component_id === pick.value);
      Object.assign(target, { status: 'assigned', semantic: role.value, side: side.value, bone_ids: [...bones.selectedOptions].map(o => o.value) });
      try { draft = validateComponentDraft(next, template); refresh(); } catch (e) { message.textContent = '请选择明确语义、侧别及 1–4 根骨骼。' + e.message; }
    };
    clear.onclick = () => { Object.assign(row(), { status: 'pending', semantic: 'unknown', side: 'unknown', bone_ids: [] }); refresh(); };
    views.push(show);
  }
  refresh();
}
