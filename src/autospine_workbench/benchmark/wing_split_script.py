"""Canvas editor and deterministic brush shared with Python validation tests."""
CORE=r'''
function validateSplit(base,doc){
 if(!doc||Object.keys(doc).sort().join()!=Object.keys(base).sort().join()||doc.production_authorized!==false)throw Error('草稿身份不符');
 for(const k of Object.keys(base))if(k!=='strokes'&&JSON.stringify(doc[k])!==JSON.stringify(base[k]))throw Error('草稿来源不符');
 if(!Array.isArray(doc.strokes)||doc.strokes.length>500)throw Error('笔画数量超限');let total=0;
 for(const s of doc.strokes){
  if(!s||Object.keys(s).sort().join()!=='mode,points,radius'||!['remove','keep','erase'].includes(s.mode)||!Number.isInteger(s.radius)||s.radius<1||s.radius>64)throw Error('笔刷无效');
  if(!Array.isArray(s.points)||!s.points.length||(total+=s.points.length)>4096)throw Error('点数超限');
  for(const p of s.points)if(!Array.isArray(p)||p.length!==2||p.some((v,i)=>!Number.isInteger(v)||v<0||v>=base.canvas[i]))throw Error('坐标无效');
 }return structuredClone(doc);
}
function paintSplit(mask,w,h,s,from,to){
 const r=s.radius,value={erase:0,remove:1,keep:2}[s.mode];
 function stamp(cx,cy){for(let y=Math.max(0,cy-r);y<Math.min(h,cy+r+1);y++)for(let x=Math.max(0,cx-r);x<Math.min(w,cx+r+1);x++)if((x-cx)**2+(y-cy)**2<=r*r)mask[y*w+x]=value;}
 const n=Math.max(Math.abs(to[0]-from[0]),Math.abs(to[1]-from[1]));stamp(...from);
 for(let i=1;i<=n;i++)stamp(...from.map((a,j)=>Math.floor(a+(to[j]-a)*i/n+.5)));
}
function rasterSplit(doc){const [w,h]=doc.canvas,mask=new Uint8Array(w*h);for(const s of doc.strokes){let previous=s.points[0];for(const p of s.points){paintSplit(mask,w,h,s,previous,p);previous=p;}}return mask;}
'''

SCRIPT=CORE+r'''
(async()=>{
 const state=JSON.parse(document.querySelector('#state').textContent),base=state.draft;
 let doc=structuredClone(base),mask=rasterSplit(doc),active=null,redo=[],resetUndo=null;
 const [w,h]=base.canvas,edit=document.querySelector('#edit'),preview=document.querySelector('#preview'),status=document.querySelector('#status');
 for(const c of [edit,preview]){c.width=w;c.height=h;}
 const ctx=edit.getContext('2d'),out=preview.getContext('2d'),original=new Image();
 original.src=state.image;await original.decode();ctx.drawImage(original,0,0);const pixels=ctx.getImageData(0,0,w,h);
 const refs=await Promise.all(state.references.map(async r=>{const image=new Image();image.src=r.image;await image.decode();return {...r,image};}));
 function draw(){
  const overlay=new ImageData(new Uint8ClampedArray(pixels.data),w,h),result=new ImageData(new Uint8ClampedArray(pixels.data),w,h);
  let removed=0,kept=0;
  for(let i=0;i<mask.length;i++){
   if(mask[i]===1){result.data[i*4+3]=0;if(pixels.data[i*4+3])removed++;}
   if(mask[i]===2&&pixels.data[i*4+3])kept++;
   if(mask[i]){overlay.data[i*4]=mask[i]===1?255:20;overlay.data[i*4+1]=mask[i]===2?210:60;overlay.data[i*4+2]=65;overlay.data[i*4+3]=Math.max(140,pixels.data[i*4+3]);}
  }
  ctx.putImageData(overlay,0,0);out.clearRect(0,0,w,h);out.putImageData(result,0,0);
  if(document.querySelector('#hints').checked){ctx.strokeStyle='#cb8300';ctx.lineWidth=2;for(const b of state.hints)ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);}
  if(document.querySelector('#reference').checked)for(const r of refs)out.drawImage(r.image,r.x,r.y);
  status.textContent=`${doc.strokes.length} 笔 · 待移除 ${removed} 个可见像素 · 明确保留 ${kept} 个可见像素；草稿未采用`;
 }
 function point(e){const b=edit.getBoundingClientRect();return [Math.max(0,Math.min(w-1,Math.floor((e.clientX-b.left)*w/b.width))),Math.max(0,Math.min(h-1,Math.floor((e.clientY-b.top)*h/b.height)))];}
 function limit(){return doc.strokes.reduce((n,s)=>n+s.points.length,0)>=4096;}
 edit.onpointerdown=e=>{if(e.button!==0||doc.strokes.length>=500||limit())return;resetUndo=null;active={mode:document.querySelector('#mode').value,radius:+document.querySelector('#radius').value,points:[point(e)]};doc.strokes.push(active);redo=[];paintSplit(mask,w,h,active,active.points[0],active.points[0]);edit.setPointerCapture(e.pointerId);draw();};
 edit.onpointermove=e=>{if(!active||limit())return;const p=point(e),last=active.points.at(-1);if(p[0]===last[0]&&p[1]===last[1])return;active.points.push(p);paintSplit(mask,w,h,active,last,p);draw();};
 edit.onpointerup=edit.onpointercancel=()=>{active=null;};
 document.querySelector('#undo').onclick=()=>{active=null;if(resetUndo){doc=resetUndo;resetUndo=null;redo=[];}else if(doc.strokes.length)redo.push(doc.strokes.pop());mask=rasterSplit(doc);draw();};
 document.querySelector('#redo').onclick=()=>{active=null;if(redo.length)doc.strokes.push(redo.pop());mask=rasterSplit(doc);draw();};
 document.querySelector('#clear').onclick=()=>{active=null;resetUndo=structuredClone(doc);doc=structuredClone(base);redo=[];mask=rasterSplit(doc);draw();};
 for(const id of ['hints','reference'])document.querySelector('#'+id).onchange=draw;
 document.querySelector('#zoom').oninput=e=>{for(const c of [edit,preview])c.style.width=(w*Number(e.target.value)/100)+'px';};
 document.querySelector('#zoom').dispatchEvent(new Event('input'));
 document.querySelector('#save').onclick=()=>{const verified=validateSplit(base,doc),blob=new Blob([JSON.stringify(verified)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='wing-split-draft-v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 document.querySelector('#load').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>128000)throw Error('草稿文件过大');const restored=validateSplit(base,JSON.parse(await file.text()));doc=restored;active=null;redo=[];resetUndo=null;mask=rasterSplit(doc);draw();}catch(error){status.textContent='恢复失败：'+error.message;}finally{e.target.value='';}};
 draw();window.splitReady=true;
})().catch(e=>{document.querySelector('#status').textContent=e.message;window.splitFailure=e.message;});
'''
