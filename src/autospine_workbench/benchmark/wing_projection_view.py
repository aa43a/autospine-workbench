"""Group review and local brush corrections; no automatic adoption."""
import base64
import json
from .wing_split_script import CORE


SCRIPT=CORE+r'''
(async()=>{
 const s=JSON.parse(document.querySelector('#state').textContent),base=s.draft,[w,h]=s.candidate.canvas;
 let doc=structuredClone(base),undo=[],active=null;const status=document.querySelector('#status');
 const edit=document.querySelector('#edit'),preview=document.querySelector('#preview');for(const c of [edit,preview]){c.width=w;c.height=h;}
 const ctx=edit.getContext('2d'),out=preview.getContext('2d'),image=new Image();image.src=s.target;await image.decode();ctx.drawImage(image,0,0);const original=ctx.getImageData(0,0,w,h);
 const refs=await Promise.all(s.references.map(async r=>{const image=new Image();image.src=r.image;await image.decode();return {...r,image};}));
 function validate(doc){
  if(!doc||Object.keys(doc).sort().join()!==Object.keys(base).sort().join()||doc.production_authorized!==false)throw Error('草稿身份不符');
  for(const k of Object.keys(base))if(!['choices','local_strokes'].includes(k)&&JSON.stringify(doc[k])!==JSON.stringify(base[k]))throw Error('草稿来源不符');
  if(!Array.isArray(doc.choices)||doc.choices.length!==base.choices.length)throw Error('分组不符');
  doc.choices.forEach((r,i)=>{if(!r||Object.keys(r).sort().join()!=='action,id'||r.id!==base.choices[i].id||!['remove','keep','uncertain'].includes(r.action))throw Error('分组决定无效');});
  validateSplit(s.candidate.stroke_template,{...s.candidate.stroke_template,strokes:doc.local_strokes});return structuredClone(doc);
 }
 function remember(){undo.push(structuredClone(doc));if(undo.length>100)undo.shift();}
 function draw(){
  const remove=new Uint8Array(w*h),veto=new Uint8Array(w*h),hint=new Uint8Array(w*h);
  s.candidate.groups.forEach((g,i)=>{for(const [y,a,b] of g.spans)for(let x=a;x<b;x++){const k=y*w+x;hint[k]=1;if(doc.choices[i].action==='remove')remove[k]=1;else veto[k]=1;}});
  const local=rasterSplit({...s.candidate.stroke_template,strokes:doc.local_strokes});
  const left=new ImageData(new Uint8ClampedArray(original.data),w,h),right=new ImageData(new Uint8ClampedArray(original.data),w,h);let removed=0;
  for(let i=0;i<remove.length;i++){
   const cut=local[i]===1||(local[i]===0&&remove[i]&&!veto[i]);
   if(cut){right.data[i*4+3]=0;if(original.data[i*4+3])removed++;}
   if(cut||local[i]===2||(hint[i]&&document.querySelector('#hints').checked)){
    left.data[i*4]=local[i]===2?20:255;left.data[i*4+1]=local[i]===2?210:cut?60:180;left.data[i*4+2]=40;left.data[i*4+3]=Math.max(100,left.data[i*4+3]);
   }
  }
  ctx.putImageData(left,0,0);out.putImageData(right,0,0);if(document.querySelector('#reference').checked)for(const r of refs)out.drawImage(r.image,r.x,r.y);
  doc.choices.forEach((r,i)=>document.querySelector('[data-group="'+i+'"]').value=r.action);
  status.textContent=`保留原11笔结果；本轮拟移除 ${removed} 个可见像素，局部修正 ${doc.local_strokes.length} 笔。尚未采用。`;
 }
 document.querySelectorAll('[data-group]').forEach(e=>e.onchange=()=>{remember();doc.choices[+e.dataset.group].action=e.value;draw();});
 const point=e=>{const b=edit.getBoundingClientRect();return [Math.max(0,Math.min(w-1,Math.floor((e.clientX-b.left)*w/b.width))),Math.max(0,Math.min(h-1,Math.floor((e.clientY-b.top)*h/b.height)))];};
 const full=()=>doc.local_strokes.length>=500||doc.local_strokes.reduce((n,r)=>n+r.points.length,0)>=4096;
 edit.onpointerdown=e=>{if(e.button!==0||document.querySelector('#mode').value==='inspect'||full())return;remember();active={mode:document.querySelector('#mode').value,radius:+document.querySelector('#radius').value,points:[point(e)]};doc.local_strokes.push(active);edit.setPointerCapture(e.pointerId);draw();};
 edit.onpointermove=e=>{if(!active||full())return;const p=point(e),last=active.points.at(-1);if(p[0]!==last[0]||p[1]!==last[1]){active.points.push(p);draw();}};
 edit.onpointerup=edit.onpointercancel=()=>active=null;
 document.querySelector('#undo').onclick=()=>{active=null;if(undo.length)doc=undo.pop();draw();};
 document.querySelector('#reset').onclick=()=>{remember();active=null;doc=structuredClone(base);draw();};
 for(const id of ['reference','hints'])document.querySelector('#'+id).onchange=draw;
 document.querySelector('#save').onclick=()=>{const blob=new Blob([JSON.stringify(validate(doc))],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='wing-projection-draft-v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 document.querySelector('#load').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>128000)throw Error('文件过大');const next=validate(JSON.parse(await f.text()));remember();active=null;doc=next;draw();}catch(error){status.textContent='恢复失败：'+error.message;}finally{e.target.value='';}};
 draw();window.projectionReady=true;
})().catch(e=>{document.querySelector('#status').textContent=e.message;window.projectionFailure=e.message;});
'''


def render(candidate,draft,source,files):
    def image(raw):return 'data:image/png;base64,'+base64.b64encode(raw).decode()
    regions={r['id']:r for r in source['regions']};ox,oy=regions['topwear']['setup_vertices_xy'][0]
    refs=[dict(x=r['setup_vertices_xy'][0][0]-ox,y=r['setup_vertices_xy'][0][1]-oy,image=image(files['editor/images/'+n+'.png'])) for n,r in regions.items() if n!='topwear']
    state=dict(candidate=candidate,draft=draft,target=image(files['editor/images/topwear.png']),references=refs)
    controls=''.join(f'<label>{g["id"]} · {g["pixel_count"]}像素 <select data-group="{i}"><option value="uncertain">不确定</option><option value="remove">移除候选</option><option value="keep">保留</option></select></label>' for i,g in enumerate(candidate['groups']))
    payload=json.dumps(state,ensure_ascii=True).replace('<','\\u003c')
    return f'''<!doctype html><meta charset="utf-8"><title>主翼投影分组复核</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<style>body{{font:17px/1.7 system-ui;margin:24px;background:#f4f6f8;color:#243448}}label{{display:inline-block;margin:8px}}button,select{{padding:8px}}main{{display:flex;gap:20px}}section{{width:50%;overflow:auto}}canvas{{width:100%;height:auto;touch-action:none;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/16px 16px}}</style>
<h1>主翼投影：分组复核与局部修正</h1><p>已有11笔清理保持不变。黄色区域是翼片alpha反向投影，不证明上衣像素应删除；无膨胀、无补全。默认全部不确定。</p>
<div>{controls}</div><label>局部笔刷 <select id="mode"><option value="inspect">仅查看</option><option value="remove">待移除</option><option value="keep">明确保留</option><option value="erase">恢复分组结果</option></select></label>
<label>半径 <input id="radius" type="range" min="1" max="64" value="12"></label><button id="undo">撤销</button><button id="reset">重置本轮</button><button id="save">保存完整草稿</button><input id="load" type="file" accept=".json">
<label><input id="reference" type="checkbox" checked>叠加翼片参考</label><label><input id="hints" type="checkbox" checked>显示候选</label><p id="status">加载…</p>
<main><section><h2>已清理上衣＋本轮遮罩</h2><canvas id="edit"></canvas></section><section><h2>本轮静态预览</h2><canvas id="preview"></canvas></section></main>
<p>红＝本轮拟移除，绿＝局部保留。局部笔画优先于分组；重叠分组含保留或不确定时默认保留。保存后提交 JSON 再生成候选，没有生产授权。</p>
<script id="state" type="application/json">{payload}</script><script>{SCRIPT}</script>'''
