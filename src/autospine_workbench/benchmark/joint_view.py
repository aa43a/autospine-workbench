"""Offline joint observations on the hash-bound PSD composite."""
import json
import re

from .joint_draft import JOINTS, build_joint_draft, validate_joint_draft
from .semantic_view import _image_url


def render_joint_review(candidate, composite_bytes, *, draft=None):
    initial = build_joint_draft(candidate) if draft is None else validate_joint_draft(candidate, draft)
    data = json.dumps({"draft": initial, "canvas": candidate["canvas"], "joints": JOINTS},
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
<p class="notice">先选关节，再点击图片。左右指角色自身；坐标基于 PSD 画布，左上为原点，x 向右、y 向下。连线仅辅助观察，不生成骨架。无法看清时填写原因并标记不可观测。草稿不产生正式采用。</p>
<main><section><canvas id="canvas" aria-label="点击录入所选关节"></canvas><img id="composite" alt="PSD 合成图" src="__IMAGE__"></section>
<section><label>关节<select id="joint"></select></label><p id="position"></p>
<label>观察备注<input id="notes" maxlength="1000"></label>
<button id="unobservable">标记不可观测</button><button id="clear">清除此点</button><button id="undo">撤销</button>
<p id="message" role="status"></p><button id="download">下载草稿</button>
<label>恢复草稿<input id="restore" type="file" accept="application/json,.json"></label><p id="summary"></p></section></main>
<script id="joint-data" type="application/json">__DATA__</script><script>__SCRIPT__</script></body></html>'''

_SCRIPT = r'''
const data=JSON.parse(document.getElementById('joint-data').textContent);
const clone=v=>JSON.parse(JSON.stringify(v));
let draft=clone(data.draft), history=[];
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
function imageReady(){return img.complete&&img.naturalWidth===canvas.width&&img.naturalHeight===canvas.height;}
function change(action){try{const next=clone(draft);action(next.records.find(r=>r.joint_id===el('joint').value));valid(next);history.push(clone(draft));draft=next;el('message').textContent='草稿已更新，请下载保存';render();}catch(e){el('message').textContent=e.message;}}
function render(){
 ctx.clearRect(0,0,canvas.width,canvas.height);if(imageReady())ctx.drawImage(img,0,0,canvas.width,canvas.height);
 const unit=Math.max(canvas.width,canvas.height)/600, byId=Object.fromEntries(draft.records.map(r=>[r.joint_id,r]));
 ctx.lineWidth=2*unit;ctx.strokeStyle='#1b789b';
 const edges=[['root','pelvis'],['pelvis','chest'],['chest','neck'],['neck','head']];
 for(const s of ['left','right'])edges.push(['chest',`shoulder.${s}`],[`shoulder.${s}`,`elbow.${s}`],[`elbow.${s}`,`wrist.${s}`],['pelvis',`hip.${s}`],[`hip.${s}`,`knee.${s}`],[`knee.${s}`,`ankle.${s}`]);
 for(const [a,b] of edges){const p=byId[a].position,q=byId[b].position;if(p&&q){ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();}}
 draft.records.forEach((r,i)=>{if(!r.position)return;const [x,y]=r.position;ctx.fillStyle=r.joint_id===el('joint').value?'#cf360d':'#075d87';ctx.beginPath();ctx.arc(x,y,5*unit,0,Math.PI*2);ctx.fill();ctx.font=`bold ${14*unit}px sans-serif`;ctx.fillText(String(i+1),x+7*unit,y-7*unit);});
 const row=current();el('notes').value=row.notes;el('position').textContent=row.status==='observed'?`PSD 坐标：${row.position.join(', ')}`:row.status==='unobservable'?'不可观测':'尚未标记';
 el('summary').textContent=`已观察 ${draft.records.filter(r=>r.status==='observed').length} / ${data.joints.length}\n不可观测 ${draft.records.filter(r=>r.status==='unobservable').length} 个`;el('undo').disabled=!history.length;
}
canvas.onclick=e=>{const b=canvas.getBoundingClientRect();if(!b.width||!b.height||!imageReady())return;const p=[(e.clientX-b.left)*canvas.width/b.width,(e.clientY-b.top)*canvas.height/b.height].map(v=>Math.round(v*1000)/1000);change(r=>{r.position=p;r.status='observed';});};
el('joint').onchange=render;
el('notes').onchange=()=>change(r=>{r.notes=el('notes').value;});
el('unobservable').onclick=()=>change(r=>{r.notes=el('notes').value;r.status='unobservable';r.position=null;});
el('clear').onclick=()=>change(r=>{r.status='unmarked';r.position=null;});
el('undo').onclick=()=>{if(history.length){draft=history.pop();render();}};
el('download').onclick=()=>{try{const content=valid(draft),blob=new Blob([JSON.stringify(content,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='joint-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){el('message').textContent=e.message;}};
el('restore').onchange=async()=>{try{const f=el('restore').files[0];if(!f)return;if(f.size>100000)throw Error('草稿文件过大');const next=valid(JSON.parse(await f.text()));history.push(clone(draft));draft=next;render();el('message').textContent='草稿已恢复';}catch(e){el('message').textContent=e.message;}finally{el('restore').value='';}};
img.onload=()=>{if(img.naturalWidth!==canvas.width||img.naturalHeight!==canvas.height){el('message').textContent='合成图尺寸与 PSD 画布不一致';canvas.onclick=null;}render();};
img.onerror=()=>{el('message').textContent='合成图加载失败';canvas.onclick=null;};
if(img.complete&&img.naturalWidth)img.onload();else render();
'''
