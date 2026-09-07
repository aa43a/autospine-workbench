"""Offline draft controls; imported files are validated before changing the UI."""
from html import escape
import json

ACTIONS = {'pending': '尚未处理', 'bind': '选择候选骨骼', 'requires_split': '需要拆层',
           'semantic_review': '需要语义复核', 'exclude': '草稿中排除'}


def controls(row, record):
    actions = ''.join(f'<option value="{key}"'+(' selected' if record['action'] == key else '')+
                      f'>{label}</option>' for key, label in ACTIONS.items() if key != 'bind' or row['bone_options'])
    options = '<option value="">未选择</option>' + ''.join(
        f'<option value="{escape(b["bone_id"], quote=True)}"'+
        (' selected' if record['bone_id'] == b['bone_id'] else '')+
        f'>{escape(b["bone_id"])}</option>' for b in row['bone_options'])
    return f'''<fieldset data-layer="{escape(row['layer_id'], quote=True)}"><legend>复核草稿</legend>
<label>处理方式 <select data-action>{actions}</select></label>
<label>候选骨骼 <select data-bone>{options}</select></label>
<label>备注（拆层、排除、语义复核必填）<textarea data-notes maxlength="2000">{escape(record['notes'])}</textarea></label></fieldset>'''


def panel(bindings, draft):
    payload = json.dumps({'bindings': bindings, 'draft': draft}, ensure_ascii=True).replace('<', '\\u003c')
    return ('<section class="notice"><button id="save-draft">保存整份草稿</button> '
            '<label>恢复草稿 <input id="load-draft" type="file" accept=".json,application/json"></label> '
            '<button id="undo-draft">撤销上一步</button><p id="draft-status" role="status"></p></section>'
            f'<script type="application/json" id="binding-state">{payload}</script>')


SCRIPT = r'''
function validateDraft(bindings, base, doc) {
  const keys = (obj, expected) => obj && typeof obj === 'object' && !Array.isArray(obj) &&
    JSON.stringify(Object.keys(obj).sort()) === JSON.stringify(expected.slice().sort());
  if (!keys(doc, Object.keys(base)) || doc.schema !== base.schema || doc.authority !== 'none' ||
      doc.production_authorized !== false || doc.source_bindings_sha256 !== base.source_bindings_sha256 ||
      !Array.isArray(doc.records) || doc.records.length !== bindings.bindings.length) throw Error('草稿来源或格式不匹配');
  doc.records.forEach((r,i) => {
    const row = bindings.bindings[i];
    if (!keys(r, ['layer_id','action','bone_id','notes']) || r.layer_id !== row.layer_id ||
        !['pending','bind','requires_split','exclude','semantic_review'].includes(r.action) ||
        typeof r.notes !== 'string' || Array.from(r.notes).length > 2000 ||
        /\p{C}/u.test(r.notes.replace(/[\n\r\t]/g,''))) throw Error('图层记录无效');
    if (r.action === 'bind') {
      if (row.status !== 'needs_review' || !row.bone_options.some(b => b.bone_id === r.bone_id)) throw Error('选择的骨骼不在候选中');
    } else if (r.bone_id !== null) throw Error('未绑定记录不能携带骨骼');
    if (['requires_split','exclude','semantic_review'].includes(r.action) && !r.notes.trim()) throw Error('请填写拆层、排除或语义复核备注');
  });
  return structuredClone(doc);
}
if (typeof document !== 'undefined') {
  const {bindings,draft:base} = JSON.parse(document.getElementById('binding-state').textContent);
  let current = structuredClone(base), history = [];
  const fields = [...document.querySelectorAll('fieldset[data-layer]')];
  const status = document.getElementById('draft-status');
  function show() {
    fields.forEach((f,i) => {
      const r = current.records[i];
      f.querySelector('[data-action]').value = r.action;
      const bone = f.querySelector('[data-bone]');
      bone.value = r.bone_id || ''; bone.disabled = r.action !== 'bind';
      f.querySelector('[data-notes]').value = r.notes;
    });
    const pending = current.records.filter(r => r.action === 'pending').length;
    status.textContent = `共 ${current.records.length} 层，${pending} 层尚未处理。草稿不等于正式采用。`;
  }
  fields.forEach((f,i) => f.addEventListener('change', () => {
    history.push(structuredClone(current)); if (history.length > 100) history.shift();
    const r = current.records[i]; r.action = f.querySelector('[data-action]').value;
    r.bone_id = r.action === 'bind' ? (f.querySelector('[data-bone]').value || null) : null;
    r.notes = f.querySelector('[data-notes]').value;
    show();
  }));
  document.getElementById('undo-draft').onclick = () => { if (history.length) {current = history.pop(); show();} };
  document.getElementById('save-draft').onclick = () => {
    try {
      const checked = validateDraft(bindings, base, current);
      const url = URL.createObjectURL(new Blob([JSON.stringify(checked,null,2)],{type:'application/json'}));
      const link = document.createElement('a'); link.href = url; link.download = 'region-binding-draft.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = '草稿已下载；可用恢复草稿继续编辑。';
    } catch (error) {status.textContent = error.message;}
  };
  document.getElementById('load-draft').onchange = async event => {
    try {
      const file = event.target.files[0]; if (!file) return;
      if (file.size > 4*1024*1024) throw Error('草稿文件过大');
      const checked = validateDraft(bindings, base, JSON.parse(await file.text()));
      history.push(structuredClone(current)); current = checked; show();
    } catch (error) {status.textContent = error.message;}
    event.target.value = '';
  };
  show();
}
'''
