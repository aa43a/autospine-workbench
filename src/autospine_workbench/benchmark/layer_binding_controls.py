"""Version-two option selection, preserving an entire mesh chain as one choice."""
from html import escape
import json

from .region_binding_controls import ACTIONS


def option_label(option):
    mode = '多骨 Mesh（待生成权重）' if option['mode'] == 'mesh_chain' else '刚性单骨'
    if len(option['bone_ids']) == 6:
        return mode + ' · 双侧两链：' + ' → '.join(option['bone_ids'][:3]) + ' / ' + ' → '.join(option['bone_ids'][3:])
    return mode + ' · ' + ' → '.join(option['bone_ids'])


def controls(row, record):
    actions = ''.join(f'<option value="{k}"'+(' selected' if record['action'] == k else '')+
                      f'>{v}</option>' for k,v in ACTIONS.items() if k != 'bind' or row['options'])
    choices = '<option value="">未选择绑定模式和骨链</option>' + ''.join(
        f'<option value="{escape(o["id"], quote=True)}"'+(' selected' if record['option_id'] == o['id'] else '')+
        f'>{escape(option_label(o))}</option>' for o in row['options'])
    return f'''<fieldset data-layer="{escape(row['layer_id'], quote=True)}"><legend>绑定草稿</legend>
<label>处理方式<select data-action>{actions}</select></label>
<label>绑定模式 / 骨链<select data-option>{choices}</select></label>
<label>备注<textarea data-notes maxlength="2000">{escape(record['notes'])}</textarea></label></fieldset>'''


def panel(bindings, draft, focus_layers=None):
    if focus_layers is not None:
        known = {row['layer_id'] for row in bindings['bindings']}
        if (not focus_layers or any(not isinstance(x, str) for x in focus_layers)
                or len(set(focus_layers)) != len(focus_layers) or not set(focus_layers) <= known):
            raise ValueError('focus_layers must contain unique known layer IDs')
    focus = ('<label><input id="focus-only" type="checkbox" checked>仅显示本次缺失图层</label>'
             '<p>此范围仅筛选显示；其他图层及分区候选的原有决定保留在完整草稿中。</p>'
             if focus_layers is not None else '')
    data = json.dumps({'bindings': bindings, 'draft': draft, 'focus_layers': focus_layers}, ensure_ascii=True).replace('<','\\u003c')
    return ('<section class="notice"><button id="save">保存整份草稿</button> '
            '<button id="undo">撤销上一步</button><label>恢复 v2 草稿 <input id="load" type="file" accept=".json"></label>'
            '<label><input id="pending-only" type="checkbox" checked>仅显示待处理图层</label>'
            f'{focus}<p id="status" role="status"></p></section>'
            f'<script type="application/json" id="state">{data}</script>')


SCRIPT = r'''
function bindingRecordComplete(r) {
  return r.action==='bind'?Boolean(r.option_id):r.action!=='pending'&&Boolean(r.notes.trim());
}
function validateLayerDraft(bindings, base, doc) {
  const keys = (o,k) => o && typeof o === 'object' && !Array.isArray(o) &&
    JSON.stringify(Object.keys(o).sort()) === JSON.stringify(k.slice().sort());
  if (!keys(doc,Object.keys(base)) || doc.schema !== base.schema || doc.authority !== 'none' ||
      doc.production_authorized !== false || doc.source_bindings_sha256 !== base.source_bindings_sha256 ||
      !Array.isArray(doc.records) || doc.records.length !== bindings.bindings.length) throw Error('草稿版本或来源不匹配');
  doc.records.forEach((r,i) => {
    const source=bindings.bindings[i];
    if (!keys(r,['layer_id','action','option_id','notes']) || r.layer_id !== source.layer_id ||
        !['pending','bind','requires_split','exclude','semantic_review'].includes(r.action) ||
        typeof r.notes !== 'string' || Array.from(r.notes).length > 2000 ||
        /\p{C}/u.test(r.notes.replace(/[\n\r\t]/g,''))) throw Error('图层记录不完整或无效');
    if (r.action === 'bind') {
      if (source.status !== 'needs_review' || !source.options.some(o=>o.id===r.option_id)) throw Error('绑定选项不在候选中');
    } else if (r.option_id !== null) throw Error('未绑定记录不能保存骨链选项');
    if (['requires_split','exclude','semantic_review'].includes(r.action) && !r.notes.trim()) throw Error('拆层、排除或语义问题请填写备注');
  });
  return structuredClone(doc);
}
if (typeof document !== 'undefined') {
  const {bindings,draft:base,focus_layers}=JSON.parse(document.getElementById('state').textContent);
  const focus=new Set(focus_layers||[]), focusControl=document.getElementById('focus-only');
  let current=structuredClone(base), history=[];
  const fields=[...document.querySelectorAll('fieldset[data-layer]')], status=document.getElementById('status');
  function show() {
    fields.forEach((f,i)=>{
      const r=current.records[i]; f.querySelector('[data-action]').value=r.action;
      const complete=bindingRecordComplete(r);
      f.closest('article').hidden=(focusControl?.checked && !focus.has(r.layer_id)) ||
        (document.getElementById('pending-only').checked && complete);
      const select=f.querySelector('[data-option]'); select.value=r.option_id||''; select.disabled=r.action!=='bind';
      f.querySelector('[data-notes]').value=r.notes;
      f.closest('article').querySelectorAll('[data-chain]').forEach(g=>{
        g.style.opacity=(!r.option_id || g.dataset.chain===r.option_id)?'1':'.12';
      });
    });
    const pending=records=>records.filter(r=>!bindingRecordComplete(r)).length;
    const scoped=current.records.filter(r=>focus.has(r.layer_id));
    status.textContent=(focusControl?`本次范围 ${pending(scoped)}/${scoped.length} 层待处理；`:'')+
      `完整草稿 ${pending(current.records)}/${current.records.length} 层待处理；保存始终包含全部图层。`;
  }
  const remember=()=>{history.push(structuredClone(current)); if(history.length>100)history.shift();};
  document.getElementById('pending-only').onchange=show;
  if(focusControl)focusControl.onchange=show;
  fields.forEach((f,i)=>f.addEventListener('change',()=>{
    remember(); const r=current.records[i]; r.action=f.querySelector('[data-action]').value;
    r.option_id=r.action==='bind'?(f.querySelector('[data-option]').value||null):null;
    r.notes=f.querySelector('[data-notes]').value; show();
  }));
  document.getElementById('undo').onclick=()=>{if(history.length){current=history.pop();show();}};
  document.getElementById('save').onclick=()=>{
    try {
      const doc=validateLayerDraft(bindings,base,current);
      const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download='layer-binding-draft-v2.json';a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='v2 草稿已下载。';
    } catch(e){status.textContent=e.message;}
  };
  document.getElementById('load').onchange=async e=>{
    try {
      const file=e.target.files[0];if(!file)return;if(file.size>4*1024*1024)throw Error('文件过大');
      const restored=validateLayerDraft(bindings,base,JSON.parse(await file.text()));remember();current=restored;show();
    }catch(error){status.textContent=error.message;}e.target.value='';
  };
  show();
}
'''
