"""Offline joint observations on the hash-bound PSD composite."""
import json
import re

from .joint_draft import JOINTS, build_joint_draft, validate_joint_draft
from .semantic_view import _image_url


def render_joint_review(candidate, composite_bytes, *, draft=None, assistance=None):
    if assistance is not None:
        from ..resolved_project import canonical_sha256
        if assistance.get('candidate_sha256') != canonical_sha256(candidate) or assistance.get('independent_annotation') is not False:
            raise ValueError('benchmark_assisted_joint_source_mismatch')
        draft = assistance['draft']
    initial = build_joint_draft(candidate) if draft is None else validate_joint_draft(candidate, draft)
    data = json.dumps({"draft": initial, "canvas": candidate["canvas"], "joints": JOINTS, "assistance": assistance},
                      ensure_ascii=False, allow_nan=False)
    for char, encoded in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        data = data.replace(char, encoded)
    replacements = {"__DATA__": data, "__IMAGE__": _image_url(composite_bytes, candidate["composite_sha256"]),
                    "__SCRIPT__": _SCRIPT}
    return re.sub('|'.join(replacements), lambda match: replacements[match[0]], _PAGE)


_PAGE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>关节点观察草稿</title><style>
body{font:16px/1.6 system-ui;margin:24px auto;max-width:1150px;padding:0 18px;color:#182333;background:#f5f6f8}
.notice{background:#fff2d0;padding:14px}main{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:20px}
canvas{width:100%;height:auto;display:block;cursor:crosshair;background:white;background-image:conic-gradient(#ddd 25%,transparent 0 50%,#ddd 0 75%,transparent 0);background-size:20px 20px}
label{display:block;margin:12px 0}select,input,button{font:inherit;padding:7px;max-width:100%;box-sizing:border-box}select,input{width:100%}button{margin:4px}#summary{white-space:pre-line}#message{color:#a52a00;min-height:2em}img{display:none}@media(max-width:720px){main{grid-template-columns:1fr}}
</style></head><body><h1>关节点观察草稿</h1>
<style>canvas{touch-action:none;cursor:grab}.toolbar{display:flex;flex-wrap:wrap;gap:6px}#point-list{display:flex;flex-wrap:wrap;max-height:260px;overflow:auto}#point-list button{font-size:13px}#point-list button.active{outline:2px solid #cf360d}</style>
<p class="notice" id="guidance">直接点选图上的关节并拖动修正，松开即保留修改；空白处点击可放置所选点。左右指角色自身。无法看清时填写原因并标记不可观测，最后一次保存全部标注。</p>
<main><section><canvas id="canvas" aria-label="点选并拖动关节"></canvas><img id="composite" alt="PSD 合成图" src="__IMAGE__"></section>
<section><label>关节<select id="joint"></select></label><p id="position"></p>
<label>观察备注<input id="notes" maxlength="1000"></label>
<button id="unobservable">标记不可观测</button><button id="clear">清除此点</button><button id="undo">撤销</button>
<div id="point-list" aria-label="全部关节"></div><p id="message" role="status"></p><button id="confirm-all" hidden>确认当前全部有坐标的点</button><button id="download">保存全部标注</button>
<label>恢复草稿<input id="restore" type="file" accept="application/json,.json"></label><p id="summary"></p></section></main>
<script id="joint-data" type="application/json">__DATA__</script><script>__SCRIPT__</script></body></html>'''

_SCRIPT = r'''
const data=JSON.parse(document.getElementById('joint-data').textContent);
const clone=v=>JSON.parse(JSON.stringify(v));
let draft=clone(data.draft), history=[];
let reviewed=new Set(data.assistance?.reviewed_joint_ids||[]), drag=null, suppressClick=false;
const el=id=>document.getElementById(id), canvas=el('canvas'), ctx=canvas.getContext('2d'), img=el('composite');
canvas.width=data.canvas[0]; canvas.height=data.canvas[1];
const labels={root:'根参考点',pelvis:'骨盆',chest:'胸部',neck:'颈部',head:'头部',shoulder:'肩',elbow:'肘',wrist:'腕',hip:'髋',knee:'膝',ankle:'踝'};
for(const [i,id] of data.joints.entries()){const o=document.createElement('option');o.value=id;const [name,side]=id.split('.');o.textContent=`${i+1}. ${labels[name]}${side==='left'?'（角色左）':side==='right'?'（角色右）':''} · ${id}`;el('joint').append(o);}
function valid(value){
 const keys=(v,ks)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===ks.sort().join('|');
 if(!keys(value,['schema','candidate_sha256','authority','records'])||value.schema!==data.draft.schema||value.authority!=='none'||value.candidate_sha256!==data.draft.candidate_sha256||!Array.isArray(value.records)||value.records.length!==data.joints.length)throw Error('草稿与当前证据不匹配');
 value.records.forEach((r,i)=>{
  if(!keys(r,['joint_id','status','position','notes'])||r.joint_id!==data.joints[i]||!['unmarked','observed','unobservable'].includes(r.status)||typeof r.notes!=='string'||[...r.notes].length>1000||/\p{C}/u.test(r.notes))throw Error('关节记录无效');
  if(r.status==='unobservable'&&!r.notes.trim())throw Error('不可观测必须填写原因');
  if(r.status==='observed'){if(!Array.isArray(r.position)||r.position.length!==2||r.position.some((v,j)=>typeof v!=='number'||!Number.isFinite(v)||v<0||v>data.canvas[j]))throw Error('坐标超出 PSD 画布');}
  else if(r.position!==null)throw Error('未观测关节不能保留坐标');
 }); return clone(value);
}
function current(){return draft.records.find(r=>r.joint_id===el('joint').value);}
function checkpoint(){history.push({draft:clone(draft),reviewed:[...reviewed]});}
function imageReady(){return img.complete&&img.naturalWidth===canvas.width&&img.naturalHeight===canvas.height;}
function change(action){try{const next=clone(draft);action(next.records.find(r=>r.joint_id===el('joint').value));valid(next);checkpoint();draft=next;reviewed.add(el('joint').value);el('message').textContent='修改已保留，可继续拖动其他点，最后保存全部';render();}catch(e){el('message').textContent=e.message;}}
function render(){
 ctx.clearRect(0,0,canvas.width,canvas.height);if(imageReady())ctx.drawImage(img,0,0,canvas.width,canvas.height);
 const unit=Math.max(canvas.width,canvas.height)/600, byId=Object.fromEntries(draft.records.map(r=>[r.joint_id,r]));
 ctx.lineWidth=2*unit;ctx.strokeStyle='#1b789b';
 const edges=[['root','pelvis'],['pelvis','chest'],['chest','neck'],['neck','head']];
 for(const s of ['left','right'])edges.push(['chest',`shoulder.${s}`],[`shoulder.${s}`,`elbow.${s}`],[`elbow.${s}`,`wrist.${s}`],['pelvis',`hip.${s}`],[`hip.${s}`,`knee.${s}`],[`knee.${s}`,`ankle.${s}`]);
 for(const [a,b] of edges){const p=byId[a].position,q=byId[b].position;if(p&&q){ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();}}
 draft.records.forEach((r,i)=>{if(!r.position)return;const [x,y]=r.position;ctx.fillStyle=r.joint_id===el('joint').value?'#cf360d':data.assistance&&!reviewed.has(r.joint_id)?'#ae7100':'#075d87';ctx.beginPath();ctx.arc(x,y,5*unit,0,Math.PI*2);ctx.fill();ctx.font=`bold ${14*unit}px sans-serif`;const [name,side]=r.joint_id.split('.');const label=`${side==='left'?'左':side==='right'?'右':''}${labels[name]}`;ctx.fillText(`${i+1} ${label}`,x+7*unit,y-7*unit);});
 const row=current();el('notes').value=row.notes;el('position').textContent=row.status==='observed'?`PSD 坐标：${row.position.join(', ')}`:row.status==='unobservable'?'不可观测':'尚未标记';
 el('summary').textContent=`已观察 ${draft.records.filter(r=>r.status==='observed').length} / ${data.joints.length}\n不可观测 ${draft.records.filter(r=>r.status==='unobservable').length} 个`;el('undo').disabled=!history.length;
 if(data.assistance)el('summary').textContent=`模型辅助标注 · 已复核 ${reviewed.size} / ${data.joints.length}\n金色点：自动建议尚未复核；蓝色点：已调整或确认。`;
 if(el('point-list').replaceChildren){el('point-list').replaceChildren();draft.records.forEach((r,i)=>{const b=document.createElement('button');b.textContent=`${i+1} ${r.joint_id}${reviewed.has(r.joint_id)?' ✓':''}`;b.className=r.joint_id===el('joint').value?'active':'';b.onclick=()=>{el('joint').value=r.joint_id;render();};el('point-list').append(b);});}
}
function pointer(e){const b=canvas.getBoundingClientRect();return [(e.clientX-b.left)*canvas.width/b.width,(e.clientY-b.top)*canvas.height/b.height].map((v,i)=>Math.round(Math.max(0,Math.min(data.canvas[i],v))*1000)/1000);}
function hit(e){const b=canvas.getBoundingClientRect();let result=null,best=16;for(const r of draft.records){if(!r.position)continue;const d=Math.hypot((r.position[0]*b.width/canvas.width+b.left)-e.clientX,(r.position[1]*b.height/canvas.height+b.top)-e.clientY);if(d<best){best=d;result=r;}}return result;}
canvas.onclick=e=>{if(suppressClick){suppressClick=false;return;}const b=canvas.getBoundingClientRect();if(!b.width||!b.height||!imageReady())return;const r=hit(e);if(r){el('joint').value=r.joint_id;render();return;}const p=pointer(e);change(r=>{r.position=p;r.status='observed';});};
canvas.onpointerdown=e=>{if(!imageReady()||e.button!==undefined&&e.button!==0)return;const r=hit(e);if(!r)return;el('joint').value=r.joint_id;drag={id:e.pointerId,before:clone(draft),reviewed:[...reviewed],start:[e.clientX,e.clientY],moved:false};canvas.setPointerCapture?.(e.pointerId);render();};
canvas.onpointermove=e=>{if(!drag||drag.id!==e.pointerId)return;if(!drag.moved&&Math.hypot(e.clientX-drag.start[0],e.clientY-drag.start[1])<2)return;drag.moved=true;current().position=pointer(e);current().status='observed';reviewed.add(current().joint_id);render();};
canvas.onpointerup=e=>{if(!drag||drag.id!==e.pointerId)return;if(drag.moved){history.push({draft:drag.before,reviewed:drag.reviewed});suppressClick=true;el('message').textContent='位置已保存到本页，可继续拖动；最后保存全部标注';}drag=null;canvas.releasePointerCapture?.(e.pointerId);render();};
canvas.onpointercancel=()=>{if(drag){draft=drag.before;reviewed=new Set(drag.reviewed);drag=null;render();}};
el('joint').onchange=render;
el('notes').onchange=()=>change(r=>{r.notes=el('notes').value;});
el('unobservable').onclick=()=>change(r=>{r.notes=el('notes').value;r.status='unobservable';r.position=null;});
el('clear').onclick=()=>change(r=>{r.status='unmarked';r.position=null;});
el('undo').onclick=()=>{if(history.length){const old=history.pop();draft=old.draft;reviewed=new Set(old.reviewed);render();}};
function exportDraft(){const result=valid(draft);return data.assistance?{...clone(data.assistance),draft:result,reviewed_joint_ids:data.joints.filter(j=>reviewed.has(j))}:result;}
el('download').onclick=()=>{try{const content=exportDraft(),blob=new Blob([JSON.stringify(content,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=data.assistance?'assisted-joint-draft.json':'joint-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){el('message').textContent=e.message;}};
el('restore').onchange=async()=>{try{const f=el('restore').files[0];if(!f)return;if(f.size>100000)throw Error('草稿文件过大');const content=JSON.parse(await f.text());let ids=[];if(data.assistance){for(const k of Object.keys(data.assistance).filter(k=>!['draft','reviewed_joint_ids'].includes(k)))if(JSON.stringify(content[k])!==JSON.stringify(data.assistance[k]))throw Error('模型辅助来源不匹配');ids=content.reviewed_joint_ids;if(!Array.isArray(ids)||new Set(ids).size!==ids.length||ids.some(j=>!data.joints.includes(j))||Object.keys(content).sort().join('|')!==Object.keys(data.assistance).sort().join('|'))throw Error('复核标记无效');}const next=valid(data.assistance?content.draft:content);checkpoint();draft=next;reviewed=new Set(ids);render();el('message').textContent='草稿已恢复';}catch(e){el('message').textContent=e.message;}finally{el('restore').value='';}};
if(data.assistance){el('guidance').textContent='已加载12个 Pose 四肢点与5个旧基线中轴建议。直接点选、拖动，最后一次保存全部。金色建议尚未复核；这是模型辅助标注，不计为独立 GT。';el('confirm-all').hidden=false;el('confirm-all').onclick=()=>{checkpoint();draft.records.filter(r=>r.position).forEach(r=>reviewed.add(r.joint_id));render();};}
img.onload=()=>{if(img.naturalWidth!==canvas.width||img.naturalHeight!==canvas.height){el('message').textContent='合成图尺寸与 PSD 画布不一致';canvas.onclick=null;}render();};
img.onerror=()=>{el('message').textContent='合成图加载失败';canvas.onclick=null;};
if(img.complete&&img.naturalWidth)img.onload();else render();
'''
